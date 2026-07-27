from datetime import timedelta
import random
import pandas as pd


class TimestampGenerator:
    def __init__(self, default_frequency):
        self.default_frequency = default_frequency

    def _normalize_window(self, start_time, end_time):
        frequency_seconds = self.default_frequency.total_seconds()
        if frequency_seconds >= 3600:
            start_time = start_time.replace(minute=0, second=0, microsecond=0)
            end_time = end_time.replace(minute=0, second=0, microsecond=0)
        elif frequency_seconds >= 60:
            start_time = start_time.replace(second=0, microsecond=0)
            end_time = end_time.replace(second=0, microsecond=0)
        return start_time, end_time

    def available_count(self, start_time, end_time):
        start_time, end_time = self._normalize_window(start_time, end_time)
        return len(pd.date_range(start_time, end_time, freq=self.default_frequency))

    def generate(self, num_of_records, start_time, end_time, jitter=False, allow_duplicates=False):
        start_time, end_time = self._normalize_window(start_time, end_time)
        timestamps = list(pd.date_range(start_time, end_time, freq=self.default_frequency))
        num_of_records = int(num_of_records or 0)
        if num_of_records > len(timestamps):
            if allow_duplicates:
                selected = random.choices(timestamps, k=num_of_records)
            else:
                raise ValueError(
                    f"Number of records {num_of_records} exceeds the number of available timestamps {len(timestamps)}."
                )
        else:
            selected = random.sample(timestamps, num_of_records)
        if jitter:
            jittered_timestamps = []
            delta = pd.to_timedelta(self.default_frequency)
            for ts in timestamps:
                offset_sec = random.uniform(0, delta.total_seconds())
                jittered_ts = ts + timedelta(seconds=offset_sec)
                jittered_timestamps.append(jittered_ts)
            return jittered_timestamps
        return selected
