"""Only fixed, non-sensitive error messages cross the MCP boundary."""

MESSAGES = {
    "authentication": (
        "Garmin rejected the credentials. Check expiry/revocation and run garmin-mcp setup."
    ),
    "missing_credentials": (
        "Credentials unavailable. Run garmin-mcp setup; check file permissions and "
        "environment overrides."
    ),
    "not_found": ("Garmin has no data for this resource, or it is unavailable to this account."),
    "rate_limited": (
        "Garmin rate limit reached. Retry after the indicated delay, or later if absent."
    ),
    "timeout": ("Garmin request timed out; retry later or request a smaller period."),
    "network": ("Could not reach Garmin. Check internet connectivity and retry later."),
    "upstream": ("Garmin is temporarily unavailable; retry later."),
    "upstream_rejected": (
        "Garmin rejected the request. Check the dates, sport and account availability."
    ),
    "upstream_schema": ("Garmin returned an unexpected data format; no values were inferred."),
    "response_too_large": (
        "Response exceeds the local size limit. Request a smaller period or page."
    ),
    "busy": ("Credential storage is busy. Retry shortly."),
    "configuration": (
        "Invalid local configuration; check paths/timezone and remove any Garmin base URL override."
    ),
    "invalid_input": (
        "Invalid input. Check ISO dates, date order, identifiers and documented request limits."
    ),
    "unsupported": (
        "Detailed samples and GPS tracks are unavailable in v1; no documented JSON "
        "endpoint was found."
    ),
    "internal": ("The request could not be completed. Check the local installation and retry."),
}


class GarminError(Exception):
    def __init__(
        self, code: str, *, status: int | None = None, retry_after_seconds: float | None = None
    ):
        self.code = code
        self.status = status
        self.retry_after_seconds = retry_after_seconds
        super().__init__(MESSAGES[code])
