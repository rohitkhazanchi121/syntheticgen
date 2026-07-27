from datetime import datetime, timedelta

from qa_orchestrator.services.syn_dataloader.syntheticgen.timestamp_generator import (
    TimestampGenerator,
)


def test_available_count_uses_frequency_over_window():
    generator = TimestampGenerator(default_frequency=timedelta(minutes=1))
    start = datetime(2026, 1, 1, 10, 0, 0)
    end = datetime(2026, 1, 1, 10, 59, 0)

    assert generator.available_count(start, end) == 60


def test_generate_uses_full_available_count_without_error():
    generator = TimestampGenerator(default_frequency=timedelta(minutes=5))
    start = datetime(2026, 1, 1, 10, 0, 0)
    end = datetime(2026, 1, 1, 10, 59, 0)
    count = generator.available_count(start, end)

    timestamps = generator.generate(count, start, end)

    assert len(timestamps) == count


def test_generate_allows_duplicate_timestamps_when_enabled():
    generator = TimestampGenerator(default_frequency=timedelta(seconds=1))
    start = datetime(2026, 1, 1, 10, 0, 0)
    end = datetime(2026, 1, 1, 10, 0, 2)

    timestamps = generator.generate(5, start, end, allow_duplicates=True)

    assert len(timestamps) == 5