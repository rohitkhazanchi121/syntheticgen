import json

import pytest

from qa_orchestrator.services.syn_dataloader.syntheticgen.config_loader import ConfigLoader


def _base_config(schema_block):
    return {
        "general": {"duration_hours": 1, "default_frequency": "1sec"},
        "output": {"sink": "db", "db_config": {"type": "postgresql"}},
        "rules": {"entity_file": None, "defaults": {"record_count": 10}},
        "schema": schema_block,
    }


def test_yaml_source_columns_shorthand_is_normalized_to_output_fields_and_tables():
    config_data = _base_config(
        {
            "source": "yaml",
            "columns": ["sensor_tag", "reading_timestamp", "temperature_c"],
        }
    )

    loader = ConfigLoader(base_path=".", config_data=config_data)
    loader.load_main_config()

    schema = loader.config["schema"]
    assert schema["output_fields"] == ["sensor_tag", "reading_timestamp", "temperature_c"]
    assert "tables" in schema
    active_table = schema["tables"][schema["_active_table_name"]]
    assert set(active_table["columns"].keys()) == {"sensor_tag", "reading_timestamp", "temperature_c"}


def test_local_avsc_requires_path():
    config_data = _base_config(
        {
            "source": "local_avsc",
            "avro": {},
        }
    )

    loader = ConfigLoader(base_path=".", config_data=config_data)

    with pytest.raises(ValueError, match="schema.avro.path"):
        loader.load_main_config()


def test_local_avsc_schema_is_mapped_to_columns(tmp_path):
    avro_schema = {
        "type": "record",
        "name": "telemetry",
        "fields": [
            {"name": "sensor_tag", "type": "string"},
            {"name": "reading_timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}},
            {
                "name": "temperature_c",
                "type": [
                    "null",
                    {"type": "bytes", "logicalType": "decimal", "precision": 8, "scale": 2},
                ],
            },
            {
                "name": "status",
                "type": {
                    "type": "enum",
                    "name": "status_enum",
                    "symbols": ["GOOD", "BAD"],
                },
            },
        ],
    }
    avsc_file = tmp_path / "telemetry.avsc"
    avsc_file.write_text(json.dumps(avro_schema), encoding="utf-8")

    config_data = _base_config(
        {
            "source": "local_avsc",
            "table_defaults": {
                "load_mode": "drop_recreate",
                "allow_duplicate_timestamps": True,
                "record_count": 777,
            },
            "avro": {"path": str(avsc_file), "table_name": "telemetry_table"},
        }
    )

    loader = ConfigLoader(base_path=str(tmp_path), config_data=config_data)
    loader.load_main_config()

    schema = loader.config["schema"]
    assert schema["_active_table_name"] == "telemetry_table"
    columns = schema["tables"]["telemetry_table"]["columns"]
    assert columns["sensor_tag"]["type"] == "string"
    assert columns["reading_timestamp"]["type"] == "datetime"
    assert columns["temperature_c"]["type"] == "decimal"
    assert columns["temperature_c"]["nullable"] is True
    assert columns["temperature_c"]["precision"] == 8
    assert columns["temperature_c"]["scale"] == 2
    assert columns["status"]["type"] == "categorical"
    assert columns["status"]["values"] == ["GOOD", "BAD"]
    assert columns["status"]["enum_name"] == "status_enum"
    assert columns["status"]["create_type"] is True
    assert schema["tables"]["telemetry_table"]["load_mode"] == "drop_recreate"
    assert schema["tables"]["telemetry_table"]["allow_duplicate_timestamps"] is True
    assert schema["tables"]["telemetry_table"]["record_count"] == 777


def test_apicurio_registry_source_uses_subject_and_version(monkeypatch):
    config_data = _base_config(
        {
            "source": "apicurio_registry",
            "registry": {
                "subject": "telemetry-value",
                "version": 7,
                "table_name": "telemetry_registry_table",
            },
        }
    )

    fetched = {}

    def _fake_fetch(self, subject, version, group_id, base_url=None):
        fetched["subject"] = subject
        fetched["version"] = version
        fetched["group_id"] = group_id
        return {
            "type": "record",
            "name": "telemetry",
            "fields": [{"name": "sensor_tag", "type": "string"}],
        }

    monkeypatch.setattr(ConfigLoader, "_fetch_apicurio_schema", _fake_fetch)

    loader = ConfigLoader(base_path=".", config_data=config_data)
    loader.load_main_config()

    assert fetched["subject"] == "telemetry-value"
    assert fetched["version"] == "7"
    assert fetched["group_id"] == "default"
    assert loader.config["schema"]["_active_table_name"] == "telemetry_registry_table"


def test_local_avro_reads_writer_schema(tmp_path):
    fastavro = pytest.importorskip("fastavro")
    avro_schema = {
        "type": "record",
        "name": "telemetry_bin",
        "fields": [{"name": "sensor_tag", "type": "string"}],
    }
    avro_file = tmp_path / "telemetry.avro"
    with avro_file.open("wb") as handle:
        fastavro.writer(handle, avro_schema, [{"sensor_tag": "A"}])

    config_data = _base_config(
        {
            "source": "local_avro",
            "avro": {"path": str(avro_file)},
        }
    )

    loader = ConfigLoader(base_path=str(tmp_path), config_data=config_data)
    loader.load_main_config()

    schema = loader.config["schema"]
    table_name = schema["_active_table_name"]
    assert schema["tables"][table_name]["columns"]["sensor_tag"]["type"] == "string"


def test_local_avro_falls_back_to_json_schema_content(tmp_path):
    avro_schema = {
        "type": "record",
        "name": "telemetry_json_fallback",
        "fields": [
            {"name": "id", "type": "int"},
            {"name": "email", "type": ["null", "string"]},
        ],
    }
    avro_file = tmp_path / "telemetry_json.avro"
    avro_file.write_text(json.dumps(avro_schema), encoding="utf-8")

    config_data = _base_config(
        {
            "source": "local_avro",
            "avro": {"path": str(avro_file)},
        }
    )

    loader = ConfigLoader(base_path=str(tmp_path), config_data=config_data)
    loader.load_main_config()

    schema = loader.config["schema"]
    table_name = schema["_active_table_name"]
    assert schema["tables"][table_name]["columns"]["id"]["type"] == "integer"
    assert schema["tables"][table_name]["columns"]["email"]["type"] == "string"
    assert schema["tables"][table_name]["columns"]["email"]["nullable"] is True


def test_table_defaults_are_applied_but_table_specific_values_take_precedence():
    config_data = _base_config(
        {
            "source": "yaml",
            "table_defaults": {
                "load_mode": "drop_recreate",
                "allow_duplicate_timestamps": True,
                "record_count": 99,
            },
            "tables": {
                "Employees": {
                    "load_mode": "append",
                    "allow_duplicate_timestamps": False,
                    "record_count": 12,
                    "columns": {
                        "empID": {"type": "integer"},
                    },
                }
            },
        }
    )

    loader = ConfigLoader(base_path=".", config_data=config_data)
    loader.load_main_config()

    table = loader.config["schema"]["tables"]["Employees"]
    assert table["load_mode"] == "append"
    assert table["allow_duplicate_timestamps"] is False
    assert table["record_count"] == 12


def test_avro_x_metadata_is_mapped_to_generation_fields(tmp_path):
    avro_schema = {
        "type": "record",
        "name": "Employees",
        "x-record-count": 321,
        "fields": [
            {
                "name": "firstName",
                "type": "string",
                "x-semantic": "first_name",
            },
            {
                "name": "isActive",
                "type": "boolean",
                "x-true-probability": 0.91,
            },
            {
                "name": "departmentName",
                "type": {
                    "type": "enum",
                    "name": "DepartmentEnum",
                    "symbols": ["HR", "IT", "OPS"],
                },
                "x-values-probabilities": [0.1, 0.2, 0.7],
            },
            {
                "name": "salary",
                "type": "float",
                "x-min": 100.5,
                "x-max": 999.9,
            },
            {
                "name": "exitDate",
                "type": ["null", {"type": "int", "logicalType": "date"}],
                "default": None,
                "x-null-probability": 0.5,
                "x-min": "2024-01-01",
                "x-max": "2024-12-31",
            },
        ],
    }
    avsc_file = tmp_path / "employees.avsc"
    avsc_file.write_text(json.dumps(avro_schema), encoding="utf-8")

    config_data = _base_config(
        {
            "source": "local_avsc",
            "avro": {"path": str(avsc_file)},
        }
    )

    loader = ConfigLoader(base_path=str(tmp_path), config_data=config_data)
    loader.load_main_config()

    schema = loader.config["schema"]
    table = schema["tables"][schema["_active_table_name"]]
    columns = table["columns"]

    assert table["record_count"] == 321
    assert columns["firstName"]["semantic"] == "first_name"
    assert columns["isActive"]["true_probability"] == 0.91
    assert columns["departmentName"]["values_probabilities"] == [0.1, 0.2, 0.7]
    assert columns["salary"]["min"] == 100.5
    assert columns["salary"]["max"] == 999.9
    assert columns["exitDate"]["nullable"] is True
    assert columns["exitDate"]["null_probability"] == 0.5
    assert columns["exitDate"]["min"] == "2024-01-01"
    assert columns["exitDate"]["max"] == "2024-12-31"
