from qa_orchestrator.services.syn_dataloader.syntheticgen.generator import SyntheticDataGenerator

import os
import yaml
from copy import deepcopy
from typing import Any
from qa_orchestrator.services.syn_dataloader.syntheticgen.logger import logger
from qa_orchestrator.services.syn_dataloader.syntheticgen.result_storage import ResultStorage
from qa_orchestrator.services.syn_dataloader.syntheticgen.default_configs import resolve_default_config
import asyncio
DEFAULT_SOURCE_NAME = "synthetic"
SOURCE_DETAIL_KEYS = {"config", "config_file", "overrides"}


def load_config_file(config_file_path):
    """
    Load YAML configuration file.
    
    Args:
        config_file_path (str): Path to the YAML configuration file
        
    Returns:
        dict: Parsed YAML configuration
        
    Raises:
        FileNotFoundError: If config file does not exist
        yaml.YAMLError: If YAML parsing fails
    """
    try:
        with open(config_file_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_file_path}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing configuration file {config_file_path}: {e}")
        raise


async def run_synthetic(data_sources_config=None):
    """
    Generic synthetic data generation orchestrator.
    
    Generates synthetic data for multiple configured data sources and optionally refreshes pivots.
    
    Args:
        data_sources_config (dict): Optional configuration defining sources to process.
            Supported formats:
            - None: run one generic synthetic source with default config.
            - {"overrides": {...}}: run one generic source with overrides.
            - {"xyz": {"overrides": {...}}}: run flat source map without a site.
            - {"qb": {"historian": {...}, "eot": {...}}}: legacy site-scoped map.
    
    Returns:
        None
        
    Raises:
        KeyError: If required configuration keys are missing
        FileNotFoundError: If config files cannot be found
    """
    source_config = normalize_data_sources_config(data_sources_config)
    logger.info(f"Starting synthetic data generation for sources: {', '.join(source_config)}")
    
    for source_name, source_details in source_config.items():
        logger.info(f"Processing data source: {source_name}")

        try:
            config_file, resolved_config, overrides = resolve_source_config(source_name, source_details)
        except Exception as e:
            logger.error(f"Failed to resolve config for {source_name}: {e}")
            continue

        logger.info(
            f"Generating synthetic data for {source_name}: "
            f"{resolved_config['general'].get('start_time')} to {resolved_config['general'].get('end_time')}"
        )
        
        try:
            generator = SyntheticDataGenerator(
                config_file=config_file,
                config_data=resolved_config,
                overrides=None,
                source_name=source_name,
            )
            config, generated_data = generator.generate_records()

            result_storage = ResultStorage(config)

            sink = str(config.get("output", {}).get("sink") or "").lower()
            if sink == "db":
                result_storage.store(generated_data)
            else:
                logger.info(f"No database sink configured for {source_name}, skipping storage and pivot")
                
        except Exception as e:
            logger.error(f"Error processing {source_name}: {e}")
            continue

def merge_config_overrides(base_config, overrides):
    """
    Recursively merge override configuration into base configuration.
    
    Args:
        base_config (dict): Base configuration to be updated
        overrides (dict): Override values to merge in
        
    Returns:
        None (modifies base_config in place)
    """
    for key, value in overrides.items():
        if isinstance(value, dict) and key in base_config and isinstance(base_config[key], dict):
            merge_config_overrides(base_config[key], value)
        else:
            base_config[key] = value

def is_source_details_config(config: dict[str, Any]) -> bool:
    return any(key in config for key in SOURCE_DETAIL_KEYS)

def is_site_scoped_config(config: dict[str, Any]) -> bool:
    return any(
        isinstance(site_sources, dict)
        and bool(site_sources)
        and not is_source_details_config(site_sources)
        and all(isinstance(source_details, dict) for source_details in site_sources.values())
        for site_sources in config.values()
    )

def normalize_data_sources_config(data_sources_config=None) -> dict[str, dict[str, Any]]:
    """
    Normalize supported run_synthetic inputs to a flat source map.

    Supported inputs:
      - None -> {"synthetic": {}}
      - {"overrides": {...}} -> {"synthetic": {"overrides": {...}}}
      - {"xyz": {...}} -> flat source map
      - {"qb": {"historian": {...}, "eot": {...}}} -> legacy site-scoped map
    """
    if data_sources_config is None:
        return {DEFAULT_SOURCE_NAME: {}}

    if not isinstance(data_sources_config, dict):
        raise ValueError("data_sources_config must be a dictionary when provided")

    if is_source_details_config(data_sources_config):
        return {DEFAULT_SOURCE_NAME: data_sources_config}

    if is_site_scoped_config(data_sources_config):
        site = os.environ.get("SITE", "qb").lower()
        if site not in data_sources_config:
            logger.error(f"Site '{site}' not found in data_sources_config")
            raise KeyError(f"Site '{site}' not configured in data_sources_config")
        return data_sources_config[site]

    return data_sources_config

def resolve_source_config(source_name: str, source_details: dict[str, Any] | None):
    """
    Resolve source config from inline config, file config, or default fallback.

    Precedence:
      1) inline config (source_details["config"])
      2) config file (source_details["config_file"])
      3) source/default fallback config file
    """
    source_details = source_details or {}
    overrides = source_details.get("overrides", {})
    inline_config = source_details.get("config")
    config_file = source_details.get("config_file")

    if inline_config is not None:
        if not isinstance(inline_config, dict):
            raise ValueError(f"'config' for source '{source_name}' must be a dictionary")
        config_data = deepcopy(inline_config)
        merge_config_overrides(config_data, overrides)
        return None, config_data, overrides

    if not config_file:
        config_file = str(resolve_default_config(source_name))
        logger.info(f"No config_file specified for {source_name}; using default config {config_file}")

    base_config = load_config_file(config_file)
    merge_config_overrides(base_config, overrides)
    return config_file, base_config, overrides


if __name__ == '__main__':


    asyncio.run(run_synthetic())