"""Bounded training-data operations shared by MCP and the local live check."""

from datetime import UTC, date, datetime, timedelta

from pydantic import ValidationError

from . import normalize
from .config import Settings
from .errors import GarminError
from .models import (
    Activity,
    ActivityDetail,
    ActivityRequest,
    ActivitySearch,
    DailySummary,
    HrvDay,
    Pagination,
    Period,
    SleepDay,
    ToolResponse,
)

CALENDAR_SEMANTICS = (
    "Garmin calendarDate preserved; sleep-start versus wake-date association is unverified "
    "in official Swagger. Compare sleep UTC timestamps when aligning nights."
)


def validate(model, maximum=None, **kwargs):
    try:
        request = model(**kwargs)
        if maximum:
            request.require_days(maximum)
        return request
    except (ValidationError, ValueError, TypeError):
        raise GarminError("invalid_input") from None


def bounded(result):
    if len(result.model_dump_json().encode()) > 128 * 1024:
        raise GarminError("response_too_large")
    return result


def rows(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise GarminError("upstream_schema")
    return value


def pagination(offset, limit, more):
    next_offset = offset + limit if more and offset + limit <= 10000 else None
    return Pagination(offset=offset, limit=limit, has_more=more, next_offset=next_offset)


class TrainingService:
    def __init__(self, adapter, settings: Settings):
        self.adapter = adapter
        self.settings = settings

    def list_activities(self, start_date, end_date, sport=None, offset=0, limit=20):
        request = validate(
            ActivitySearch,
            366,
            start_date=start_date,
            end_date=end_date,
            sport=sport,
            offset=offset,
            limit=limit,
        )
        upstream = rows(
            self.adapter.call(
                "search_activities",
                start_date=request.start_date,
                end_date=request.end_date,
                activity_type=request.sport,
                start=request.offset,
                limit=request.limit + 1,
            )
        )
        if len(upstream) > limit + 1:
            raise GarminError("upstream_schema")
        page = pagination(offset, limit, len(upstream) > limit)
        records = [normalize.activity(row, self.settings.timezone) for row in upstream[:limit]]
        warnings = []
        if page.has_more and page.next_offset is None:
            warnings.append("Local offset cap reached; narrow the date range to retrieve more.")
        return bounded(
            ToolResponse[Activity](
                status="ok" if records else "missing",
                retrieved_at=datetime.now(UTC),
                timezone=self.settings.timezone,
                start_date=request.start_date,
                end_date=request.end_date,
                date_semantics=(
                    "Inclusive Garmin activity-local start dates; "
                    "configured timezone does not shift filters."
                ),
                records=records,
                pagination=page,
                warnings=warnings,
            )
        )

    def get_activity(
        self, activity_id, split_offset=0, split_limit=100, include_samples=False, include_gps=False
    ):
        request = validate(
            ActivityRequest,
            activity_id=activity_id,
            split_offset=split_offset,
            split_limit=split_limit,
            include_samples=include_samples,
            include_gps=include_gps,
        )
        if request.include_samples or request.include_gps:
            raise GarminError("unsupported")
        upstream = self.adapter.call("get_activity", request.activity_id)
        if upstream is None:
            raise GarminError("not_found")
        upstream = normalize.obj(upstream)
        result = normalize.activity(upstream, self.settings.timezone, detail=True)
        if result.activity_id != activity_id:
            raise GarminError("upstream_schema")
        splits = rows(upstream.get("splitSummaries"))
        result.splits = [
            normalize.split(row) for row in splits[split_offset : split_offset + split_limit]
        ]
        result.unavailable_fields = [k for k in result.unavailable_fields if k != "splits"]
        warnings = [
            "splitSummaries are Garmin feature/group summaries, not guaranteed individual laps."
        ]
        if "splitSummaries" not in upstream or upstream["splitSummaries"] is None:
            warnings.append("Split summaries are unavailable in this response.")
        page = pagination(split_offset, split_limit, len(splits) > split_offset + split_limit)
        if page.has_more and page.next_offset is None:
            warnings.append(
                "Local split offset cap reached; additional splits are unavailable in v1."
            )
        return bounded(
            ToolResponse[ActivityDetail](
                status="ok",
                retrieved_at=datetime.now(UTC),
                timezone=self.settings.timezone,
                date_semantics=(
                    "GMT fields are UTC instants; Garmin local start is preserved "
                    "without an assumed offset."
                ),
                records=[result],
                pagination=page,
                warnings=warnings,
            )
        )

    def _wellness(self, method, model, mapper, start_date, end_date, container=None):
        request = validate(Period, 31, start_date=start_date, end_date=end_date)
        upstream = self.adapter.call(method, request.start_date, request.end_date)
        if container and upstream is not None:
            upstream = normalize.obj(upstream)
            if container not in upstream:
                raise GarminError("upstream_schema")
            upstream = upstream[container]
        upstream = rows(upstream)
        start, end = date.fromisoformat(request.start_date), date.fromisoformat(request.end_date)
        requested = {(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)}
        seen, records = set(), []
        for row in upstream:
            calendar = row.get("calendarDate")
            if not isinstance(calendar, str) or calendar not in requested or calendar in seen:
                raise GarminError("upstream_schema")
            seen.add(calendar)
            records.append(mapper(row, self.settings.timezone))
        missing = sorted(requested - seen)
        return bounded(
            ToolResponse[model](
                status="missing" if not records else "partial" if missing else "ok",
                retrieved_at=datetime.now(UTC),
                timezone=self.settings.timezone,
                start_date=request.start_date,
                end_date=request.end_date,
                date_semantics=CALENDAR_SEMANTICS
                if model in (SleepDay, HrvDay)
                else "Inclusive Garmin calendar dates; no timezone rebucketing.",
                records=sorted(records, key=lambda r: r.calendar_date),
                missing_dates=missing,
            )
        )

    def get_sleep(self, start_date, end_date=None):
        return self._wellness(
            "get_daily_sleep_summaries", SleepDay, normalize.sleep, start_date, end_date
        )

    def get_hrv(self, start_date, end_date=None):
        return self._wellness(
            "get_daily_hrv_summaries", HrvDay, normalize.hrv, start_date, end_date, "hrvSummaries"
        )

    def get_daily_summary(self, start_date, end_date=None):
        return self._wellness(
            "get_daily_summaries", DailySummary, normalize.daily, start_date, end_date, "data"
        )
