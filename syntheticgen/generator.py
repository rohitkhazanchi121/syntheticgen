from datetime import datetime, timedelta
import random, os, pytz, re
import numpy as np
from typing import Dict, Optional
from dotenv import load_dotenv
from syntheticgen.config_loader import ConfigLoader
from syntheticgen.entity_normalizer import EntityNormalizer
from syntheticgen.timestamp_generator import TimestampGenerator
from syntheticgen.result_storage import ResultStorage

load_dotenv()


class SyntheticDataGenerator:
    def __init__(self, overrides: Optional[Dict] = None):
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.config_loader = ConfigLoader(self.base_path)
        self.config_loader.load_main_config()
        if overrides:
            self.config_loader.apply_overrides(overrides)
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

    def generate_records(self):
        records = []
        number_of_hours = ((self.end_time - self.start_time).total_seconds()) / (60 * 60)
        for hour in range(int(number_of_hours)):
            gen_start_time = self.start_time + timedelta(hours=hour)
            gen_end_time = self.start_time + timedelta(hours=hour + 1)
            for ent_key, ent_info in self.entity["entity"].items():
                for ent_value, ent_details in ent_info.items():
                    ent_info1 = ent_details if isinstance(ent_details, dict) else {"value": ent_details}
                    records_per_hour = ent_info1.get(self.record_rate_field)
                    timestamps = self.timestamp_generator.generate(records_per_hour, gen_start_time, gen_end_time)
                    for ts in timestamps:
                        rec = {}
                        if self.field_mapping:
                            rec[self.field_mapping[ent_key]] = ent_value
                            for ent_field, output_field in self.field_mapping.items():
                                if ent_field in ent_info1:
                                    rec[output_field] = ent_info1[ent_field]
                        else:
                            rec[ent_key] = ent_value
                            rec.update(ent_info1)
                        if self.range_field_mapping:
                            for output_field, range_keys in self.range_field_mapping.items():
                                min_v = ent_info1.get(range_keys["min"], 0)
                                max_v = ent_info1.get(range_keys["max"], 100)
                                rec[output_field] = round(random.uniform(min_v, max_v), 2)
                        rec["timestamp"] = ts.isoformat()
                        if self.output_fields:
                            records.append({k: rec.get(k) for k in self.output_fields})
                        else:
                            records.append(rec)
        return records

    def store_results(self, records):
        return self.result_storage.store(records)
