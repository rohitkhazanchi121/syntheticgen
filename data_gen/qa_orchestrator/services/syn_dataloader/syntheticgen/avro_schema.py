import importlib
import json
import re
from pathlib import Path
from typing import Any


FIELD_X_KEY_MAP = {
    "x-min": "min",
    "x-max": "max",
    "x-null-probability": "null_probability",
    "x-true-probability": "true_probability",
    "x-values-probabilities": "values_probabilities",
    "x-server-default": "server_default",
    "x-semantic": "semantic",
}


class AvroSchemaProcessor:
    @staticmethod
    def read_local_schema(schema_path: Path, source: str) -> dict:
        if not schema_path.is_file():
            raise FileNotFoundError(f"AVRO schema file not found: {schema_path}")

        if source == "local_avsc":
            try:
                with open(schema_path, "r") as schema_file:
                    parsed_schema = json.load(schema_file)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Failed to parse AVSC schema from {schema_path}: {exc}") from exc
            if not isinstance(parsed_schema, dict):
                raise ValueError(f"AVSC schema must be a JSON object: {schema_path}")
            return parsed_schema

        try:
            fastavro_module = importlib.import_module("fastavro")
            avro_reader = fastavro_module.reader
        except ModuleNotFoundError as exc:
            raise ImportError("fastavro is required to read local_avro schema files") from exc

        try:
            with open(schema_path, "rb") as avro_file:
                schema_reader = avro_reader(avro_file)
                parsed_schema = getattr(schema_reader, "writer_schema", None)
        except Exception:
            parsed_schema = AvroSchemaProcessor.read_json_fallback(schema_path)

        if not isinstance(parsed_schema, dict):
            raise ValueError(f"Could not resolve writer schema from AVRO file: {schema_path}")
        return parsed_schema

    @staticmethod
    def read_json_fallback(schema_path: Path) -> dict:
        try:
            with open(schema_path, "r") as schema_file:
                parsed_schema = json.load(schema_file)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Failed to read AVRO container schema from {schema_path}. "
                "File is not a valid Avro OCF binary and is not valid JSON schema. "
                f"Underlying error: {exc}"
            ) from exc

        if not isinstance(parsed_schema, dict):
            raise ValueError(
                f"Failed to read AVRO schema from {schema_path}: JSON content must be an object schema"
            )
        return parsed_schema

    @staticmethod
    def map_schema_to_table_config(
        avro_schema: dict[str, Any],
        table_name: str | None,
        output_table_name: str | None,
        db_table_name: str | None,
    ) -> tuple[str, dict[str, Any]]:
        resolved_table_name = (
            table_name
            or output_table_name
            or db_table_name
            or avro_schema.get("x-sql-table")
            or avro_schema.get("name")
            or "synthetic_default"
        )

        field_defs = avro_schema.get("fields")
        if not isinstance(field_defs, list) or not field_defs:
            raise ValueError("AVRO schema must be a record with a non-empty fields array")

        primary_keys = avro_schema.get("x-primary-key")
        primary_key_set = set(primary_keys) if isinstance(primary_keys, list) else set()

        columns: dict[str, dict[str, Any]] = {}
        for field in field_defs:
            if not isinstance(field, dict):
                continue
            field_name = field.get("name")
            field_type = field.get("type")
            if not isinstance(field_name, str) or not field_name.strip():
                continue

            mapped = AvroSchemaProcessor._map_avro_field(field_name, field_type, field)
            if field_name in primary_key_set:
                mapped["primary_key"] = True
                mapped["nullable"] = False
            columns[field_name] = mapped

        if not columns:
            raise ValueError("No mappable AVRO fields were found in schema")

        table_config: dict[str, Any] = {"columns": columns}

        record_count = avro_schema.get("x-record-count")
        if record_count is not None:
            table_config["record_count"] = record_count

        load_mode = avro_schema.get("x-load-mode")
        if isinstance(load_mode, str) and load_mode.strip():
            table_config["load_mode"] = load_mode.strip()

        allow_duplicate_timestamps = avro_schema.get("x-allow-duplicate-timestamps")
        if isinstance(allow_duplicate_timestamps, bool):
            table_config["allow_duplicate_timestamps"] = allow_duplicate_timestamps

        sql_schema = avro_schema.get("x-sql-schema")
        if isinstance(sql_schema, str) and sql_schema.strip():
            table_config["target_schema"] = sql_schema.strip()

        return str(resolved_table_name), table_config

    @staticmethod
    def _map_avro_field(field_name: str, field_type: Any, field: dict[str, Any]) -> dict[str, Any]:
        nullable = False
        resolved_type = field_type

        if isinstance(field_type, list):
            non_null = [item for item in field_type if item != "null"]
            nullable = len(non_null) != len(field_type)
            if len(non_null) == 1:
                resolved_type = non_null[0]
            else:
                raise ValueError(f"Unsupported AVRO union type: {field_type}")

        mapped_type = "string"
        column: dict[str, Any] = {}

        if isinstance(resolved_type, str):
            mapped_type = AvroSchemaProcessor._map_avro_primitive_type(resolved_type)
        elif isinstance(resolved_type, dict):
            mapped_type, column = AvroSchemaProcessor._map_avro_complex_type(resolved_type, field_name)
        else:
            raise ValueError(f"Unsupported AVRO field type definition: {resolved_type}")

        column["type"] = mapped_type
        if nullable:
            column["nullable"] = True

        for avro_key, internal_key in FIELD_X_KEY_MAP.items():
            if avro_key in field:
                column[internal_key] = field.get(avro_key)

        return column

    @staticmethod
    def _map_avro_primitive_type(avro_type: str) -> str:
        primitive_map = {
            "string": "string",
            "boolean": "boolean",
            "int": "integer",
            "long": "integer",
            "float": "float",
            "double": "float",
            "bytes": "string",
            "fixed": "string",
            "enum": "categorical",
            "record": "string",
            "array": "string",
            "map": "string",
            "null": "string",
        }
        return primitive_map.get(str(avro_type).lower(), "string")

    @staticmethod
    def _map_avro_complex_type(type_def: dict[str, Any], field_name: str) -> tuple[str, dict[str, Any]]:
        avro_type = str(type_def.get("type", "string")).lower()
        logical_type = str(type_def.get("logicalType", "")).lower()

        if logical_type == "uuid":
            return "uuid", {}
        if logical_type in {
            "timestamp-millis",
            "timestamp-micros",
            "local-timestamp-millis",
            "local-timestamp-micros",
        }:
            return "datetime", {}
        if logical_type == "date":
            return "date", {}
        if logical_type in {"time-millis", "time-micros"}:
            return "time", {}
        if logical_type == "decimal":
            details = {}
            precision = type_def.get("precision")
            scale = type_def.get("scale")
            if precision is not None:
                details["precision"] = precision
            if scale is not None:
                details["scale"] = scale
            return "decimal", details

        if avro_type == "enum":
            details: dict[str, Any] = {}
            symbols = type_def.get("symbols")
            if isinstance(symbols, list) and symbols:
                details["values"] = symbols
            enum_type_name = type_def.get("name")
            details["enum_name"] = AvroSchemaProcessor._normalize_pg_enum_name(
                str(enum_type_name) if enum_type_name else f"{field_name}_enum"
            )
            details["create_type"] = True
            return "categorical", details

        return AvroSchemaProcessor._map_avro_primitive_type(avro_type), {}

    @staticmethod
    def _normalize_pg_enum_name(raw_name: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw_name).strip())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        if not normalized:
            return "synthetic_enum"
        if normalized[0].isdigit():
            normalized = f"enum_{normalized}"
        return normalized.lower()
