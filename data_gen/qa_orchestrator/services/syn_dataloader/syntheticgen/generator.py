from datetime import datetime, timedelta
import random, os, pytz, re
import numpy as np
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from qa_orchestrator.services.syn_dataloader.syntheticgen.config_loader import ConfigLoader
from qa_orchestrator.services.syn_dataloader.syntheticgen.entity_normalizer import EntityNormalizer
from qa_orchestrator.services.syn_dataloader.syntheticgen.timestamp_generator import TimestampGenerator
from qa_orchestrator.services.syn_dataloader.syntheticgen.type_based_entity_generator import TypeBasedEntityGenerator
from qa_orchestrator.services.syn_dataloader.syntheticgen.default_configs import resolve_default_config
from qa_orchestrator.services.syn_dataloader.syntheticgen.logger import logger
from pathlib import Path
import inspect
from copy import deepcopy

load_dotenv()


class SyntheticDataGenerator:
    def __init__(
        self,
        config_file: str | None = 'config.yaml',
        base_path: str | None = None,
        overrides: Optional[Dict] = None,
        source_name: str | None = None,
        config_data: Optional[Dict[str, Any]] = None,
    ):
        
        frame = inspect.stack()[1]
        caller_file = frame.filename
        self.base_path = base_path if base_path else Path(caller_file).resolve().parent
        if config_data is None and config_file is None:
            config_file = str(resolve_default_config(source_name))
        self.config_loader = ConfigLoader(
            self.base_path,
            config_file,
            override_config=overrides,
            config_data=config_data,
        )
        self.config_loader.load_main_config()
        
        # Check if entity_file is provided
        if self.config_loader.is_entity_file_provided():
            # Load entity config from file (existing behavior)
            self.config_loader.load_entity_config()
            self.config = self.config_loader.config
            self.entity_config = self.config_loader.entity_config
            self.type_based_generator = None
            logger.info("Loading entity configuration from file")
        else:
            # Generate entity config based on column types (new behavior)
            self.config = self.config_loader.config
            self.entity_config = None  # Will be generated based on types
            self.type_based_generator = TypeBasedEntityGenerator()
            logger.info("Entity file not provided, will generate configuration based on column types")
        
        self._parse_time_range()
        self._parse_frequency()
        self._initialize_seed()
        self._parse_schema_mapping()
        
        # Generate or normalize entity configuration
        if self.entity_config is None:
            self.entity = None
        else:
            # File-based entity normalization (existing behavior)
            self.entity = EntityNormalizer(self.entity_config, self.config).normalize()
        
        self.timestamp_generator = TimestampGenerator(self.default_frequency)

        

    def _parse_time_range(self):
        general_config = self.config.get("general", {})
        start_time_str = general_config.get("start_time")
        end_time_str = general_config.get("end_time")
        raw_duration_hours = general_config.get("duration_hours", 1)
        try:
            duration_hours = int(raw_duration_hours) if raw_duration_hours is not None else 1
        except (TypeError, ValueError):
            duration_hours = 1
        start_time = (
            datetime.fromisoformat(start_time_str).replace(microsecond=0) if isinstance(start_time_str,str) else start_time_str
            if start_time_str
            else None
        )
        end_time = (
            datetime.fromisoformat(end_time_str).replace(microsecond=0) if isinstance(end_time_str,str) else end_time_str
            if end_time_str 
            else None
        )
        if not start_time and not end_time:
            end_time = datetime.now().replace(tzinfo=pytz.UTC)
            start_time = end_time - timedelta(hours=duration_hours)
        elif start_time and not end_time:
            end_time = start_time + timedelta(hours=duration_hours)
        elif end_time and not start_time:
            start_time = end_time - timedelta(hours=duration_hours)
        if start_time > end_time:
            raise ValueError(f"Invalid time range: start_time={start_time}, end_time={end_time}")
        self.start_time = start_time
        self.end_time = end_time

    def _apply_overrides(self, base, overrides):
        
        result = deepcopy(base)

        for section, params in overrides.items():
            if section in result and isinstance(result[section], dict) and isinstance(params, dict):
                result[section] = self._apply_overrides(result[section], params)
            else:
                result[section] = deepcopy(params)
        

        return result

    def _parse_frequency(self):
        general_config = self.config.get("general", {})
        frequency_str = general_config.get("default_frequency", "1min")
        match = re.match(r"(\d+)([a-zA-Z]+)", frequency_str.strip())
        if not match:
            raise ValueError(f"Invalid frequency format: {frequency_str}")
        value, unit = int(match.group(1)), match.group(2).lower()
        if unit in ["min", "minutes", "minute", "m", "mins"]:
            delta = timedelta(minutes=value)
        elif unit in ["hour", "hours", "h", "hr", "hrs"]:
            delta = timedelta(hours=value)
        elif unit in ["second", "seconds", "sec", "s"]:
            delta = timedelta(seconds=value)
        else:
            raise ValueError(f"Unsupported frequency unit: {unit}")
        self.default_frequency = delta

    def _initialize_seed(self):
        seed = self.config.get("general", {}).get("seed")
        if seed is not None:
            self.seed = seed
            random.seed(seed)
            np.random.seed(seed)
        else:
            self.seed = None

    def _parse_schema_mapping(self):
        schema_config = self.config.get("schema", {})
        if not schema_config:
            self.field_mapping = {}
            self.record_rate_field = None
            self.range_field_mapping = {}
            self.output_fields = None
            self.column_configs = {}
            self.active_table = {}
            self.allow_duplicate_timestamps = False
            return
        self.active_table = schema_config.get("_active_table", {})
        self.column_configs = self.active_table.get("columns", {}) if isinstance(self.active_table, dict) else {}
        self.field_mapping = schema_config.get("field_mapping", {})
        self.record_rate_field = schema_config.get("record_rate_field", None)
        self.range_field_mapping = schema_config.get("range_field_mapping", {})
        self.allow_duplicate_timestamps = bool(
            self.active_table.get("allow_duplicate_timestamps")
            if isinstance(self.active_table, dict)
            else schema_config.get("allow_duplicate_timestamps", False)
        )
        if self.column_configs:
            self.output_fields = list(self.column_configs.keys())
        else:
            self.output_fields = schema_config.get("output_fields", [])

    def _generate_type_based_entities(self) -> dict:
        """
        Generate a single type-based sample record.
        Kept as a compatibility helper for callers that inspect generated defaults.
        
        Returns:
            dict: Sample record with values generated from configured column types
        """
        if not self.output_fields:
            raise ValueError("output_fields must be defined in schema configuration for type-based generation")

        return self.type_based_generator.generate_record(
            self.output_fields,
            self.config.get("schema", {}),
            self.config,
            column_configs=self.column_configs,
        )

    def _extract_range_info(self):
        """Extract range field mapping info once."""
        range_info = {}
        for output_field, range_keys in self.range_field_mapping.items():
            range_info[output_field] = {
                'min': range_keys["min"],
                'max': range_keys["max"],
                'output': output_field
            }
        return range_info


    def _get_range_values(self, ent_, key, vals , ent_value):
        """Get min, max, and output column for range generation."""
        if not vals:
            return 0, 100, key
        
        # Get first range info (assuming single range field)
        info = vals
        min_field = info['min']
        max_field = info['max']
        output_column = info['output']
        
        min_v = ent_.get(min_field)
        max_v = ent_.get(max_field)
        
        if min_v is None or max_v is None:
            defaults = self.config.get('rules', {}).get('defaults', {})
            if min_field in defaults:
                min_v = defaults[min_field]
            else:
                min_v = None
            if max_field in defaults:
            
                max_v = defaults[max_field] 
            else:
                max_v = None
            
            if max_v and min_v:
                if max_v < min_v:
                    min_v, max_v = max_v, min_v
                
                logger.info(f"Generating random min and max range value between (0,100) "
                    f"for entity {ent_value} because of missing min or max range value")
            
        return min_v, max_v, output_column


    def _build_base_record(self, ent_key, ent_value, ent_, use_field_mapping):
        """Build the base record dictionary once per entity."""
        if use_field_mapping:
            rec = {self.field_mapping[ent_key]: ent_value}
            for ent_field, output_field in self.field_mapping.items():
                if ent_field in ent_:
                    rec[output_field] = ent_[ent_field]
        else:
            rec = {ent_key: ent_value, **ent_}
        
        return rec

    def _prepare_generation_params(self):
        """Prepare common parameters needed for record generation."""
        number_of_hours = int(((self.end_time - self.start_time).total_seconds()) / (60 * 60))
        range_info = self._extract_range_info() if self.range_field_mapping else {}
        use_field_mapping = bool(self.field_mapping)
        filter_output = bool(self.output_fields)
        output_fields_set = set(self.output_fields) if filter_output else None
        columns = list(range_info.keys()) if range_info else []
        return number_of_hours, range_info, use_field_mapping, filter_output, output_fields_set, columns

    def _generate_numeric_arrays(self, ent_, range_info, no_of_timestamps, ent_value):
        """Generate numeric arrays for range fields."""
        return {
            output_col: np.round(np.random.uniform(min_v, max_v, no_of_timestamps), 2).tolist() if (min_v is not None) and (max_v is not None) else None
            for key, vals in range_info.items()
            for min_v, max_v, output_col in [self._get_range_values(ent_, key, vals, ent_value)]
        }

    def _create_batch_records(self, timestamps, base_rec, numeric_arrays, columns):
        """Create batch records with or without numeric arrays."""
        if 'timestamp' in self.field_mapping:
            timestamp_column = self.field_mapping['timestamp']
        else:
            timestamp_column = 'timestamp'
        if numeric_arrays:
            # Filter out None values for zipping
            valid_arrays = {k: v for k, v in numeric_arrays.items() if v is not None}
            columns = list(valid_arrays.keys())
            
            # Keys with None values
            none_keys = {k for k, v in numeric_arrays.items() if v is None}
            return [
                {
                    timestamp_column: ts.isoformat(),
                    **base_rec,
                    **dict(zip(columns, val)),
                    **{k: None for k in none_keys}
                }   
                for ts, *val in zip(timestamps, *valid_arrays.values())
            ]
        return [
            {
                'timestamp': ts.isoformat(), 
                **base_rec,
                **{col: None for col in columns}
            }
            for ts in timestamps
        ]

    def _filter_output_fields(self, batch_records, output_fields_set):
        """Filter records to include only specified output fields."""
        return [
            {
                **{k: v for k, v in rec.items() if k in output_fields_set},
                **{k: None for k in output_fields_set if k not in rec}
            }
            for rec in batch_records
        ]
    
    def _safe_eval_formula(self, formula, record):
        """Evaluate formula, return None if any required field is None"""
        try:
            # Extract variable names from the formula (simple approach)
            import re
            variables = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', formula)
            
            # Check if any variable in the formula is None
            if any(record.get(var) is None for var in variables):
                return None
            
            return eval(formula, {"__builtins__": {}}, record)
        except (KeyError, TypeError, ZeroDivisionError):
            return None
    
    def _add_calculated_field(self, calc_field, records):

        
        return [
            { **record,
            field: self._safe_eval_formula(formula, record)

            }
        for record in records
        for field, formula in calc_field.items()
        ]

    def _generate_type_based_records(self):
        if not self.output_fields:
            raise ValueError("output_fields must be defined in schema configuration for type-based generation")

        records = []
        number_of_hours = max(1, int(((self.end_time - self.start_time).total_seconds()) / (60 * 60)))
        configured_record_count = self._resolve_configured_record_count()
        schema_config = self.config.get("schema", {})
        output_fields_set = set(self.output_fields)

        for hour in range(number_of_hours):
            gen_start_time = self.start_time + timedelta(hours=hour)
            gen_end_time = gen_start_time + timedelta(minutes=59)
            if configured_record_count is not None:
                record_count = configured_record_count
            else:
                record_count = self.timestamp_generator.available_count(gen_start_time, gen_end_time)
            timestamps = self.timestamp_generator.generate(
                record_count,
                gen_start_time,
                gen_end_time,
                allow_duplicates=self.allow_duplicate_timestamps,
            )

            batch_records = [
                self.type_based_generator.generate_record(
                    self.output_fields,
                    schema_config,
                    self.config,
                    timestamp,
                    self.column_configs,
                )
                for timestamp in timestamps
            ]

            calc_field = self.config.get('rules', {}).get('calculated_field')
            if calc_field:
                batch_records = self._add_calculated_field(calc_field, batch_records)

            batch_records = self._filter_output_fields(batch_records, output_fields_set)
            records.extend(batch_records)

        return self.config, records

    def _resolve_configured_record_count(self) -> int | None:
        if isinstance(self.active_table, dict) and "record_count" in self.active_table:
            table_record_count = self.active_table.get("record_count")
            if table_record_count is not None:
                return int(table_record_count)

        # For table-based schema, record count should come from table definition.
        # If missing, fallback is computed from time window and frequency.
        if isinstance(self.config.get("schema", {}).get("tables"), dict):
            return None

        defaults = self.config.get("rules", {}).get("defaults", {})
        if self.record_rate_field and self.record_rate_field in defaults:
            defaults_record_count = defaults.get(self.record_rate_field)
            if defaults_record_count is not None:
                return int(defaults_record_count)

        return None

    def generate_records(self):
        if self.entity is None:
            return self._generate_type_based_records()

        records = []
        params = self._prepare_generation_params()
        number_of_hours, range_info, use_field_mapping, filter_output, output_fields_set, columns = params
        
        for hour in range(number_of_hours):
            gen_start_time = self.start_time + timedelta(hours=hour)
            gen_end_time = gen_start_time + timedelta(minutes=59)
            
            for ent_key, ent_info in self.entity.items():
                for ent_value, ent_details in ent_info.items():
                    ent_ = ent_details if isinstance(ent_details, dict) else {"value": ent_details}
                    records_per_hour = ent_.get(self.record_rate_field)
                    timestamps = self.timestamp_generator.generate(
                        records_per_hour,
                        gen_start_time,
                        gen_end_time,
                        allow_duplicates=self.allow_duplicate_timestamps,
                    )
                    
                    if not timestamps:
                        continue

                    numeric_arrays = self._generate_numeric_arrays(ent_, range_info, len(timestamps), ent_value)
                    base_rec = self._build_base_record(ent_key, ent_value, ent_, use_field_mapping)
                    batch_records = self._create_batch_records(timestamps, base_rec, numeric_arrays, columns)
                    calc_field = self.config.get('rules', {}).get('calculated_field')
                    if calc_field:
                        batch_records = self._add_calculated_field(calc_field, batch_records)
                    
                    if filter_output:
                        batch_records = self._filter_output_fields(batch_records, output_fields_set)

                    records.extend(batch_records)

        
            
        return self.config, records
