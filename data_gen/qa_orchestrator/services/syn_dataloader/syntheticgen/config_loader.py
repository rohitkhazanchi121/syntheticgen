import os
import yaml
from pathlib import Path
from copy import deepcopy
from dotenv import load_dotenv
from qa_orchestrator.services.syn_dataloader.syntheticgen.schema_registry import fetch_apicurio_schema
from qa_orchestrator.services.syn_dataloader.syntheticgen.avro_schema import AvroSchemaProcessor

load_dotenv()


class ConfigLoader:
    def __init__(self, base_path, config_path=None, override_config=None, config_data=None):
        self.base_path = base_path
        self.config_path = Path(os.path.join(self.base_path, config_path)) if config_path else None
        self.config = {}
        self.entity_config = {}
        self.override = override_config
        self.config_data = deepcopy(config_data) if isinstance(config_data, dict) else None

    def load_main_config(self):
        if self.config_data is not None:
            self.config = deepcopy(self.config_data)
        elif self.config_path and self.config_path.is_file():
            try:
                with open(self.config_path, "r") as yaml_file:
                    self.config = yaml.safe_load(yaml_file)
            except yaml.YAMLError as e:
                raise ValueError(f"Error parsing config YAML file: {e}")
        else:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        required_keys = ["general", "output", "rules", "schema"]
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"Missing required section '{key}' in config.yaml")
        
        if self.config and self.override:
            self.apply_overrides(self.override)

        self.normalize_schema_source()
        self.normalize_schema()

    def normalize_schema_source(self):
        """Normalize schema source definitions into table-based schema config."""
        schema = self.config.setdefault("schema", {})
        source = str(schema.get("source", "yaml")).strip().lower()

        if source in {"", "yaml"}:
            self._normalize_yaml_source(schema)
            return

        if source in {"local_avsc", "local_avro"}:
            avro_config = schema.get("avro", {})
            if not isinstance(avro_config, dict):
                raise ValueError("schema.avro must be an object when schema.source is local_avsc/local_avro")

            schema_path = avro_config.get("path")
            if not isinstance(schema_path, str) or not schema_path.strip():
                raise ValueError("schema.avro.path is required when schema.source is local_avsc/local_avro")

            resolved_path = self._resolve_path(schema_path)
            avro_schema = AvroSchemaProcessor.read_local_schema(resolved_path, source)
            table_name = avro_config.get("table_name")
            self._set_tables_from_avro_schema(avro_schema, table_name=table_name)
            return

        if source == "apicurio_registry":
            registry_config = schema.get("registry", {})
            if not isinstance(registry_config, dict):
                raise ValueError("schema.registry must be an object when schema.source is apicurio_registry")

            subject = registry_config.get("subject")
            version = registry_config.get("version")
            if not isinstance(subject, str) or not subject.strip():
                raise ValueError("schema.registry.subject is required when schema.source is apicurio_registry")
            if version is None or str(version).strip() == "":
                raise ValueError("schema.registry.version is required when schema.source is apicurio_registry")

            avro_schema = self._fetch_apicurio_schema(
                subject=subject.strip(),
                version=str(version).strip(),
                group_id=str(registry_config.get("group_id", "default")).strip() or "default",
                base_url=registry_config.get("url"),
            )
            table_name = registry_config.get("table_name")
            self._set_tables_from_avro_schema(avro_schema, table_name=table_name)
            return

        raise ValueError(
            f"Unsupported schema.source '{source}'. Supported values: yaml, local_avsc, local_avro, apicurio_registry"
        )

    def _normalize_yaml_source(self, schema: dict):
        columns = schema.get("columns")
        if isinstance(columns, list) and columns and "output_fields" not in schema and "tables" not in schema:
            schema["output_fields"] = [str(column) for column in columns if str(column).strip()]

    def _resolve_path(self, configured_path: str) -> Path:
        config_file_dir = self.config_path.parent if self.config_path else Path(self.base_path)
        path = Path(configured_path)
        if path.is_absolute():
            return path
        return (config_file_dir / path).resolve()

    def _fetch_apicurio_schema(self, subject: str, version: str, group_id: str, base_url=None) -> dict:
        return fetch_apicurio_schema(
            subject=subject,
            version=version,
            group_id=group_id,
            base_url=base_url,
        )

    def _resolve_table_defaults(self) -> dict:
        schema_block = self.config.setdefault("schema", {})
        configured_defaults = schema_block.get("table_defaults")
        table_defaults = configured_defaults if isinstance(configured_defaults, dict) else {}
        rules_defaults = self.config.get("rules", {}).get("defaults", {})

        defaults = {
            "record_count": table_defaults.get(
                "record_count",
                schema_block.get("record_count", rules_defaults.get("record_count", 60)),
            ),
            "allow_duplicate_timestamps": table_defaults.get(
                "allow_duplicate_timestamps",
                schema_block.get("allow_duplicate_timestamps", False),
            ),
        }

        load_mode = table_defaults.get("load_mode", schema_block.get("load_mode"))
        if load_mode is not None:
            defaults["load_mode"] = load_mode

        return defaults

    def _apply_table_defaults(self, table_config: dict | None) -> dict:
        merged = dict(self._resolve_table_defaults())
        if isinstance(table_config, dict):
            merged.update(table_config)
        return merged

    def _set_tables_from_avro_schema(self, avro_schema: dict, table_name=None):
        schema_block = self.config.setdefault("schema", {})
        output = self.config.setdefault("output", {})
        db_config = output.setdefault("db_config", {})
        table, raw_table_config = AvroSchemaProcessor.map_schema_to_table_config(
            avro_schema=avro_schema,
            table_name=table_name,
            output_table_name=output.get("table_name"),
            db_table_name=db_config.get("table_name"),
        )

        table_config = self._apply_table_defaults(raw_table_config)
        schema_block["tables"] = {str(table): table_config}

    def normalize_schema(self):
        """Normalize schema to support both legacy and table-based formats.

        This keeps current behavior intact while allowing a richer `schema.tables`
        input model for type-based generation.
        """
        schema = self.config.setdefault("schema", {})
        output = self.config.setdefault("output", {})
        db_config = output.setdefault("db_config", {})
        tables = schema.get("tables")

        if isinstance(tables, dict) and tables:
            normalized_tables = {}
            for table_name, table_config in tables.items():
                normalized_tables[table_name] = self._apply_table_defaults(table_config)
            schema["tables"] = normalized_tables
            tables = normalized_tables

            configured_table_name = output.get("table_name") or db_config.get("table_name")
            if configured_table_name in tables:
                active_table_name = configured_table_name
            else:
                active_table_name = next(iter(tables))

            active_table = tables.get(active_table_name, {})
            columns = active_table.get("columns", {}) if isinstance(active_table, dict) else {}

            if "output_fields" not in schema and isinstance(columns, dict):
                schema["output_fields"] = list(columns.keys())

            if "output_column_types" not in schema and isinstance(columns, dict):
                schema["output_column_types"] = {
                    col_name: col_details.get("type", "string")
                    for col_name, col_details in columns.items()
                    if isinstance(col_details, dict)
                }

            schema.setdefault("record_rate_field", "record_count")
            schema.setdefault("range_field_mapping", {})
            schema["_active_table_name"] = active_table_name
            schema["_active_table"] = active_table
            return

        output_fields = schema.get("output_fields", [])
        if not isinstance(output_fields, list) or not output_fields:
            return

        output_column_types = schema.get("output_column_types", {})
        table_name = output.get("table_name") or db_config.get("table_name", "synthetic_default")

        schema["tables"] = {
            table_name: self._apply_table_defaults(
                {
                    "record_count": self.config.get("rules", {}).get("defaults", {}).get(
                        schema.get("record_rate_field", "record_count"),
                        60,
                    ),
                    "columns": {
                        field_name: {"type": output_column_types.get(field_name, "string")}
                        for field_name in output_fields
                    },
                }
            )
        }
        schema["_active_table_name"] = table_name
        schema["_active_table"] = schema["tables"][table_name]

    def apply_overrides(self, overrides):
        def _apply(base, overrides):
            result = deepcopy(base)
            for section, params in overrides.items():
                if section in result and isinstance(result[section], dict) and isinstance(params, dict):
                    result[section] = _apply(result[section], params)
                else:
                    result[section] = deepcopy(params)
            return result

        self.config = _apply(self.config, overrides)

    def is_entity_file_provided(self) -> bool:
        """
        Check if entity_file is provided and valid in configuration.
        
        Returns:
            bool: True if entity_file is specified and not empty/None, False otherwise
        """
        entity_file = self.config.get("rules", {}).get("entity_file")
        return entity_file is not None and (isinstance(entity_file, str) and entity_file.strip() != "")
    
    def load_entity_config(self):
        entity_config_path = self.config["rules"].get("entity_file")
        if not entity_config_path:
            raise ValueError("Tags configuration path not specified in main config.")
        filepath = self.config_path.parent if self.config_path else Path(self.base_path)
        entity_config_path = (
            filepath / entity_config_path if not Path(entity_config_path).is_absolute() else Path(entity_config_path)
        )
        entity_file = Path(entity_config_path)
        if not entity_file.is_file():
            raise FileNotFoundError(f"entity configuration file not found: {entity_config_path}")
        
        try:
            with open(entity_file, "r") as yaml_file:
                self.entity_config = yaml.safe_load(yaml_file)
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing entity configuration YAML file: {e}")
