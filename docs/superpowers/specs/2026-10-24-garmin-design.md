# Local Garmin training MCP design

The binding requirements are in [the project brief](../../project-brief.md).
The user explicitly requests reasonable defaults and implementation without repeated confirmation.

## Intent and constraints
Supply accurate personal Garmin training and wellness data to Claude Code and Codex
through one Mac-only stdio executable. Python >=3.12, uv, official Garmin client
1.0.0, official MCP SDK 1.30.0 FastMCP, Pydantic, pytest and Ruff.
No HTTP listener, database, AI coaching, unofficial endpoints, account passwords,
publishing, pushing or deployment. Account and device availability require live checks.

## Approaches
Use the official synchronous Python Garmin client behind a small adapter, offloading
whole operations to a worker thread. This is the selected approach from the brief.
A TypeScript server plus a Python subprocess adds a second runtime and protocol;
a direct HTTP implementation duplicates the official authentication client. Neither
is justified here. MCP v2 has renamed FastMCP to MCPServer; pin official SDK v1.30.0
instead of using the separately distributed fastmcp package.

## Components
- config.py: timezone, hidden setup prompt, credential discovery, owner-only storage,
  atomic key replacement and a bounded process/file lock for shared credential/cache access.
- adapter.py: official authentication/client, fixed production origin, timeouts,
  safe errors, one stale-token refresh, bounded transient retries and Retry-After.
  Keep SDK token caching, serialize access and make its writes atomic.
- models.py and normalize.py: strict input validation, compact allowlisted projections,
  null/absent/zero preservation, units and time conversion.
- service.py: five bounded operations and explicit missing-date/partial-result reporting.
- server.py: official FastMCP tool registration, typed output schemas, annotations,
  worker-thread calls, sanitized protocol errors and cleanup.
- __main__.py: garmin-mcp [setup|serve|check], default serve.

## Data contracts and limits (implementation choices)
Wellness calls accept inclusive ISO start_date/end_date (end defaults to start),
maximum 31 days. Activity search accepts <=366 days, offset <=10000, limit 1..100;
fetch limit+1 to determine more results. Activity detail splits are paged, <=100
per call, with explicit next offset. Total structured output <=128 KiB; reject
oversize responses instead of truncating. HTTP decoded bodies <=4 MiB.
Activity load/training effect and detail recovery HR are retained when reported.
Only documented JSON fields are mapped; unknown fields are dropped. Optional numeric
fields preserve explicit null and zero; absent fields stay absent. Report omitted
fields as unavailable without guessing why. No derived readiness or pace metrics.

Garmin calendar dates and local activity date filters remain Garmin's dates; a
configurable America/Vancouver zone controls presentation of UTC instants and today's
date. Do not reinterpret naive device-local timestamps using the default zone.
Sleep/HRV calendarDate is preserved: Swagger does not establish universally whether
it is sleep-start or wake date. Sleep timestamp schemas conflict (date-time strings
with descriptions saying milliseconds); accept ISO strings and epoch milliseconds,
and document this compatibility decision pending live verification.

## Confirmed limitations
Activity summary splitSummaries are feature/group summaries, not a promise of
individual laps. No documented JSON samples/GPS track or daily training readiness/load
endpoint. Reject requests for unavailable samples/GPS explicitly, before fetching.
A FIT parser could later add such features from the documented download endpoint,
but is deliberately outside v1. No historical retention or rate quota was found.

## Credentials and reliability
Key override GARMIN_PERSONAL_API_KEY precedes an owner-only key file under
~/Library/Application Support/garmin-training-mcp; GARMIN_MCP_CONFIG_DIR allows
an absolute local override. GARMIN_MCP_TIMEZONE defaults to America/Vancouver.
Never prompt while serving. Setup writes only when explicitly run by the user.
Disable SDK/http logging; never expose upstream exception text, URLs or bodies.
Use fixed public Garmin origin and reject the SDK's base-URL override; ignore
proxy/netrc environment in Requests sessions. Follow no redirects.
No wellness data cache; only official bearer token cache. SDK renews within one
hour of expiry; expired/revoked keys need replacement locally. Cross-process lock
covers token reads/writes, setup and calls. Atomic token replacement uses the
SDK's writer on a private temporary cache path, then os.replace under the lock.

## Verification
Synthetic fixtures based on Garmin OpenAPI, no live credentials. Verify validation,
DST, exact projections, absence/null/zero, pagination, errors, 401 refresh bounds,
rate waiting, timeouts, byte limits, permissions, concurrent cache access and no
secret leakage. Actual subprocess stdio initialize/discover/call tests use a
test-only injected Garmin HTTP session. Live check command separately verifies
account access after setup; no live-validation claim until run.
