import os, yaml
from pathlib import Path
from copy import deepcopy
from dotenv import load_dotenv

load_dotenv()


class ConfigLoader:
    def __init__(self, base_path, config_path):
        self.base_path = base_path
        self.config_path = Path(os.path.join(self.base_path, config_path))
        self.config = {}
        self.entity_config = {}

    def load_main_config(self):
        if self.config_path and self.config_path.is_file():
            try:
                with open(self.config_path, "r") as yaml_file:
                    self.config = yaml.safe_load(yaml_file)
            except yaml.YAMLError as e:
                raise ValueError(f"Error parsing config YAML file: {e}")
            
            required_keys = ["general", "output", "rules", "schema"]
            for key in required_keys:
                if key not in self.config:
                    raise ValueError(f"Missing required section '{key}' in config.yaml")
        else:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

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

    def load_entity_config(self):
        entity_config_path = self.config["rules"].get("entity_file")
        if not entity_config_path:
            raise ValueError("Tags configuration path not specified in main config.")
        filepath = self.config_path.parent if self.config_path else Path(".")
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
