import pandas as pd
import pytest
import yaml
from sqlalchemy import types
from sqlalchemy.dialects import mssql as mssql_types
from sqlalchemy.dialects import postgresql as pg_types

from qa_orchestrator.services.syn_dataloader.syntheticgen.result_storage import (
    DBType,
    _drop_existing_pg_enum_types,
    _schema_type_to_sa_type,
    get_dtype_overrides_from_config,
    infer_dtypes_from_dataframe,
)


@pytest.mark.parametrize(
    "df, expected, db_type",
    [
        (pd.DataFrame({"a": [1, 2, 3]}), {"a": types.BigInteger()}, DBType.POSTGRES),
        # None values are converted to NaN, making it the dtype Float. Good case use case for overrides
        (pd.DataFrame({"a": [None, 2, None]}), {"a": types.Float()}, DBType.POSTGRES),
    ],
)
def test_get_numeric_type_from_mapping(df, expected, db_type):
    """Verify the correct numeric dtypes are returned for various mappings."""
    mapping = infer_dtypes_from_dataframe(df, db_type)
    assert mapping if expected else True
    for col, dtype in mapping.items():
        expected_dtype = expected[col]
        assert type(dtype) is type(expected_dtype), (
            f"Expected {col} to be {expected_dtype}, got {dtype}"
        )


@pytest.mark.parametrize(
    "df, expected, db_type",
    [
        (pd.DataFrame({"a": [True, False]}), {"a": types.Boolean()}, DBType.POSTGRES),
        (pd.DataFrame({"a": [True, False]}), {"a": types.Boolean()}, DBType.MSSQL),
    ],
)
def test_get_boolean_type_from_mapping(df, expected, db_type):
    """Verify the correct boolean dtypes are returned for various mappings."""
    mapping = infer_dtypes_from_dataframe(df, db_type)
    assert mapping if expected else True
    for col, dtype in mapping.items():
        expected_dtype = expected[col]
        assert type(dtype) is type(expected_dtype), (
            f"Expected {col} to be {expected_dtype}, got {dtype}"
        )


@pytest.mark.parametrize(
    "df, expected, db_type, is_aware",
    [
        (
            pd.DataFrame({"a": [pd.to_datetime("2026-06-06 04:00:00")]}),
            {"a": types.DateTime()},
            DBType.POSTGRES,
            False,
        ),
        (
            pd.DataFrame({"a": [pd.to_datetime("2026-06-06 04:00:00")]}),
            {"a": types.DateTime()},
            DBType.MSSQL,
            False,
        ),
        (
            pd.DataFrame({"a": [pd.to_datetime("2026-06-06 04:00:00-04:00")]}),
            {"a": types.DateTime()},
            DBType.POSTGRES,
            True,
        ),
        (
            pd.DataFrame({"a": [pd.to_datetime("2026-06-06 04:00:00-04:00")]}),
            {"a": types.DateTime()},
            DBType.MSSQL,
            True,
        ),
    ],
)
def test_get_date_type_from_mapping(df, expected, db_type, is_aware):
    """Verify the correct date dtypes are returned for various mappings."""
    mapping = infer_dtypes_from_dataframe(df, db_type)
    assert mapping if expected else True
    for col, dtype in mapping.items():
        expected_dtype = expected[col]
        assert type(dtype) is type(expected_dtype), (
            f"Expected {col} to be {expected_dtype}, got {dtype}"
        )
        if is_aware:
            assert dtype.timezone, f"Expected {col} to be timezone aware, got {dtype}"


@pytest.mark.parametrize(
    "df, expected, db_type",
    [
        (pd.DataFrame({"a": ["test"]}), {"a": types.Unicode()}, DBType.POSTGRES),
        (pd.DataFrame({"a": ["†es†"]}), {"a": types.Unicode()}, DBType.POSTGRES),
        (pd.DataFrame({"a": ["test"]}), {"a": types.Unicode()}, DBType.MSSQL),
        (pd.DataFrame({"a": ["†es†"]}), {"a": types.Unicode()}, DBType.MSSQL),
    ],
)
def test_get_object_type_from_mapping(df, expected, db_type):
    """Verify the correct object dtypes are returned for various mappings."""
    mapping = infer_dtypes_from_dataframe(df, db_type)
    assert mapping if expected else True
    for col, dtype in mapping.items():
        expected_dtype = expected[col]
        assert type(dtype) is type(expected_dtype), (
            f"Expected {col} to be {expected_dtype}, got {dtype}"
        )


@pytest.mark.parametrize(
    "df, override, expected, db_type",
    [
        (
            pd.DataFrame({"a": ["test"], "b": ["†es†"]}),
            {"b": types.Text()},
            {"a": types.Unicode(), "b": types.Text()},
            DBType.MSSQL,
        ),
        (
            pd.DataFrame({"a": [None, 2, None]}),
            {"a": types.Integer()},
            {"a": types.Integer()},
            DBType.POSTGRES,
        ),
    ],
)
def test_override_mapping(df, override, expected, db_type):
    """Verify the mappings return overridden dtypes."""
    mapping = infer_dtypes_from_dataframe(df, db_type, overrides=override)
    assert mapping if expected else True
    for col, dtype in mapping.items():
        expected_dtype = expected[col]
        assert type(dtype) == type(expected_dtype), (
            f"Expected {col} to be {expected_dtype}, got {dtype}"
        )


def test_get_dtype_overrides_from_config():
    """Verify the overrides are correctly parsed from the config."""

    # This is not a realistic config because it's a mix of PostgreSQL and MSSQL types.
    override_config = yaml.safe_load("""\
overrides:
  fill_type: Text
  agg_value:
    type: Numeric
    precision: 10
    scale: 2
  timestamp:
    type: DATETIMEOFFSET
    timezone: true
  is_active: Boolean
  flag: BIT
""")
    overrides = get_dtype_overrides_from_config(override_config)

    fill_type_dtype = overrides["fill_type"]
    assert isinstance(fill_type_dtype, types.Text)

    agg_value_dtype = overrides["agg_value"]
    assert isinstance(agg_value_dtype, types.Numeric)
    assert agg_value_dtype.precision == 10
    assert agg_value_dtype.scale == 2

    timestamp_dtype = overrides["timestamp"]
    assert isinstance(timestamp_dtype, mssql_types.DATETIMEOFFSET)
    assert timestamp_dtype.timezone is True

    is_active_dtype = overrides["is_active"]
    assert isinstance(is_active_dtype, types.Boolean)

    flag_dtype = overrides["flag"]
    assert isinstance(flag_dtype, mssql_types.BIT)


def test_schema_type_aliases_mapping():
    tiny_int_type = _schema_type_to_sa_type({"type": "tiny int"})
    smallint_type = _schema_type_to_sa_type({"type": "smallint"})
    json_type = _schema_type_to_sa_type({"type": "jsonb"})
    datetime_offset_type = _schema_type_to_sa_type({"type": "datetime offset"})

    assert isinstance(tiny_int_type, types.SmallInteger)
    assert isinstance(smallint_type, types.SmallInteger)
    assert isinstance(json_type, types.JSON)
    assert isinstance(datetime_offset_type, types.DateTime)
    assert datetime_offset_type.timezone is True


def test_categorical_schema_type_creates_named_postgres_enum():
    enum_type = _schema_type_to_sa_type(
        {
            "type": "categorical",
            "values": ["ACTIVE", "INACTIVE"],
            "enum_name": "user_status_enum",
        }
    )

    assert isinstance(enum_type, pg_types.ENUM)
    assert enum_type.name == "user_status_enum"
    assert enum_type.create_type is True


def test_drop_existing_pg_enum_types_deduplicates_and_qualifies_names():
    executed_sql = []

    class DummyConnection:
        def execute(self, stmt):
            executed_sql.append(str(stmt))

    table_schema = {
        "columns": {
            "status": {
                "type": "categorical",
                "values": ["ACTIVE", "INACTIVE"],
                "enum_name": "userstatus",
                "create_type": True,
            },
            "status_copy": {
                "type": "enum",
                "values": ["ACTIVE", "INACTIVE"],
                "enum_name": "userstatus",
                "create_type": True,
            },
            "phase": {
                "type": "category",
                "values": ["A", "B"],
                "enum_name": "phase_state",
                "enum_schema": "custom",
                "create_type": True,
            },
            "name": {"type": "string"},
        }
    }

    _drop_existing_pg_enum_types(DummyConnection(), table_schema)

    assert executed_sql == [
        'DROP TYPE IF EXISTS "userstatus" CASCADE',
        'DROP TYPE IF EXISTS "custom"."phase_state" CASCADE',
    ]


def test_drop_existing_pg_enum_types_skips_create_type_false():
    executed_sql = []

    class DummyConnection:
        def execute(self, stmt):
            executed_sql.append(str(stmt))

    table_schema = {
        "columns": {
            "status": {
                "type": "categorical",
                "values": ["ACTIVE", "INACTIVE"],
                "enum_name": "userstatus",
                "create_type": False,
            }
        }
    }

    _drop_existing_pg_enum_types(DummyConnection(), table_schema)

    assert executed_sql == []
