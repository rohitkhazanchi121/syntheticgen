from datetime import timedelta
import random
import pandas as pd


class TimestampGenerator:
    def __init__(self, default_frequency):
        self.default_frequency = default_frequency

    def generate(self, num_of_records, start_time, end_time, jitter=False):
        if self.default_frequency.seconds >= 3600:
            start_time = start_time.replace(minute=0, second=0, microsecond=0)
            end_time = end_time.replace(minute=0, second=0, microsecond=0)
        elif self.default_frequency.seconds >= 60:
            start_time = start_time.replace(second=0, microsecond=0)
            end_time = end_time.replace(second=0, microsecond=0)
        timestamps = list(pd.date_range(start_time, end_time, freq=self.default_frequency))
        if num_of_records > len(timestamps):
            raise ValueError(
                f"Number of records {num_of_records} exceeds the number of available timestamps {len(timestamps)}."
            )
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
