"""Synthetic fixtures shaped from Garmin's public OpenAPI, not account captures."""

from copy import deepcopy

import pytest

from garmin_training_mcp.config import Settings
from garmin_training_mcp.errors import GarminError
from garmin_training_mcp.service import TrainingService


class FakeGarmin:
    def __init__(self, **responses):
        self.responses = responses
        self.calls = []

    def call(self, method, *args, **kwargs):
        self.calls.append((method, args, kwargs))
        return deepcopy(self.responses[method])


def service(tmp_path, **responses):
    api = FakeGarmin(**responses)
    return TrainingService(api, Settings(tmp_path)), api


ACTIVITY = {
    "activityId": 42,
    "activityName": "Synthetic Run",
    "activityType": {"typeKey": "running"},
    "startTimeGMT": "2026-10-24 17:30:00",
    "startTimeLocal": "2026-10-24 10:30:00",
    "distance": 5000,
    "duration": 1500,
    "averageSpeed": 3.333,
    "averageHR": 150,
    "avgPower": 0,
    "maxHR": None,
    "startLatitude": 49.2,
    "unknown": "discard",
}


def test_activity_projection_units_null_zero_and_lookahead(tmp_path):
    s, api = service(tmp_path, search_activities=[ACTIVITY, {**ACTIVITY, "activityId": 43}])
    result = s.list_activities("2026-10-01", "2026-10-24", sport="running", limit=1)
    data = result.model_dump(mode="json")
    assert data["pagination"] == {"offset": 0, "limit": 1, "has_more": True, "next_offset": 1}
    assert api.calls[0][2] == {
        "start_date": "2026-10-01",
        "end_date": "2026-10-24",
        "activity_type": "running",
        "start": 0,
        "limit": 2,
    }
    row = data["records"][0]
    assert row["distance_m"] == 5000
    assert row["average_power_w"] == 0
    assert row["max_heart_rate_bpm"] is None
    assert "max_power_w" not in row
    assert "latitude" not in str(row)
    assert "unknown" not in row
    assert row["started_at"] == "2026-10-24T10:30:00-07:00"
    assert "max_power_w" in row["unavailable_fields"]


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-02-30", "2026-03-01"),
        ("2026-10-02", "2026-10-01"),
        ("2026-1-01", "2026-01-01"),
        ("2026-01-01", "2026-02-01"),
        ("2026-01-01T00:00:00", "2026-01-01"),
    ],
)
def test_wellness_rejects_invalid_or_oversize_ranges_before_network(tmp_path, start, end):
    s, api = service(tmp_path)
    with pytest.raises(GarminError) as exc:
        s.get_sleep(start, end)
    assert exc.value.code == "invalid_input"
    assert api.calls == []


def test_sleep_range_marks_missing_and_retains_partial_values(tmp_path):
    s, _ = service(
        tmp_path,
        get_daily_sleep_summaries=[
            {
                "calendarDate": "2026-10-01",
                "sleepTimeSeconds": 25200,
                "deepSleepSeconds": 0,
                "remSleepSeconds": None,
                "sleepScores": {"overall": {"value": 85}},
                "sleepStartTimestampGMT": "2026-10-01T06:30:00.000Z",
                "sleepEndTimestampGMT": 1790857800000,
            }
        ],
    )
    data = s.get_sleep("2026-10-01", "2026-10-02").model_dump(mode="json")
    assert data["status"] == "partial"
    assert data["missing_dates"] == ["2026-10-02"]
    row = data["records"][0]
    assert row["duration_s"] == 25200
    assert row["deep_s"] == 0
    assert row["rem_s"] is None
    assert "light_s" not in row
    assert row["scores"]["overall"] == {"value": 85}
    assert row["sleep_start"] == "2026-09-30T23:30:00-07:00"
    assert "unverified" in data["date_semantics"]


def test_hrv_and_v2_nested_wellness_schema(tmp_path):
    s, _ = service(
        tmp_path,
        get_daily_hrv_summaries={
            "hrvSummaries": [
                {
                    "calendarDate": "2026-10-01",
                    "lastNightAvg": 46,
                    "weeklyAvg": None,
                    "status": "BALANCED",
                    "baseline": {"balancedLow": 40, "balancedUpper": 70},
                }
            ]
        },
        get_daily_summaries={
            "data": [
                {
                    "calendarDate": "2026-10-01",
                    "movement": {"steps": {"value": 0}},
                    "heartRate": {"restingValue": 49},
                    "stress": {"avgLevel": None},
                    "bodyBattery": {"latestValue": 55},
                }
            ]
        },
    )
    hrv = s.get_hrv("2026-10-01").model_dump(mode="json")["records"][0]
    assert hrv["last_night_average"] == 46 and hrv["weekly_average"] is None
    assert hrv["baseline"] == {"balanced_low": 40, "balanced_upper": 70}
    daily = s.get_daily_summary("2026-10-01").model_dump(mode="json")["records"][0]
    assert daily["steps"] == 0 and daily["resting_heart_rate_bpm"] == 49
    assert daily["stress_average"] is None and daily["body_battery_latest"] == 55


def test_splits_are_paged_and_location_samples_explicitly_unsupported(tmp_path):
    s, api = service(
        tmp_path,
        get_activity={
            "activityId": 42,
            "activityName": "Synthetic",
            "summaryDTO": {"distance": 5000, "averagePower": 200},
            "splitSummaries": [
                {"splitType": "INTERVAL_ACTIVE", "distance": 1000, "noOfSplits": 3},
                {"splitType": "INTERVAL_REST", "distance": 200, "noOfSplits": 2},
            ],
        },
    )
    data = s.get_activity("42", split_limit=1).model_dump(mode="json")
    assert data["pagination"]["has_more"]
    assert data["records"][0]["splits"][0]["represented_splits"] == 3
    assert data["records"][0]["average_power_w"] == 200
    for flag in ["include_samples", "include_gps"]:
        with pytest.raises(GarminError) as exc:
            s.get_activity("42", **{flag: True})
        assert exc.value.code == "unsupported"
    assert len(api.calls) == 1


@pytest.mark.parametrize("id", ["../42", "0", "-1", "４２", "42/other", True, 42])
def test_invalid_identifiers_never_reach_api(tmp_path, id):
    s, api = service(tmp_path)
    with pytest.raises(GarminError):
        s.get_activity(id)
    assert not api.calls


def test_dst_uses_utc_instant_not_naive_local_assumption(tmp_path):
    s, _ = service(
        tmp_path, search_activities=[{**ACTIVITY, "startTimeGMT": "2025-11-02 09:30:00"}]
    )
    row = s.list_activities("2025-11-02", "2025-11-02").model_dump(mode="json")["records"][0]
    assert row["started_at"] == "2025-11-02T01:30:00-08:00"
    s, _ = service(
        tmp_path, search_activities=[{k: v for k, v in ACTIVITY.items() if k != "startTimeGMT"}]
    )
    row = s.list_activities("2026-10-24", "2026-10-24").model_dump(mode="json")["records"][0]
    assert "started_at" not in row
    assert row["garmin_local_start"] == "2026-10-24 10:30:00"


def test_missing_schema_drift_and_size_limits(tmp_path):
    s, _ = service(tmp_path, get_daily_sleep_summaries=[])
    assert s.get_sleep("2026-10-01").status == "missing"
    for payload in [
        {"unexpected": []},
        [{"calendarDate": "2026-10-01", "sleepTimeSeconds": "bad"}],
    ]:
        s, _ = service(tmp_path, get_daily_sleep_summaries=payload)
        with pytest.raises(GarminError) as exc:
            s.get_sleep("2026-10-01")
        assert exc.value.code == "upstream_schema"
    s, _ = service(tmp_path, search_activities=[{**ACTIVITY, "activityName": "x" * 200000}])
    with pytest.raises(GarminError) as exc:
        s.list_activities("2026-10-01", "2026-10-24")
    assert exc.value.code == "response_too_large"


def test_duplicate_or_outside_period_is_schema_error(tmp_path):
    for rows in [[{"calendarDate": "2026-10-01"}] * 2, [{"calendarDate": "2025-01-01"}]]:
        s, _ = service(tmp_path, get_daily_sleep_summaries=rows)
        with pytest.raises(GarminError) as exc:
            s.get_sleep("2026-10-01")
        assert exc.value.code == "upstream_schema"


def test_activity_load_and_effect_are_garmin_reported(tmp_path):
    s, _ = service(
        tmp_path,
        search_activities=[
            {
                **ACTIVITY,
                "activityTrainingLoad": 75,
                "aerobicTrainingEffect": 3.2,
                "anaerobicTrainingEffect": 0,
            }
        ],
        get_activity={
            "activityId": 42,
            "summaryDTO": {
                "activityTrainingLoad": 75,
                "trainingEffect": 3.2,
                "recoveryHeartRate": 85,
            },
        },
    )
    row = s.list_activities("2026-10-01", "2026-10-24").model_dump(mode="json")["records"][0]
    assert row["activity_training_load"] == 75
    assert row["aerobic_training_effect"] == 3.2
    assert row["anaerobic_training_effect"] == 0
    row = s.get_activity("42").model_dump(mode="json")["records"][0]
    assert row["aerobic_training_effect"] == 3.2
    assert row["recovery_heart_rate_bpm"] == 85


def test_exact_range_boundaries_and_complete_activity_page(tmp_path):
    s, _ = service(tmp_path, get_daily_sleep_summaries=[], search_activities=[ACTIVITY])
    assert len(s.get_sleep("2026-01-01", "2026-01-31").missing_dates) == 31
    result = s.list_activities("2025-01-01", "2026-01-01", limit=1)
    assert result.pagination.has_more is False
    assert result.pagination.next_offset is None
    with pytest.raises(GarminError):
        s.list_activities("2025-01-01", "2026-01-02")


def test_empty_activity_response_is_missing_resource(tmp_path):
    s, _ = service(tmp_path, get_activity=None)
    with pytest.raises(GarminError) as exc:
        s.get_activity("42")
    assert exc.value.code == "not_found"
