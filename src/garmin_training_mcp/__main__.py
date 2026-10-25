"""Separate interactive credential setup from the noninteractive MCP process."""

import argparse
import getpass
import json
import logging
import sys
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo

from .adapter import GarminAdapter
from .config import Settings, save_key
from .errors import GarminError
from .service import TrainingService


def setup(settings):
    if not sys.stdin.isatty():
        raise ValueError("Run setup in an interactive terminal; hidden input is required.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("Garmin Personal API Key (hidden): ")
    except getpass.GetPassWarning:
        raise ValueError("A terminal with hidden input is required.") from None
    save_key(settings, key)
    print("Personal API Key saved with owner-only permissions.", file=sys.stderr)


def live_check(settings, calendar_date):
    """Explicit live network checks; prints availability counts, never raw data or keys."""
    service = TrainingService(GarminAdapter(settings), settings)
    period = calendar_date or datetime.now(ZoneInfo(settings.timezone)).date().isoformat()
    failures = False
    results = {}
    activities = None
    for name in ("list_activities", "get_sleep", "get_hrv", "get_daily_summary"):
        try:
            if name == "list_activities":
                result = service.list_activities(period, period, limit=1)
                activities = result.records
            else:
                result = getattr(service, name)(period)
            results[name] = {"status": result.status, "records": len(result.records)}
        except GarminError as exc:
            results[name] = {"error": exc.code}
            failures = True
    if activities:
        try:
            result = service.get_activity(activities[0].activity_id)
            results["get_activity"] = {
                "status": result.status,
                "split_summaries": len(result.records[0].splits),
            }
        except GarminError as exc:
            results["get_activity"] = {"error": exc.code}
            failures = True
    else:
        results["get_activity"] = {"status": "unverified; no activity retrieved for this date"}
    print(json.dumps({"date": period, "checks": results}, indent=2))
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="Local, read-only Garmin Personal API MCP server")
    parser.add_argument("command", choices=("serve", "setup", "check"), nargs="?", default="serve")
    parser.add_argument("--date", help="YYYY-MM-DD for explicit live check (defaults to today)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(message)s")
    try:
        settings = Settings.from_env()
        if args.command == "setup":
            setup(settings)
        elif args.command == "check":
            return live_check(settings, args.date)
        else:
            from .server import create_server

            create_server().run(transport="stdio")
        return 0
    except (ValueError, OSError):
        print(
            "Local configuration/setup failed. Check paths, permissions, timezone and terminal.",
            file=sys.stderr,
        )
        return 1
    except GarminError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 0
    except Exception:
        # SDK exceptions may contain response bodies/credentials. Never print raw tracebacks.
        print(
            "Server failed. Verify the locked local installation and configuration.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
