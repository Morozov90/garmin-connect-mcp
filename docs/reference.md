# Technical reference

For installation and client setup, see the [README](../README.md).

## SDKs

Uses Garmin's **official** Python client and **official MCP Python SDK**
(`mcp.server.fastmcp.FastMCP`), not the separately distributed `fastmcp` project.
MCP is pinned to 1.30.0 because the official 2.x SDK renamed this interface to MCPServer.

## Scope and verified capabilities

| Tool | Inputs | Output |
| --- | --- | --- |
| `list_activities` | `start_date`, `end_date`, optional parent `sport`, `offset=0`, `limit=20` | IDs, name/sport/start, duration, distance, speed, HR, power, activity training load/effect where present; next page information |
| `get_activity` | Decimal-string `activity_id`, `split_offset=0`, `split_limit=100` | Activity metrics, reported recovery HR, one page of feature/group split summaries |
| `get_sleep` | `start_date`, optional `end_date` | Duration/stages in seconds, numeric Garmin score components, sleep window times |
| `get_hrv` | `start_date`, optional `end_date` | Garmin overnight/weekly summaries and reported baseline/status |
| `get_daily_summary` | `start_date`, optional `end_date` | Steps, Garmin resting-HR field, stress and Body Battery where present |

The [capability matrix](capabilities.md) separates official-source confirmation,
implemented features needing account verification, and unavailable features.

Split summaries can represent groups of splits, and do **not** promise individual
laps or a heart-rate time series. Detailed samples and GPS tracks are unavailable in
v1; `include_samples=true` or `include_gps=true` on `get_activity` returns `unsupported`.
No start/end coordinates are returned. The official ZIP download endpoint could support
future FIT parsing, which is outside v1. Daily readiness/load/status/recovery-time
endpoints were not found; activity training load is a different reported metric.

## Credential options

Create a key on the [Garmin Connect Personal API Key page](https://connect.garmin.com/app/settings/personalApiToken).
Garmin lets you choose 30, 90, 180 days or one year; the key is displayed only once.
Deleting a key revokes it and its associated access tokens. See the
[official FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/).

Use a Personal API Key rather than a temporary bearer token. Environment keys
are stored as plaintext in your client's configuration. The server does not copy
them to its key file; temporary bearer tokens still use the protected local cache.
A nonempty environment key takes precedence over a saved key file. An empty
`GARMIN_PERSONAL_API_KEY` is an error and does not fall back to the file.

The `setup` prompt hides input and refuses noninteractive input or an echoing
fallback. To use the saved key file, omit the client's `env` block or `.env` table.
Both clients use separate stdio processes and can share the local credential store.

After saving the key with `setup`, you can register clients from Terminal:

```sh
codex mcp get garmin-training
codex mcp list
```

```sh
claude mcp get garmin-training
claude mcp list
```

```sh
GARMIN_UVX_BIN="$(command -v uvx)"
claude mcp add --transport stdio --scope user garmin-training -- "$GARMIN_UVX_BIN" --python 3.13 --from garmin-training-mcp==0.1.1 garmin-mcp
codex mcp add garmin-training -- "$GARMIN_UVX_BIN" --python 3.13 --from garmin-training-mcp==0.1.1 garmin-mcp
```

Register only the clients you use. Update existing entries instead of adding
duplicate TOML tables. If only the key changes, keep your command and arguments.
The optional Codex timeout allows time for bounded retries. Codex CLI and its local
desktop app share MCP configuration on the same host. Claude Code's user
configuration is `~/.claude.json`; preserve its other settings. After restarting,
run `/mcp` and check that the server exposes five tools.

See the [OpenAI MCP documentation](https://learn.chatgpt.com/docs/extend/mcp)
and [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).

## Credential storage and renewal

The application directory has mode `700`; key, token and lock files have mode `600`.
Symlinked, nonregular, wrong-owner or permissive credential files are rejected.
The `bearer-token.json` file in the same directory uses the official SDK's cache
format and expiry logic, with atomic writes and a cross-process lock.

| Variable | Behavior |
| --- | --- |
| `GARMIN_PERSONAL_API_KEY` | Overrides the saved key. An empty value is an error with no fallback. |
| `GARMIN_MCP_CONFIG_DIR` | Overrides the storage directory; must be an absolute path. Configure identically in both clients when sharing a cache. |
| `GARMIN_MCP_TIMEZONE` | Presentation timezone as an IANA identifier; defaults to `America/Vancouver`. |

`GARMIN_PERSONAL_API_BASE_URL` overrides are rejected except for the identical official
origin. Requests ignores proxy/netrc environment settings and follows no redirects,
so credentials are sent only to `https://personal.connectapi.garmin.com`.

The official authenticator exchanges the key for a bearer token valid for up to
24 hours or key expiry, whichever is earlier. It renews the cache when a token has
one hour or less remaining. There are no refresh tokens. A data-call 401 triggers
one forced exchange and one replay. If authentication still fails, replace the key
in the client's environment setting or run `setup` again, depending on your method.
Changing the key prevents reuse of a token cached for a different key.

## Install with the project lockfile

For development or exact locked dependencies, clone the repository and enter it:

```sh
git clone https://github.com/Morozov90/garmin-connect-mcp.git
cd garmin-connect-mcp
```

Then install and verify the locked environment:

```sh
uv sync --locked
uv run --locked garmin-mcp --help
```

This creates `.venv` and the `garmin-mcp` executable. For a client to launch this
installation directly, use `/absolute/path/to/garmin-connect-mcp/.venv/bin/garmin-mcp`
as its command and `[]` as its arguments. Keep the same credential configuration.
The direct launcher does not install or resolve dependencies during client startup.
For local `uvx` development instead, use `--from .` in the repository root; client
configurations need the full checkout path in place of `garmin-training-mcp==0.1.1`.

## Dates, units and output semantics

- Dates are exactly `YYYY-MM-DD`, with ordered inclusive bounds. Wellness accepts
  up to **31 days**; omitted end equals start. Activity search accepts up to **366 days**.
  These conservative local limits are separate from endpoint limits in the matrix.
- Activity filters are Garmin's **activity-local start dates**. Garmin wellness
  `calendarDate` is preserved. The presentation timezone does not shift filters or
  rebucket wellness data. Official Swagger does not establish whether sleep/HRV
  calendar dates consistently refer to sleep start or wake date; verify against
  timestamps before aligning nights and workouts.
- Documented GMT activity/sleep fields are UTC even when the API omits a suffix.
  Output instants are ISO timestamps with offsets in the configured IANA zone.
  Naive Garmin local start times remain `garmin_local_start`; no offset is invented.
  DST behavior follows the machine's timezone database. Sleep schema declarations
  conflict about strings versus milliseconds; ISO date-time and numeric epoch
  milliseconds are accepted for GMT sleep fields pending live verification.
- Distance is **meters**, duration/stages **seconds**, speed **meters/second**,
  heart rate **bpm**, power **watts**. There are no derived metrics or pace estimates.
  Load, training effect, stress and Body Battery retain Garmin's reported scales.
  HRV values also retain Garmin's scale: the reviewed Swagger does not state the
  measurement unit, so output names intentionally do not claim a unit.
- `resting_heart_rate_bpm` comes from Garmin's `restingValue`, documented as resting HR
  **or absolute minimum when no resting value is available**. The server cannot
  distinguish those cases and does not replace it with its own calculation.
- A missing property stays absent and is listed in `unavailable_fields`; explicit
  `null` stays null; numeric **zero stays zero**. Absence means Garmin didn't provide
  that field, not proof of a device limitation. Numeric sleep score components preserve
  missing/null values too. Unsupported/unrecorded metrics are never inferred.
- Every response includes retrieval time (UTC), presentation timezone, requested period
  where applicable, date semantics, records, missing dates and pagination/warnings.
  `status=partial` means some requested dates were absent; `missing` means no records.
  `ok` means coverage was returned, not that every optional metric exists. Malformed,
  duplicate or out-of-period wellness rows cause a schema error instead of misleading
  partial results. A 404 is an explicit `not_found` error, never a zero measurement.
- Pages have at most **100** activities/split summaries; offsets are **0..10000**.
  Activity search fetches one extra record to report `has_more`. Follow `next_offset`.
  A full page without another record has `has_more=false`. At the local offset cap,
  `has_more=true` with no next offset includes a warning to narrow the range.
- Structured output is limited to **128 KiB**, decoded HTTP bodies to **4 MiB**.
  Oversize responses produce an error rather than silently dropping fields/rows.
  Split paging reduces returned output but fetches the same bounded activity summary.

Example tool inputs:

```json
{"start_date":"2026-10-01","end_date":"2026-10-14","sport":"running","limit":20}
```

```json
{"activity_id":"123456789","split_offset":0,"split_limit":25}
```

## Reliability and privacy

Only documented Personal API operations are used. Remote data operations are GET;
token creation is the required authentication POST. All five tools advertise
read-only, nondestructive, idempotent, open-world MCP annotations. No arbitrary URL
or endpoint tool exists; no email/password, scraping or unofficial fallback exists.

Requests have 5-second connect and 15-second read timeouts, plus a 20-second response-body
deadline that starts after response headers arrive. A timer interrupts the socket
even when a streaming read has not filled its chunk. GET attempts are limited to three, including retries for network
failures and HTTP 429/500/502/503/504. Retry-After (seconds or HTTP date) is honored:
wait up to five seconds per retry, otherwise return the delay without retrying.
Without a header, delays are 0.5 then 1 second. Token POST is not retried. Stale-token
recovery is limited to one renewal/replay; a slow pathological call can exceed an
individual client timeout. Credential-lock acquisition waits at most five seconds.

Garmin calls run in worker threads, preserving MCP runtime responsiveness. Sessions
close after each adapter call, including errors; the server exits when stdin closes
or the client terminates it. Blocking in-flight requests finish or time out before
thread cleanup. There is no long-lived HTTP session, background scheduler, database,
or wellness cache. Data is fetched fresh each call; only bearer tokens are cached.

The server runs on your Mac and stores credentials locally. Internet is required for
Garmin API requests, and package downloads are required during installation/update.
**Retrieved data can be sent to the AI provider by Claude Code or Codex.** Running the
server locally does not make the model's analysis offline or keep retrieved health
information out of client history. Configure provider/client privacy settings to
match your preferences. The server itself writes no health-data files or telemetry.
Your macOS backups or sync tools may back up local files; the plaintext credential
store is not Keychain and should be treated like other local secrets.

Stdout is exclusively MCP protocol during serving. Diagnostics go to stderr using
fixed codes for ordinary tool failures. Upstream bodies and raw tool-validation
errors are not returned in tool error responses. SDK diagnostic records are also
redacted at the root logging handler, including protocol-validation warnings and
tracebacks; see the [security audit](security-audit-2026-10-24.md).
Do not enable raw HTTP logging around this process. Returned activity names are
untrusted user content, not instructions.

## Verify and test

### Published package and client connection

Check that the release launches without a checkout:

```sh
uvx --python 3.13 --from garmin-training-mcp==0.1.1 garmin-mcp --help
```

After configuring credentials, fully quit and reopen your client, then ask:

> Use Garmin to compare my last two runs. What was my average pace?

> Use Garmin to summarize my sleep from the last seven days.

Confirm that the client calls Garmin tools and compare the results with Garmin
Connect. A successful `--help` check verifies installation, not authentication.
The server returns speed in meters/second; the AI client can calculate pace.

### Development checks

From the repository root, run the offline checks below. Tests use clearly synthetic
fixtures and injected HTTP transport; no test requires your key or contacts Garmin:

```sh
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The stdio tests launch actual subprocesses, initialize an MCP session, discover all
five schemas/annotations, invoke all five tools with synthetic HTTP responses
through the official SDK, check errors, and close the transport. They also start
the production entry point without credentials to verify discovery and an actionable
error. Fixture injection exists only in test files, not as a production mode.

### Live Garmin check

After configuring credentials locally, choose a date with synced activity, sleep
and wellness data. Replace `YYYY-MM-DD` with that date:

```sh
uvx --python 3.13 --from garmin-training-mcp==0.1.1 garmin-mcp check --date YYYY-MM-DD
```

This command makes real Garmin calls and prints only availability counts/statuses,
not raw health records or keys. It checks activity detail if search finds an activity.
A key set only in the client's `env` configuration is not inherited by Terminal;
use a saved key file or a securely configured terminal environment for this check.
A missing date is a successful empty result, not proof of device support. Then:

1. Make an actual tool invocation in each registered client; compare the returned
   metrics with Garmin Connect for a known workout/night/day.
2. Verify sport-specific power/HR/distance, grouped split meaning, sleep score keys,
   HRV scale/baseline/status, and nested daily-summary fields for your account/devices.
3. Compare sleep window timestamps to the associated calendar date, particularly
   across midnight/travel. Check actual sleep timestamp representation.
4. Query an older short range to establish accessible history for each tool. No
   retention/backfill guarantee was found. Test pagination against enough activities.
5. Restart both clients to exercise cache reuse. Check renewal on expiry and a
   deliberately revoked key only when ready to replace it through setup.

The five tools have passed a live account check, and activity/sleep queries have
been exercised through Codex. These checks do not guarantee the same data is
available for every account or device. Claude Code integration, historical coverage,
every optional sport/device metric, and live expiry/revocation behavior still need
verification for the deployment you use.

## Troubleshooting

| Symptom / error code | Action |
| --- | --- |
| No tools/failed startup | Run the published launcher with `--help`; check the `uvx` executable path; restart the client; check stderr. For local development, run locked sync. Running `serve` manually waits for MCP messages. |
| `missing_credentials` | Check `GARMIN_PERSONAL_API_KEY` in the client's `env` block, or run setup if using a key file. An empty environment override is an error. For key files, check mode/ownership and use `chmod 600` on files you intentionally trust. |
| `authentication` | Key may be expired/deleted/revoked. Create a new Personal API key, update the client's environment setting and restart the server, or run setup if using a key file. No interactive sign-in occurs during calls. |
| `configuration` | Check absolute config path, timezone and directory permissions; remove SDK base URL overrides. |
| `busy` | Another process is accessing credentials/doing a request. Retry when it finishes. Do not delete the lock file while clients run. |
| `invalid_input` | Check date format/order, <=31/366-day range, positive decimal-string ID, parent sport key, page size and offset. No credential arguments are accepted. |
| `rate_limited` | Honor `retry_after_seconds` when provided, otherwise wait and retry conservatively. |
| `timeout`, `network`, `upstream` | Check internet/Garmin availability, retry later or request a smaller range. Environment proxy settings are intentionally ignored. |
| `not_found` / `missing` | Check account/date/sync state. Data may be unavailable; absence is not zero. |
| `upstream_rejected` | Check supported parent sport, dates and resource availability; Garmin may impose undocumented limits. |
| `upstream_schema` | Official API schema may have changed or an unexpected response arrived. Mapping is intentionally strict. Inspect upstream changes without logging credentials or full responses. |
| `response_too_large` | Reduce date range/page size. A single summary over the upstream body cap cannot be retrieved by this version. |
| `unsupported` | Samples/GPS require future FIT work; readiness/daily load are not available through the documented endpoints. |

## Update or remove

### Published releases

To upgrade, replace `garmin-training-mcp==0.1.1` in your client arguments with the
new published version. Run the matching `--help` command, restart the client, and
make a Garmin tool call. Keep your existing credential settings. Editing a local
checkout does not change an installation launched from PyPI.

### Local development

After editing dependencies intentionally, use `uv lock` to refresh `uv.lock`, review
changes and run the full checks before keeping the update. The pinned official SDK
versions do not automatically jump to breaking releases. For existing locked sources:

```sh
uv sync --locked
```

Run project commands from the repository root. For a local source directory, uv's
cache normally checks the project metadata timestamp, so source-only changes may
not trigger a rebuild. If using `uvx`, refresh the metadata timestamp and launch
an isolated tool environment after source changes:

```sh
touch pyproject.toml
uvx --isolated --python 3.13 --from . garmin-mcp --help
```

The `touch` command updates only the timestamp, not the file's contents. See
[uv's local dependency caching behavior](https://docs.astral.sh/uv/concepts/cache/).
Restart your MCP client after code/dependency changes.

### Remove

Remove registrations with:

```sh
claude mcp remove --scope user garmin-training
codex mcp remove garmin-training
```

To remove saved credentials, first stop both clients/server processes, then delete
the `garmin-training-mcp` application-support directory using Finder. Revoke the key
in Garmin Connect as well, and remove any `GARMIN_PERSONAL_API_KEY` value saved in
client configuration or inherited from your environment. Removing client registration
alone does not revoke the key or delete the separate credential store. Remove the
checkout/virtual environment separately if no longer needed.

## Architecture

`config.py` owns credentials/settings/locking; `adapter.py` wraps official SDK auth
and transport; `models.py` defines contracts; `normalize.py` projects documented
fields; `service.py` handles bounded data operations; `server.py` registers stdio
MCP tools; `__main__.py` separates setup, serving and explicit live checks.
The adapter accepts a session factory for synthetic HTTP tests. The pinned official
SDK's private token writer is overridden only to add atomic replacement, with tests
covering the cache and concurrency behavior.

See the [capability matrix](capabilities.md) for the official API sources and
the [security audit](security-audit-2026-10-24.md) for reviewed controls and the
logging remediation.

