from qa_orchestrator.services.syn_dataloader.syntheticgen.type_based_entity_generator import (
    TypeBasedEntityGenerator,
)
from qa_orchestrator.services.syn_dataloader.syntheticgen.config_loader import ConfigLoader
import uuid
from datetime import datetime


def test_case_insensitive_field_default_list_is_used_for_string_type():
    generator = TypeBasedEntityGenerator()
    config = {
        "rules": {
            "defaults": {
                "id": ["tag1", "tag2", "tag3"],
            }
        }
    }

    value = generator.generate_value("Id", "string", config)

    assert value in config["rules"]["defaults"]["id"]


def test_string_values_default_list_is_used_for_string_fields():
    generator = TypeBasedEntityGenerator()
    config = {
        "rules": {
            "defaults": {
                "string_values": ["alpha", "beta", "gamma"],
            }
        }
    }

    value = generator.generate_value("facility_name", "string", config)

    assert value in config["rules"]["defaults"]["string_values"]


def test_field_default_takes_precedence_over_string_values():
    generator = TypeBasedEntityGenerator()
    config = {
        "rules": {
            "defaults": {
                "id": ["id_a", "id_b"],
                "string_values": ["fallback_a", "fallback_b"],
            }
        }
    }

    value = generator.generate_value("id", "string", config)

    assert value in config["rules"]["defaults"]["id"]


def test_values_probabilities_are_used_when_provided():
    generator = TypeBasedEntityGenerator()
    config = {"rules": {"defaults": {}}}

    value = generator.generate_value(
        "departmentName",
        "string",
        config,
        column_config={
            "values": ["HR", "IT"],
            "values_probabilities": [1.0, 0.0],
        },
    )

    assert value == "HR"


def test_true_probability_controls_boolean_generation():
    generator = TypeBasedEntityGenerator()
    config = {"rules": {"defaults": {}}}

    always_true = generator.generate_value(
        "isActive",
        "boolean",
        config,
        column_config={"true_probability": 1.0},
    )
    always_false = generator.generate_value(
        "isActive",
        "boolean",
        config,
        column_config={"true_probability": 0.0},
    )

    assert always_true is True
    assert always_false is False


def test_null_probability_returns_none_when_nullable():
    generator = TypeBasedEntityGenerator()
    config = {"rules": {"defaults": {}}}

    value = generator.generate_value(
        "leavingDate",
        "date",
        config,
        column_config={"nullable": True, "null_probability": 1.0},
    )

    assert value is None


def test_null_probability_ignored_when_not_nullable():
    generator = TypeBasedEntityGenerator()
    config = {"rules": {"defaults": {}}}

    value = generator.generate_value(
        "joiningDate",
        "date",
        config,
        column_config={"nullable": False, "null_probability": 1.0},
    )

    assert value is not None


def test_config_loader_normalizes_table_schema_to_legacy_keys():
    config_data = {
        "general": {"duration_hours": 1, "default_frequency": "1sec"},
        "output": {"sink": "db", "db_config": {"type": "postgresql"}, "file_config": {"format": "json", "path": "output.json"}},
        "rules": {"entity_file": None, "calculated_field": None, "defaults": {"record_count": 10}},
        "schema": {
            "tables": {
                "Employees": {
                    "record_count": 100,
                    "columns": {
                        "empID": {"type": "integer"},
                        "isActive": {"type": "boolean", "true_probability": 0.7},
                    },
                }
            }
        },
    }

    loader = ConfigLoader(base_path=".", config_data=config_data)
    loader.load_main_config()

    schema = loader.config["schema"]
    assert schema["_active_table_name"] == "Employees"
    assert schema["output_fields"] == ["empID", "isActive"]
    assert schema["output_column_types"]["empID"] == "integer"
    assert loader.config["output"].get("table_name") is None


def test_table_column_definition_ignores_rules_defaults_for_numeric_range():
    generator = TypeBasedEntityGenerator()
    config = {
        "rules": {
            "defaults": {
                "min_value": 1,
                "max_value": 2,
            }
        },
        "schema": {
            "tables": {
                "Employees": {
                    "columns": {
                        "empID": {
                            "type": "integer",
                            "min": 25,
                            "max": 2000,
                        }
                    }
                }
            }
        },
    }

    record = generator.generate_record(
        output_fields=["empID"],
        schema=config["schema"],
        config=config,
        column_configs=config["schema"]["tables"]["Employees"]["columns"],
    )

    assert 25 <= record["empID"] <= 2000


def test_uuid_type_generates_valid_uuid_values():
    generator = TypeBasedEntityGenerator()
    config = {
        "rules": {"defaults": {}},
        "schema": {
            "tables": {
                "Employees": {
                    "columns": {
                        "reading_id": {
                            "type": "uuid",
                            "nullable": False,
                        }
                    }
                }
            }
        },
    }

    record = generator.generate_record(
        output_fields=["reading_id"],
        schema=config["schema"],
        config=config,
        column_configs=config["schema"]["tables"]["Employees"]["columns"],
    )

    generated_id = record["reading_id"]
    assert isinstance(generated_id, str)
    assert str(uuid.UUID(generated_id)) == generated_id


def test_smallint_and_tiny_int_generate_integer_values_in_range():
    generator = TypeBasedEntityGenerator()
    config = {"rules": {"defaults": {}}}

    smallint_value = generator.generate_value(
        "signal_quality",
        "smallint",
        config,
        column_config={"min": 0, "max": 100},
        use_rule_defaults=False,
    )
    tiny_int_value = generator.generate_value(
        "alarm_priority",
        "tiny int",
        config,
        column_config={"min": 0, "max": 4},
        use_rule_defaults=False,
    )

    assert isinstance(smallint_value, int)
    assert isinstance(tiny_int_value, int)
    assert 0 <= smallint_value <= 100
    assert 0 <= tiny_int_value <= 4


def test_semantic_email_generates_email_when_faker_available():
    generator = TypeBasedEntityGenerator()
    config = {"rules": {"defaults": {}}}

    value = generator.generate_value(
        "email",
        "string",
        config,
        column_config={"semantic": "email"},
        use_rule_defaults=False,
    )

    if generator.faker:
        assert isinstance(value, str)
        assert "@" in value
    else:
        assert isinstance(value, str)


def test_datetime_uses_column_min_max_range_when_provided():
    generator = TypeBasedEntityGenerator()
    config = {
        "general": {
            "start_time": "2018-01-01T00:00:00",
            "end_time": "2018-12-31T23:59:59",
        },
        "rules": {"defaults": {}},
    }

    value = generator.generate_value(
        "joiningDate",
        "date",
        config,
        column_config={
            "min": "2024-01-01",
            "max": "2024-12-31",
        },
        use_rule_defaults=False,
    )

    assert isinstance(value, datetime)
    assert datetime(2024, 1, 1) <= value <= datetime(2024, 12, 31, 23, 59, 59)
