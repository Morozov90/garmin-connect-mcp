"""Project only officially documented fields; never forward raw upstream payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from .errors import GarminError
from .models import Activity, ActivityDetail, Baseline, DailySummary, HrvDay, SleepDay, Split

METRICS = {
    "distance_m": "distance",
    "duration_s": "duration",
    "average_speed_mps": "averageSpeed",
    "max_speed_mps": "maxSpeed",
    "average_heart_rate_bpm": "averageHR",
    "max_heart_rate_bpm": "maxHR",
    "average_power_w": "averagePower",
    "max_power_w": "maxPower",
}


def obj(value):
    if not isinstance(value, dict):
        raise GarminError("upstream_schema")
    return value


def project(source, fields):
    source = obj(source)
    return {target: source[key] for target, key in fields.items() if key in source}


def build(model, values):
    try:
        return model.model_validate(values)
    except (ValidationError, ValueError, TypeError):
        raise GarminError("upstream_schema") from None


def timestamp(value, timezone):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            instant = datetime.fromtimestamp(value / 1000, UTC)
        elif isinstance(value, str):
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # Only this helper's documented GMT fields are passed here.
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=UTC)
        else:
            raise ValueError
        return instant.astimezone(ZoneInfo(timezone)).isoformat()
    except (ValueError, OverflowError, OSError):
        raise GarminError("upstream_schema") from None


def activity(source, timezone, *, detail=False):
    source = obj(source)
    metrics = obj(source.get("summaryDTO", {})) if detail else source
    fields = {**METRICS, "average_power_w": "averagePower" if detail else "avgPower"}
    values = project(metrics, fields)
    identifier = source.get("activityId")
    if type(identifier) is not int or not 0 < identifier < 2**63:
        raise GarminError("upstream_schema")
    values["activity_id"] = str(identifier)
    values.update(
        project(
            metrics,
            {
                "activity_training_load": "activityTrainingLoad",
                "aerobic_training_effect": "trainingEffect" if detail else "aerobicTrainingEffect",
                "anaerobic_training_effect": "anaerobicTrainingEffect",
            },
        )
    )
    if detail:
        values.update(project(metrics, {"recovery_heart_rate_bpm": "recoveryHeartRate"}))
    values.update(project(source, {"name": "activityName"}))
    type_field = "activityTypeDTO" if detail else "activityType"
    if type_field in source:
        values["sport"] = (
            None if source[type_field] is None else obj(source[type_field]).get("typeKey")
        )
    if "startTimeGMT" in metrics:
        values["started_at"] = timestamp(metrics["startTimeGMT"], timezone)
    if "startTimeLocal" in metrics:
        values["garmin_local_start"] = metrics["startTimeLocal"]
    return build(ActivityDetail if detail else Activity, values)


def split(source):
    return build(
        Split,
        {
            **project(source, METRICS),
            **project(source, {"split_type": "splitType", "represented_splits": "noOfSplits"}),
        },
    )


def sleep(source, timezone):
    values = project(
        source,
        {
            "calendar_date": "calendarDate",
            "duration_s": "sleepTimeSeconds",
            "deep_s": "deepSleepSeconds",
            "light_s": "lightSleepSeconds",
            "rem_s": "remSleepSeconds",
            "awake_s": "awakeSleepSeconds",
            "unmeasurable_s": "unmeasurableSleepSeconds",
        },
    )
    for output, key in {
        "sleep_start": "sleepStartTimestampGMT",
        "sleep_end": "sleepEndTimestampGMT",
    }.items():
        if key in source:
            values[output] = timestamp(source[key], timezone)
    if "sleepScores" in source:
        scores = source["sleepScores"]
        if scores is None:
            values["scores"] = None
        else:
            obj(scores)
            if len(scores) > 32 or any(len(k) > 64 for k in scores):
                raise GarminError("response_too_large")
            values["scores"] = {}
            for key, score in scores.items():
                selected = project(score, {"value": "value"})
                if (
                    "value" in selected
                    and selected["value"] is not None
                    and type(selected["value"]) is not int
                ):
                    raise GarminError("upstream_schema")
                values["scores"][key] = selected
    return build(SleepDay, values)


def hrv(source, timezone):
    values = project(
        source,
        {
            "calendar_date": "calendarDate",
            "last_night_average": "lastNightAvg",
            "weekly_average": "weeklyAvg",
            "last_night_five_minute_high": "lastNight5MinHigh",
            "status": "status",
        },
    )
    if "baseline" in source:
        if source["baseline"] is None:
            values["baseline"] = None
        else:
            baseline = project(
                source["baseline"],
                {
                    "low_upper": "lowUpper",
                    "balanced_low": "balancedLow",
                    "balanced_upper": "balancedUpper",
                    "marker_value": "markerValue",
                },
            )
            verified = build(Baseline, baseline).model_dump(exclude_unset=True)
            verified.pop("unavailable_fields", None)
            values["baseline"] = verified
    return build(HrvDay, values)


def daily(source, timezone):
    values = project(source, {"calendar_date": "calendarDate"})
    for output, path in {
        "steps": ("movement", "steps", "value"),
        "resting_heart_rate_bpm": ("heartRate", "restingValue"),
        "stress_average": ("stress", "avgLevel"),
        "body_battery_min": ("bodyBattery", "minValue"),
        "body_battery_max": ("bodyBattery", "maxValue"),
        "body_battery_latest": ("bodyBattery", "latestValue"),
        "body_battery_charged": ("bodyBattery", "chargedValue"),
        "body_battery_drained": ("bodyBattery", "drainedValue"),
    }.items():
        current = source
        for key in path:
            if current is None:
                values[output] = None
                break
            if key not in obj(current):
                break
            current = current[key]
        else:
            values[output] = current
    return build(DailySummary, values)
