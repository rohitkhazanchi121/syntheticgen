import enum
import os
from typing import TypeAlias

import numpy as np
import pandas as pd
from sqlalchemy import inspect, text, types, MetaData, Table, Column
from sqlalchemy.dialects import mssql as mssql_types
from sqlalchemy.dialects import postgresql as pg_types

from qa_orchestrator.services.syn_dataloader.syntheticgen.logger import logger
from connecthub.helpers.dbconfig import DBDriver
from connecthub.sqlalchemy_sync import SyncSQLAlchemy

SATypeMapping: TypeAlias = dict[str, types.TypeEngine]

DEFAULT_DB_TYPE = DBDriver.POSTGRES


class DBType(enum.Enum):
    """Backward-compatible DB type alias used by tests and callers."""

    POSTGRES = DBDriver.POSTGRES
    MSSQL = DBDriver.AZURE_SQL


class LoadMode(enum.StrEnum):
    APPEND = "append"
    TRUNCATE_LOAD = "truncate_load"
    DROP_RECREATE = "drop_recreate"

# Mapping of string type names to SQLAlchemy types
# This is also used to determine what overrides are supported
# NOTE: `with_variant` could possibly be used to better handle different dialect defaults
TYPE_MAPPING = {
    # CamelCase types - tries to be database-agnostic
    #   string-like
    "Uuid": types.Uuid,
    "Text": types.Text,
    "String": types.String,
    "Unicode": types.Unicode,
    #   number-like
    "Float": types.Float,
    "Numeric": types.Numeric,
    "Integer": types.Integer,
    "SmallInteger": types.SmallInteger,
    "BigInteger": types.BigInteger,
    #   time-like
    "Date": types.Date,
    "Time": types.Time,
    "DateTime": types.DateTime,
    #   others
    "Boolean": types.Boolean,  # example of BOOLEAN for Postgres, but BIT for MSSQL
    # UPPERCASE types - database-specific types that require special handling
    "DATETIMEOFFSET": mssql_types.DATETIMEOFFSET,
    "BIT": mssql_types.BIT,
}


def _normalize_db_type(db_type: str | None) -> DBDriver | None:
    """Normalize user-provided DB type values to supported enum values."""
    if not db_type:
        return None

    normalized = db_type.strip().lower().replace("-", "_")
    alias_map = {
        "postgres": DBDriver.POSTGRES,
        "postgresql": DBDriver.POSTGRES,
        "postgressql": DBDriver.POSTGRES,
        "pg": DBDriver.POSTGRES,
        "mssql": DBDriver.AZURE_SQL,
        "sqlserver": DBDriver.AZURE_SQL,
        "sql_server": DBDriver.AZURE_SQL,
        "azure_sql": DBDriver.AZURE_SQL,
        "azuresql": DBDriver.AZURE_SQL,
    }
    return alias_map.get(normalized)


def _coerce_db_type(db_type: DBDriver | DBType | None) -> DBDriver:
    if isinstance(db_type, DBType):
        return db_type.value
    if isinstance(db_type, DBDriver):
        return db_type
    return DEFAULT_DB_TYPE


def _normalize_load_mode(load_mode: str | None) -> LoadMode:
    if not load_mode:
        return LoadMode.TRUNCATE_LOAD

    normalized = load_mode.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "append": LoadMode.APPEND,
        "truncate_load": LoadMode.TRUNCATE_LOAD,
        "truncate": LoadMode.TRUNCATE_LOAD,
        "truncate_and_load": LoadMode.TRUNCATE_LOAD,
        "drop_recreate": LoadMode.DROP_RECREATE,
        "drop_and_recreate": LoadMode.DROP_RECREATE,
        "replace": LoadMode.DROP_RECREATE,
    }
    mode = aliases.get(normalized)
    if mode is None:
        raise ValueError(
            f"Unsupported load mode '{load_mode}'. Supported values: "
            "append, truncate_load, drop_recreate"
        )
    return mode


def _infer_sqlalchemy_dtype(
    series: pd.Series, db_type: DBDriver | DBType | None = None
) -> types.TypeEngine | None:
    """Try to determine SQLAlchemy dtype based on pandas dtype.

    Args:
        series (pd.Series): The series to infer dtype from.
        db_type (DBType | None): The DB sink type.

    Returns:
        types.TypeEngine | None: The SQLAlchemy type (default to None).
    """
    db_type = _coerce_db_type(db_type)
    dtype = series.dtype

    # int
    if pd.api.types.is_integer_dtype(dtype):
        return types.BigInteger() if dtype == np.int64 else types.Integer()

    # float
    if pd.api.types.is_float_dtype(dtype):
        return types.Float()

    # boolean
    if pd.api.types.is_bool_dtype(dtype):
        return types.Boolean()

    # datetime
    if pd.api.types.is_datetime64_any_dtype(dtype):
        tz = getattr(dtype, "tz", None) is not None
        return types.DateTime(timezone=tz)

    # object / string
    if pd.api.types.is_object_dtype(dtype) or pd.api.types.is_string_dtype(dtype):
        return _infer_object_type(db_type)

    return None


def _infer_object_type(db_type: DBDriver | None = None) -> types.TypeEngine:
    """Try to determine what object type it is.

    Args:
        db_type (DBType | None): The DB sink type.

    Returns:
        types.TypeEngine | None: The SQLAlchemy type (default to types.Unicode()).
    """
    return types.Unicode()


def infer_dtypes_from_dataframe(
    df: pd.DataFrame,
    db_type: DBDriver | DBType | None = None,
    overrides: SATypeMapping | None = None,
) -> SATypeMapping:
    """Try to infer the appropriate type for each column in the dataframe.

    Allows overriding type mappings with the 'overrides' parameter.

    Args:
        df (pd.DataFrame): The dataframe to infer dtypes from.
        db_type (DBType | None): The DB sink type.
        overrides (SATypeMapping | None): Dtype overrides from the config.

    Returns:
        SATypeMapping: A mapping of column names to SQLAlchemy types.
    """
    db_type = _coerce_db_type(db_type)
    result = {}
    for col in df.columns:
        mapped = _infer_sqlalchemy_dtype(df[col], db_type)
        if mapped is not None:
            result[col] = mapped
    if overrides:
        result.update(overrides)
    return result


def _schema_type_to_sa_type(column_config: dict) -> types.TypeEngine:
    type_name = str(column_config.get("type", "string")).lower().strip()
    compact_type = type_name.replace("_", "").replace(" ", "")
    length = column_config.get("length")
    precision = column_config.get("precision")
    scale = column_config.get("scale")

    if compact_type in {"enum", "categorical", "category"}:
        enum_values = column_config.get("values")
        enum_name = column_config.get("enum_name")
        enum_schema = column_config.get("enum_schema")
        create_type = bool(column_config.get("create_type", True))
        if isinstance(enum_values, list) and enum_values:
            return pg_types.ENUM(
                *[str(value) for value in enum_values],
                name=str(enum_name) if enum_name else None,
                schema=str(enum_schema) if enum_schema else None,
                create_type=create_type,
            )

    if compact_type in {"string", "varchar"}:
        return types.String(length=int(length)) if length else types.String()
    if compact_type in {"text", "citext", "xml", "clob"}:
        return types.Text()
    if compact_type in {"char"}:
        return types.CHAR(length=int(length)) if length else types.CHAR()
    if compact_type in {"unicode", "nvarchar"}:
        return types.Unicode(length=int(length)) if length else types.Unicode()
    if compact_type in {"nchar"}:
        return types.NCHAR(length=int(length)) if length else types.NCHAR()
    if compact_type in {"uuid", "uniqueidentifier"}:
        return types.Uuid()
    if compact_type in {"json", "jsonb"}:
        return types.JSON()
    if compact_type in {"binary", "varbinary", "blob", "bytea"}:
        return types.LargeBinary(length=int(length)) if length else types.LargeBinary()

    if compact_type in {"integer", "int", "int4", "serial"}:
        return types.Integer()
    if compact_type in {"bigint", "int8", "bigserial"}:
        return types.BigInteger()
    if compact_type in {"smallint", "int2", "tinyint"}:
        return types.SmallInteger()
    if compact_type in {"numeric", "decimal", "dec"}:
        kwargs = {}
        if precision is not None:
            kwargs["precision"] = int(precision)
        if scale is not None:
            kwargs["scale"] = int(scale)
        return types.Numeric(**kwargs)
    if compact_type in {"float", "double", "number", "numericfloat", "real", "doubleprecision"}:
        return types.Float()

    if compact_type in {"datetime", "timestamp", "datetime2", "smalldatetime"}:
        return types.DateTime()
    if compact_type in {"datetimeoffset", "timestamptz"}:
        return types.DateTime(timezone=True)
    if compact_type in {"date"}:
        return types.Date()
    if compact_type in {"time"}:
        return types.Time()

    if compact_type in {"boolean", "bool", "bit"}:
        return types.Boolean()

    return types.Unicode(length=int(length)) if length else types.Unicode()


def _get_active_table_schema(config: dict, table_name: str) -> dict | None:
    schema = config.get("schema", {})
    tables = schema.get("tables", {})
    if not isinstance(tables, dict) or not tables:
        return None

    active_table_name = schema.get("_active_table_name")
    if active_table_name and active_table_name in tables:
        return tables.get(active_table_name)

    if table_name in tables:
        return tables.get(table_name)

    if len(tables) == 1:
        return next(iter(tables.values()))

    return None


def _get_active_table_target(config: dict, output_table_name: str | None) -> tuple[str, dict | None]:
    schema = config.get("schema", {})
    tables = schema.get("tables", {})
    if isinstance(tables, dict) and tables:
        active_table_name = schema.get("_active_table_name")
        if isinstance(active_table_name, str) and active_table_name in tables:
            return active_table_name, tables.get(active_table_name)

        if output_table_name and output_table_name in tables:
            return output_table_name, tables.get(output_table_name)

        fallback_name = next(iter(tables))
        return fallback_name, tables.get(fallback_name)

    fallback_output_name = output_table_name or "synthetic_default"
    return fallback_output_name, None


def _get_schema_dtype_overrides(table_schema: dict | None) -> SATypeMapping:
    if not isinstance(table_schema, dict):
        return {}

    columns = table_schema.get("columns", {})
    if not isinstance(columns, dict):
        return {}

    result: SATypeMapping = {}
    for col_name, col_config in columns.items():
        if isinstance(col_config, dict):
            result[col_name] = _schema_type_to_sa_type(col_config)
    return result


def _quote_pg_identifier(identifier: str) -> str:
    escaped = str(identifier).replace('"', '""')
    return f'"{escaped}"'


def _drop_existing_pg_enum_types(connection, table_schema: dict):
    columns = table_schema.get("columns", {})
    if not isinstance(columns, dict) or not columns:
        return

    seen_enum_types: set[tuple[str | None, str]] = set()
    for col_config in columns.values():
        if not isinstance(col_config, dict):
            continue

        raw_type = str(col_config.get("type", "string")).lower().strip()
        compact_type = raw_type.replace("_", "").replace(" ", "")
        if compact_type not in {"enum", "categorical", "category"}:
            continue

        if not bool(col_config.get("create_type", True)):
            continue

        enum_name = col_config.get("enum_name")
        if not isinstance(enum_name, str) or not enum_name.strip():
            continue

        enum_schema = col_config.get("enum_schema")
        enum_schema_value = str(enum_schema).strip() if enum_schema else None
        enum_key = (enum_schema_value, enum_name.strip())
        if enum_key in seen_enum_types:
            continue
        seen_enum_types.add(enum_key)

        enum_type_name = _quote_pg_identifier(enum_name.strip())
        if enum_schema_value:
            qualified_enum_type = f"{_quote_pg_identifier(enum_schema_value)}.{enum_type_name}"
        else:
            qualified_enum_type = enum_type_name

        connection.execute(text(f"DROP TYPE IF EXISTS {qualified_enum_type} CASCADE"))


def _ensure_table_from_schema(connection, table_name: str, table_schema: dict, load_mode: LoadMode):
    columns = table_schema.get("columns", {})
    if not isinstance(columns, dict) or not columns:
        return

    metadata = MetaData()
    sa_columns = []
    for col_name, col_config in columns.items():
        if not isinstance(col_config, dict):
            continue

        kwargs = {
            "nullable": bool(col_config.get("nullable", True)),
            "primary_key": bool(col_config.get("primary_key", False)),
        }
        server_default = col_config.get("server_default")
        if server_default is not None:
            kwargs["server_default"] = text(str(server_default))

        sa_columns.append(
            Column(
                col_name,
                _schema_type_to_sa_type(col_config),
                **kwargs,
            )
        )

    if not sa_columns:
        return

    table = Table(table_name, metadata, *sa_columns)
    if load_mode == LoadMode.DROP_RECREATE:
        table.drop(bind=connection, checkfirst=True)
        dialect_name = getattr(connection.engine.dialect, "name", "").lower()
        if dialect_name in {"postgresql", "postgres"}:
            _drop_existing_pg_enum_types(connection, table_schema)
        table.create(bind=connection, checkfirst=False)
    else:
        table.create(bind=connection, checkfirst=True)


def _truncate_existing_table(connection, dialect_name: str, table_name: str):
    if dialect_name in {"postgresql", "postgres"}:
        query = text(
            f"""DO $$
                    BEGIN
                        IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = '{table_name}') THEN
                            EXECUTE 'TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE;';
                        END IF;
                    END $$;
                """
        )
        connection.execute(query)
        return

    if dialect_name == "mssql":
        connection.execute(
            text(
                f"""IF OBJECT_ID(N'{table_name}', N'U') IS NOT NULL
                        BEGIN
                            TRUNCATE TABLE {table_name};
                        END;
                    """
            )
        )
        return

    logger.warning(
        f"Skipping truncate for unsupported dialect '{dialect_name}'."
    )


def get_sa_type_from_config(config: str | dict) -> types.TypeEngine:
    """Given a config, return the corresponding SQLAlchemy type.

    An example of a config could be:
        1. str - "Text"
        2. dict - {"type": "Numeric", "precision": 10, "scale": 2}

    Args:
        config (str | dict): Config containing the override details.

    Returns:
        types.TypeEngine: The mapped SQLAlchemy type.
    """
    if isinstance(config, str):
        type_name = config
        kwargs = {}
    elif isinstance(config, dict):
        cfg = config.copy()
        type_name = cfg.pop("type", None)
        if type_name is None:
            raise ValueError("Missing 'type' in config")
        kwargs = cfg
    else:
        raise ValueError(f"Invalid config type: {type(config)}")

    if type_name not in TYPE_MAPPING:
        raise ValueError(f"Unsupported type: {type_name}")

    return TYPE_MAPPING[type_name](**kwargs)


def get_dtype_overrides_from_config(config: dict) -> SATypeMapping:
    """Get overrides from a config dict and return a mapping of column names to SQLAlchemy types.

    Expects that the config has the structure:
        {
            "overrides": {
                ...
            }
        }

    Args:
        config (dict): Config containing the overrides.

    Returns:
        SATypeMapping: A mapping of column names to SQLAlchemy types.
    """
    result = {}
    override_config = config.get("overrides", {})
    for col_name, col_config in override_config.items():
        try:
            result[col_name] = get_sa_type_from_config(col_config)
        except (ValueError, TypeError) as e:
            logger.error(f"Error processing override for column {col_name}: {e}")
    return result


class ResultStorage:
    def __init__(self, config):
        self.config = config
        self.batch = []
        

    def store(self, records):
        if not records:
            logger.info("No records to store.")
            return
        df = pd.DataFrame(records)
        for col in df.columns:
            if "timestamp" in col:
                df[col] = pd.to_datetime(df[col])

        config_output = self.config.get("output", {})
        config_sink = config_output.get("sink")
        if config_sink == "db":
            db_conf = config_output.get("db_config", {}) or {}
            
            raw_db_type = (
                config_output.get("type")
                or config_output.get("sink_type")
                or db_conf.get("type")
            )
            if not raw_db_type:
                raise ValueError(
                    "Database sink requires output.type (or legacy output.db_config.type)."
                )
            normalized_db_type = _normalize_db_type(raw_db_type)
            db_driver = normalized_db_type.value if normalized_db_type else raw_db_type

            try:
                self.alchemy = SyncSQLAlchemy(driver=db_driver)
                self.sql_alchemy_engine = self.alchemy.get_sync_engine()
            except Exception as e:
                raise e
            
            
            overrides = get_dtype_overrides_from_config(self.config)
            
            effective_db_type = normalized_db_type or DEFAULT_DB_TYPE
            table_name, table_schema = _get_active_table_target(
                self.config,
                config_output.get("table_name") or db_conf.get("table_name"),
            )
            table_load_mode = table_schema.get("load_mode") if isinstance(table_schema, dict) else None
            load_mode = _normalize_load_mode(
                table_load_mode
                or config_output.get("load_mode")
                or db_conf.get("load_mode")
            )
            schema_type_overrides = _get_schema_dtype_overrides(table_schema)

            dtype = infer_dtypes_from_dataframe(
                df,
                db_type=effective_db_type,
                overrides={**schema_type_overrides, **overrides},
            )

            with self.sql_alchemy_engine.begin() as connection:
                dialect_name = getattr(connection.engine.dialect, "name", "").lower()
                table_exists = inspect(connection).has_table(table_name)

                if table_schema:
                    _ensure_table_from_schema(connection, table_name, table_schema, load_mode)
                    table_exists = True
                elif load_mode == LoadMode.DROP_RECREATE and table_exists:
                    Table(table_name, MetaData()).drop(bind=connection, checkfirst=True)
                    table_exists = False

                if load_mode == LoadMode.TRUNCATE_LOAD and table_exists:
                    _truncate_existing_table(connection, dialect_name, table_name)

                df.to_sql(
                    table_name,
                    con=connection,
                    if_exists="replace" if (load_mode == LoadMode.DROP_RECREATE and not table_schema) else "append",
                    index=False,
                    dtype=dtype,
                )
                logger.info(
                    f"Data successfully written to {table_name} table with {len(df)} records in {dialect_name or db_driver} database using mode '{load_mode}'."
                )
            return True
        else:
            logger.info("No output configured, returning as a dataframe")
            return df
