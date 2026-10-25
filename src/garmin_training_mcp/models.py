"""Strict request contracts and compact, JSON-schema-generating responses."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

IsoDate = Annotated[str, Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")]
ActivityId = Annotated[str, Field(strict=True, pattern=r"^[1-9][0-9]{0,18}$")]
PageSize = Annotated[int, Field(strict=True, ge=1, le=100)]
Offset = Annotated[int, Field(strict=True, ge=0, le=10000)]
Sport = Annotated[str, Field(strict=True, pattern=r"^[a-z][a-z0-9_]{0,63}$")]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Period(Request):
    start_date: IsoDate
    end_date: IsoDate | None = None

    @model_validator(mode="after")
    def ordered(self):
        self.end_date = self.end_date or self.start_date
        start, end = date.fromisoformat(self.start_date), date.fromisoformat(self.end_date)
        if end < start:
            raise ValueError("Dates must be ordered.")
        return self

    def require_days(self, maximum: int) -> None:
        if (
            date.fromisoformat(self.end_date) - date.fromisoformat(self.start_date)
        ).days >= maximum:
            raise ValueError("Date range is too large.")


class ActivitySearch(Period):
    sport: Sport | None = None
    offset: Offset = 0
    limit: PageSize = 20


class ActivityRequest(Request):
    activity_id: ActivityId
    split_offset: Offset = 0
    split_limit: PageSize = 100
    include_samples: bool = False
    include_gps: bool = False

    @model_validator(mode="after")
    def signed_id(self):
        if int(self.activity_id) > 2**63 - 1:
            raise ValueError("Activity ID must fit int64.")
        return self


class SparseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @model_serializer(mode="wrap")
    def omit_absent(self, handler):
        return {
            k: v
            for k, v in handler(self).items()
            if k in self.model_fields_set or k in {"kind", "unavailable_fields"}
        }


class Record(SparseModel):
    unavailable_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def mark_absent(self):
        self.unavailable_fields = sorted(
            k
            for k in type(self).model_fields
            if k not in self.model_fields_set and k not in {"kind", "unavailable_fields"}
        )
        return self


class Metrics(Record):
    distance_m: float | None = None
    duration_s: float | None = None
    average_speed_mps: float | None = None
    max_speed_mps: float | None = None
    average_heart_rate_bpm: float | None = None
    max_heart_rate_bpm: float | None = None
    average_power_w: float | None = None
    max_power_w: float | None = None


class Activity(Metrics):
    kind: Literal["activity"] = "activity"
    activity_id: str
    name: str | None = None
    sport: str | None = None
    started_at: str | None = None
    garmin_local_start: str | None = None
    activity_training_load: float | None = None
    aerobic_training_effect: float | None = None
    anaerobic_training_effect: float | None = None
    recovery_heart_rate_bpm: int | None = None


class Split(Metrics):
    kind: Literal["split_summary"] = "split_summary"
    split_type: str | None = None
    represented_splits: int | None = None


class ActivityDetail(Activity):
    splits: list[Split] = Field(default_factory=list)


class Score(SparseModel):
    value: int | None = None


class SleepDay(Record):
    kind: Literal["sleep"] = "sleep"
    calendar_date: str
    duration_s: int | None = None
    deep_s: int | None = None
    light_s: int | None = None
    rem_s: int | None = None
    awake_s: int | None = None
    unmeasurable_s: int | None = None
    sleep_start: str | None = None
    sleep_end: str | None = None
    scores: dict[str, Score] | None = None


class Baseline(SparseModel):
    low_upper: int | None = None
    balanced_low: int | None = None
    balanced_upper: int | None = None
    marker_value: float | None = None


class HrvDay(Record):
    kind: Literal["hrv"] = "hrv"
    calendar_date: str
    last_night_average: int | None = None
    weekly_average: int | None = None
    last_night_five_minute_high: int | None = None
    status: str | None = None
    baseline: Baseline | None = None


class DailySummary(Record):
    kind: Literal["daily_summary"] = "daily_summary"
    calendar_date: str
    steps: int | None = None
    resting_heart_rate_bpm: int | None = None
    stress_average: int | None = None
    body_battery_min: int | None = None
    body_battery_max: int | None = None
    body_battery_latest: int | None = None
    body_battery_charged: int | None = None
    body_battery_drained: int | None = None


class Pagination(BaseModel):
    offset: int
    limit: int
    has_more: bool
    next_offset: int | None


class ToolResponse[T: Record](BaseModel):
    status: Literal["ok", "partial", "missing"]
    retrieved_at: datetime
    timezone: str
    start_date: str | None = None
    end_date: str | None = None
    date_semantics: str
    records: list[T]
    missing_dates: list[str] = Field(default_factory=list)
    pagination: Pagination | None = None
    warnings: list[str] = Field(default_factory=list)
