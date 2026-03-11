import pytest
import datetime
import pytz
from services.scraper import parse_iso_time

def test_parse_iso_time_empty():
    assert parse_iso_time(None, is_local=True) is None
    assert parse_iso_time("", is_local=False) is None

def test_parse_iso_time_invalid():
    assert parse_iso_time("not-a-date", is_local=True) is None
    assert parse_iso_time("2023-13-45T25:70:80", is_local=False) is None

def test_parse_iso_time_local_naive():
    # is_local=True with naive datetime should use Europe/Prague timezone
    iso_str = "2023-10-15T10:00:00"
    expected_dt = pytz.timezone('Europe/Prague').localize(datetime.datetime(2023, 10, 15, 10, 0, 0))
    expected_ts = expected_dt.timestamp()

    assert parse_iso_time(iso_str, is_local=True) == expected_ts

def test_parse_iso_time_utc_naive():
    # is_local=False with naive datetime should use UTC timezone
    iso_str = "2023-10-15T10:00:00"
    expected_dt = datetime.datetime(2023, 10, 15, 10, 0, 0, tzinfo=datetime.timezone.utc)
    expected_ts = expected_dt.timestamp()

    assert parse_iso_time(iso_str, is_local=False) == expected_ts

def test_parse_iso_time_aware():
    # Aware datetimes shouldn't be altered by timezone logic regardless of is_local
    iso_str_utc = "2023-10-15T10:00:00+00:00"
    expected_dt_utc = datetime.datetime(2023, 10, 15, 10, 0, 0, tzinfo=datetime.timezone.utc)
    expected_ts_utc = expected_dt_utc.timestamp()

    assert parse_iso_time(iso_str_utc, is_local=True) == expected_ts_utc
    assert parse_iso_time(iso_str_utc, is_local=False) == expected_ts_utc

    iso_str_custom = "2023-10-15T10:00:00+02:00"
    tz_custom = datetime.timezone(datetime.timedelta(hours=2))
    expected_dt_custom = datetime.datetime(2023, 10, 15, 10, 0, 0, tzinfo=tz_custom)
    expected_ts_custom = expected_dt_custom.timestamp()

    assert parse_iso_time(iso_str_custom, is_local=True) == expected_ts_custom
    assert parse_iso_time(iso_str_custom, is_local=False) == expected_ts_custom
