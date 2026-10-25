"""Test-only stdio launcher with injected HTTP responses and a synthetic local key."""

from http_fixtures import ScriptedHTTP, token

from garmin_training_mcp.adapter import GarminAdapter, SafeSession
from garmin_training_mcp.config import Settings, save_key
from garmin_training_mcp.server import create_server
from garmin_training_mcp.service import TrainingService

settings = Settings.from_env()
save_key(settings, "SYNTHETIC-SECRET-KEY")
http = ScriptedHTTP(
    (200, token()),
    (
        200,
        [{"activityId": 42, "activityName": "Synthetic Run", "distance": 5000, "duration": 1500}],
    ),
    (200, [{"calendarDate": "2026-10-01", "sleepTimeSeconds": 25000}]),
    (200, {"hrvSummaries": [{"calendarDate": "2026-10-01", "lastNightAvg": 46}]}),
    (200, {"data": [{"calendarDate": "2026-10-01", "movement": {"steps": {"value": 1000}}}]}),
    (
        200,
        {
            "activityId": 42,
            "summaryDTO": {"distance": 5000},
            "splitSummaries": [{"distance": 1000, "noOfSplits": 3, "splitType": "INTERVAL_ACTIVE"}],
        },
    ),
)


def session_factory():
    session = SafeSession(sleep=lambda _: None)
    session.mount("https://", http)
    return session


service = TrainingService(GarminAdapter(settings, session_factory=session_factory), settings)
create_server(service).run(transport="stdio")
