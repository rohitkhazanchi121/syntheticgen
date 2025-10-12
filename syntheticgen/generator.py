from datetime import datetime, timedelta
import random, os, pytz, re
import numpy as np
from typing import Dict, Optional
from dotenv import load_dotenv
from syntheticgen.config_loader import ConfigLoader
from syntheticgen.entity_normalizer import EntityNormalizer
from syntheticgen.timestamp_generator import TimestampGenerator
from syntheticgen.result_storage import ResultStorage
from pathlib import Path
import inspect

load_dotenv()


class SyntheticDataGenerator:
    def __init__(self, config_file: str = "config.yaml", base_path: str | None = None):
        frame = inspect.stack()[1]
        caller_file = frame.filename
        self.base_path = base_path if base_path else Path(caller_file).resolve().parent
        self.config_loader = ConfigLoader(self.base_path, config_file)
        self.config_loader.load_main_config()
        self.config_loader.load_entity_config()
        self.config = self.config_loader.config
        self.entity_config = self.config_loader.entity_config
        self._parse_time_range()
        self._parse_frequency()
        self._initialize_seed()
        self.entity = EntityNormalizer(self.entity_config, self.config).normalize()
        self._parse_schema_mapping()
        self.timestamp_generator = TimestampGenerator(self.default_frequency)
        self.result_storage = ResultStorage(self.config)

    def _parse_time_range(self):
        general_config = self.config.get("general", {})
        start_time_str = general_config.get("start_time")
        end_time_str = general_config.get("end_time")
        duration_hours = int(general_config.get("duration_hours", 1))
        start_time = (
            datetime.fromisoformat(start_time_str.replace("Z", "+00:00")).replace(microsecond=0)
            if start_time_str
            else None
        )
        end_time = (
            datetime.fromisoformat(end_time_str.replace("Z", "+00:00")).replace(microsecond=0) if end_time_str else None
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
            return
        self.field_mapping = schema_config.get("field_mapping", {})
        self.record_rate_field = schema_config.get("record_rate_field", None)
        self.range_field_mapping = schema_config.get("range_field_mapping", {})
        self.output_fields = schema_config.get("output_fields", [])

    def _extract_range_info(self):
        """Extract range field mapping info once."""
        range_info = {}
        for output_field, range_keys in self.range_field_mapping.items():
            range_info[output_field] = {"min": range_keys["min"], "max": range_keys["max"], "output": output_field}
        return range_info

    def _get_range_values(self, ent_, key, vals, ent_value):
        """Get min, max, and output column for range generation."""
        if not vals:
            return 0, 100, key

        # Get first range info (assuming single range field)
        info = vals
        min_field = info["min"]
        max_field = info["max"]
        output_column = info["output"]

        min_v = ent_.get(min_field)
        max_v = ent_.get(max_field)

        if min_v is None or max_v is None:
            min_v = self.config["rules"]["defaults"][min_field] or np.random.uniform(0, 100)
            max_v = self.config["rules"]["defaults"][max_field] or np.random.uniform(0, 100)

            if max_v < min_v:
                min_v, max_v = max_v, min_v

            print(
                f"Generating random min and max range value between (0,100) "
                f"for entity {ent_value} because of missing min or max range value"
            )

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

    def generate_records(self):
        records = []
        number_of_hours = ((self.end_time - self.start_time).total_seconds()) / (60 * 60)

        range_info = self._extract_range_info() if self.range_field_mapping else {}

        use_field_mapping = bool(self.field_mapping)
        filter_output = bool(self.output_fields)
        output_fields_set = set(self.output_fields) if filter_output else None

        columns = list(range_info.keys()) if range_info else []

        for hour in range(int(number_of_hours)):
            gen_start_time = self.start_time + timedelta(hours=hour)
            gen_end_time = gen_start_time + timedelta(hours=1)
            for ent_key, ent_info in self.entity.items():
                for ent_value, ent_details in ent_info.items():
                    ent_ = ent_details if isinstance(ent_details, dict) else {"value": ent_details}
                    records_per_hour = ent_.get(self.record_rate_field)
                    timestamps = self.timestamp_generator.generate(records_per_hour, gen_start_time, gen_end_time)
                    no_of_timestamps = len(timestamps)

                    if no_of_timestamps == 0:
                        continue

                    numeric_arrays = {
                        output_col: np.round(np.random.uniform(min_v, max_v, no_of_timestamps), 2).tolist()
                        for key, vals in range_info.items()
                        for min_v, max_v, output_col in [self._get_range_values(ent_, key, vals, ent_value)]
                    }

                    base_rec = self._build_base_record(ent_key, ent_value, ent_, use_field_mapping)

                    if numeric_arrays:
                        batch_records = [
                            {"timestamp": ts.isoformat(), **base_rec, **dict(zip(columns, val))}
                            for ts, *val in zip(timestamps, *numeric_arrays.values())
                        ]
                    else:
                        batch_records = [
                            {"timestamp": ts.isoformat(), **base_rec, **{col: None for col in columns}}
                            for ts in timestamps
                        ]

                    if filter_output:
                        batch_records = [
                            {
                                **{k: v for k, v in rec.items() if k in output_fields_set},
                                **{k: None for k in output_fields_set if k not in rec},
                            }
                            for rec in batch_records
                        ]

                    records.extend(batch_records)

        return records

    def store_results(self, records):
        return self.result_storage.store(records)
