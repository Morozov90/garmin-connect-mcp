# Project requirements

This brief has been generalized to remove personal background and device details.

## Project context

Working project name: `garmin-training-mcp`.

Use Python and the official Garmin client to simplify API access and authentication.

Support recorded running, cycling, swimming and strength activities where the official API provides data.

The goal is to let users retrieve their own Garmin training, workout, sleep and recovery data through a locally maintained MCP server for Claude Code and Codex.

## Confirmed decisions

- The server runs locally on macOS.
- Use MCP over stdio.
- Support both Claude Code and Codex through the same implementation.
- Use a Garmin Personal API Key.
- Access Garmin through its official Personal API.
- All Garmin operations must be read-only.
- Support a single personal Garmin account.
- Keep source code, credentials, configuration and any caches local.
- No cloud hosting, deployment, domain, HTTP server or remote authentication.
- No public publishing or package-registry upload.
- No database in the first version unless a concrete requirement justifies one.
- Internet access is still required for Garmin API requests.
- Retrieved data may be sent to the AI provider by the connected client; document this distinction.

Do not use unofficial Garmin endpoints, scraping, browser automation, or Garmin email/password authentication as a fallback.

## Preferred stack

- Python 3.12 or newer, subject to dependency requirements.
- Garmin’s official Python client:
  https://github.com/garmin/connect-personal-api-python
- Official MCP Python SDK, using its FastMCP interface.
- Pydantic for validation and structured response models where useful.
- uv for dependencies, the virtual environment and execution.
- pytest for tests.
- Ruff for linting and formatting.
- pyproject.toml and a committed uv lockfile.

Distinguish the official SDK’s FastMCP interface from the separately distributed FastMCP project. Prefer the official MCP SDK unless there is a specific reason to change.

Verify current package names, supported versions, SDK interfaces and Garmin client methods before implementation. Do not assume that examples in this brief are exact API signatures.

## First step: verify the integration

Read current official Garmin and MCP documentation and inspect Garmin’s official client.

Verify:
- Personal API key creation, expiry and revocation.
- Key-to-access-token exchange.
- Token lifetime, renewal and caching.
- Supported endpoints and response structures.
- Historical-data availability.
- Pagination and endpoint-specific date-range limits.
- Documented rate limits, if available.
- Data availability for the configured account and device.

Our current understanding is that the Personal API key is exchanged for a temporary access token and that Garmin’s Python client handles token caching. Validate this before coding.

Do not invent endpoints, SDK methods, response fields or data-access guarantees.

Produce a capability matrix with these statuses:
1. Confirmed by official documentation or source.
2. Implemented but requires live account verification.
3. Unsupported or unavailable.

If a requirement is unsupported, explain the limitation and continue with the supported scope.

## First-version MCP tools

Implement these tools where official API support is confirmed:

### list_activities
- Filter by date range and sport when supported.
- Use bounded pagination.
- Return activity identifiers and concise summaries.
- Include available duration, distance, pace/speed, heart rate and power metrics.
- Report whether more results are available.

### get_activity
- Retrieve an activity by identifier.
- Include available summary metrics and laps/splits.
- Make detailed samples and GPS data opt-in.
- Do not assume every sport has the same fields.

### get_sleep
- Retrieve sleep information for a supported date or date range.
- Include available duration, stages, score and timing.
- Clearly distinguish missing data from zero.

### get_hrv
- Retrieve available HRV measurements or summaries.
- Include reported baseline/status only when provided by Garmin.
- Explain whether dates represent the sleep start date or wake date.

### get_daily_summary
- Retrieve supported daily wellness metrics.
- Include steps, resting heart rate, stress and Body Battery only where officially available.
- Explain unavailable fields rather than substituting unrelated values.

Investigate training load, training readiness and other recovery metrics, but include them only if the official Personal API supports them.

Do not create a generic arbitrary-URL or arbitrary-endpoint tool.

## Tool contracts and output

- Define precise input and output schemas.
- Use ISO dates: YYYY-MM-DD.
- Validate dates, date ordering, identifiers and request sizes.
- Use America/Vancouver as the configurable default timezone.
- Document how Garmin timestamps and calendar dates are interpreted.
- Document units and normalize them consistently where appropriate.
- Preserve meaningful distinctions between null, absent and zero values.
- Return structured, compact, model-readable data.
- Avoid returning unbounded raw upstream payloads.
- Make large sample arrays and location data explicitly opt-in.
- Never silently truncate results.
- Include retrieval timestamps and relevant request-period information.
- Mark tools with accurate MCP read-only and other supported annotations.

Keep Garmin-reported values distinct from our own calculations. Do not invent readiness scores or medical conclusions.

If adding derived metrics, document their formulas, source data and limitations.

## Authentication and local credentials

Use a Personal API Key only.

Provide a local setup command that:
- Accepts the key through a hidden terminal prompt.
- Saves it outside the repository in an appropriate user configuration directory.
- Restricts file permissions to the current user on macOS.
- Never echoes the key.

An environment variable may be supported as an optional override. Document its precedence.

Reuse Garmin’s official authentication and token cache functionality where practical. Inspect its behavior first, including file permissions and concurrent access.

Ensure:
- No secrets in source control, examples, logs, tracebacks or tool responses.
- Credentials are never passed as MCP tool arguments.
- No API key is placed in a registration command or shell-history example.
- Token renewal and stale-token recovery are bounded.
- Concurrent calls do not corrupt credential/cache files.
- Missing, revoked and expired credentials produce actionable errors.
- Authentication prompts never block an MCP tool invocation; setup happens separately.

Do not request real API keys in chat.

## Reliability

- Configure request timeouts.
- Respect documented API limits and Retry-After.
- Use bounded retries for suitable transient failures.
- Avoid infinite authentication or retry loops.
- Distinguish invalid inputs, missing data, authentication failures, rate limiting, network failures and upstream errors.
- Handle partial results explicitly.
- Bound date ranges, pagination and response sizes.
- Use a small cache only where useful and document freshness.
- Keep stdout exclusively for MCP protocol messages.
- Send redacted diagnostics to stderr.
- Ensure blocking Garmin client calls do not unnecessarily block the MCP runtime.
- Shut down cleanly when the client stops the server.

## Architecture

Keep the design small and understandable. Separate:
- Configuration and credential handling.
- Garmin client adapter.
- Validation and response models.
- MCP tool definitions.
- Process entry point.

Prefer dependency injection sufficient to test Garmin failures without making live calls. Avoid unnecessary abstraction and infrastructure.

Expose one local executable entry point, such as `garmin-mcp`, that both AI clients can launch.

Use absolute paths in installation examples so execution works from any working directory.

## Validation

Write meaningful tests using synthetic, clearly labeled fixtures.

Cover:
- Input validation and date boundaries.
- Timezone interpretation.
- Pagination and output limits.
- Missing and partial data.
- Unit normalization.
- Authentication expiry and failures.
- Rate limits, timeouts and upstream errors.
- Secret redaction.
- MCP initialization, tool discovery and at least one complete tool invocation.

Run an actual stdio MCP smoke test, not only direct Python function tests.

Make live Garmin checks a separate, explicitly documented verification step after I configure credentials locally. Do not claim live validation when only fixtures were tested.

## Documentation and installation

Provide a README containing:
- Purpose and scope.
- Architecture and tool list.
- Supported metrics and known limitations.
- Python and uv prerequisites.
- Local installation and credential setup.
- Exact Claude Code registration and verification commands.
- Exact Codex registration and verification commands.
- Instructions for updating and removing the integration.
- Troubleshooting.
- Credential storage and privacy behavior.
- A statement that the project is unofficial and not affiliated with Garmin.

Verify registration commands against current official client documentation. Both clients should launch the same server implementation.

Do not create public repositories, push code, publish packages or deploy services.

## Example user requests

The completed integration should support questions such as:
- “Compare my last three runs.”
- “Summarize my cycling workouts from the last two weeks.”
- “How has my sleep changed over the last month?”
- “Show my HRV trend alongside my recent training.”
- “What were my splits and heart-rate changes in this workout?”
- “Summarize my training consistency over the supported period.”

These are examples of client-side analysis. The MCP should primarily supply accurate data rather than embed an AI coaching system.

## Working process and deliverables

First inspect the workspace and any repository instructions.

Then:
1. Verify official documentation and SDK capabilities.
2. Present a concise architecture, capability matrix and implementation plan.
3. Proceed with implementation using the decisions above.
4. Run relevant tests and the stdio smoke test.
5. Provide installation instructions and both client configurations.
6. Clearly list account-dependent checks and anything not yet verified.

Use reasonable defaults and continue without repeated confirmation. Ask only when a missing decision materially changes the design or blocks progress.

Success means users can configure their Garmin Personal API Key locally, register the server in either Claude Code or Codex, and retrieve supported Garmin data through standard read-only MCP tools without hosting or publishing anything.
