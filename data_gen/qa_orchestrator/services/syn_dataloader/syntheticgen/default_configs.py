from pathlib import Path


DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent / "default_configs"
GENERIC_DEFAULT_CONFIG = DEFAULT_CONFIG_DIR / "generic_config.yaml"

DEFAULT_CONFIG_BY_SOURCE = {
    "historian": DEFAULT_CONFIG_DIR / "historian_config.yaml",
    "capstone": DEFAULT_CONFIG_DIR / "historian_config.yaml",
    "pi": DEFAULT_CONFIG_DIR / "historian_config.yaml",
    "eot": DEFAULT_CONFIG_DIR / "eot_config.yaml",
}


def resolve_default_config(source_name: str | None) -> Path:
    if not source_name:
        return GENERIC_DEFAULT_CONFIG

    config_path = DEFAULT_CONFIG_BY_SOURCE.get(source_name.lower())
    if not config_path or not config_path.is_file():
        return GENERIC_DEFAULT_CONFIG

    return config_path
