# Garmin Training MCP

Read your Garmin activities, sleep, HRV and daily health summaries in Codex or
Claude Code. The server runs locally on macOS and uses Garmin's official Python
client and the official MCP Python SDK.

This project is unofficial and is not affiliated with Garmin.

## Install

You need macOS, Python 3.12 or newer, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and a Garmin Connect Personal API Key. The examples use Python 3.13.

Check that the [PyPI package](https://pypi.org/project/garmin-training-mcp/) launches:

```sh
uvx --python 3.13 --from garmin-training-mcp==0.1.1 garmin-mcp --help
```

You don't need to clone the repository. `uvx` downloads the package and dependencies
on first launch, then uses its cache. `garmin-training-mcp` is the package name;
`garmin-mcp` is the command it provides.

## Connect your client

Create a key on the [Garmin Personal API Key page](https://connect.garmin.com/app/settings/personalApiToken).
Replace `YOUR_GARMIN_PERSONAL_API_KEY` below with your key in your local configuration.
Keep it out of Git, chat messages and shared examples.

### Codex

Add this entry to `~/.codex/config.toml`, or update the existing `garmin-training` entry:

```toml
[mcp_servers.garmin-training]
command = "uvx"
args = ["--python", "3.13", "--from", "garmin-training-mcp==0.1.1", "garmin-mcp"]

[mcp_servers.garmin-training.env]
GARMIN_PERSONAL_API_KEY = "YOUR_GARMIN_PERSONAL_API_KEY"
```

Codex allows 60 seconds per tool call by default. If Garmin calls time out, add
`tool_timeout_sec = 180` under `[mcp_servers.garmin-training]`, before the `.env`
table. See the [Codex timeout settings](https://learn.chatgpt.com/docs/extend/mcp#other-configuration-options).

### Claude Code and other JSON clients

Add this entry under `mcpServers` in your client's configuration.
Claude Code uses `~/.claude.json` for user settings.

```json
{
  "mcpServers": {
    "garmin-training": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--python", "3.13",
        "--from", "garmin-training-mcp==0.1.1",
        "garmin-mcp"
      ],
      "env": {
        "GARMIN_PERSONAL_API_KEY": "YOUR_GARMIN_PERSONAL_API_KEY"
      }
    }
  }
}
```

If your client can't find `uvx`, run `command -v uvx` in Terminal and use the full
executable path as `command`. Keep the package name in `args` as shown.

Fully quit and reopen your client, then try:

> Use Garmin to compare my last two runs. What was my average pace?

> Use Garmin to summarize my sleep from the last seven days.

Check the results against Garmin Connect. `--help` confirms installation;
a successful Garmin tool call confirms authentication.

### Save the key in a separate file

If you prefer to keep the key out of client configuration, run:

```sh
uvx --python 3.13 --from garmin-training-mcp==0.1.1 garmin-mcp setup
```

The prompt hides your input and saves the key to:

```text
~/Library/Application Support/garmin-training-mcp/personal-api-key
```

Use the client examples above with the `env` block or `.env` table removed.
An environment key overrides this file; an empty value is an error.

## Available tools

| Tool | Returns |
| --- | --- |
| `list_activities` | Activities in a date range, with distance, duration, speed, HR and power where available |
| `get_activity` | Activity metrics and a page of split summaries |
| `get_sleep` | Sleep duration, stages, scores and timestamps |
| `get_hrv` | Overnight and weekly HRV summaries, baseline and status |
| `get_daily_summary` | Steps, resting HR, stress and Body Battery |

Fields depend on what Garmin provides for your account and device. Missing data
isn't zero. Split summaries may group several splits. GPS tracks, detailed samples
and training readiness are unavailable in v1.

Dates use Garmin's calendar dates. Wellness queries accept up to 31 days;
activity queries accept up to 366 days. The server returns speed in meters/second,
which the AI client can convert to pace. See the [capability matrix](docs/capabilities.md)
for coverage and the [reference](docs/reference.md#dates-units-and-output-semantics)
for units, date handling and pagination.

## Privacy

The server reads Garmin data and caches bearer tokens locally. It writes no health
data files or telemetry. Keys and tokens are stored as plaintext with owner-only
permissions, outside the repository. The credential directory has mode `700` and
its files have mode `600`. Keys in client configuration also need restricted access.

Your AI client can send retrieved health data to its provider and retain it in chat
history. Local backups or sync tools may also copy credential files. Review your
client's privacy settings. See the [security audit](docs/security-audit-2026-10-24.md)
for the reviewed controls and limitations.

## Test and troubleshoot

For a live check, choose a date with synced activity and wellness data:

```sh
uvx --python 3.13 --from garmin-training-mcp==0.1.1 garmin-mcp check --date YYYY-MM-DD
```

The check prints availability counts and statuses. It needs a saved key file or a
key available in Terminal; Terminal doesn't inherit a key from your client's `env` block.
An empty date result can mean there is no data for that day.

| Problem | What to check |
| --- | --- |
| Server won't start | Run `--help`, check the `uvx` executable path, then restart the client. |
| `missing_credentials` | Set the key in client configuration or run `setup`. |
| `authentication` | Replace an expired or revoked key, then restart. |
| `rate_limited` | Wait for the reported retry delay before trying again. |
| Missing records | Check the date and Garmin Connect sync status. |

The [reference](docs/reference.md#troubleshooting) covers all error codes.

## Updates and development

To upgrade, change the version in your client's `args`, run `--help` with that
version, and restart the client. Keep your existing credentials.

For local development, locked dependencies, tests and removal instructions, see
[the reference](docs/reference.md#install-with-the-project-lockfile).
`uvx` resolves dependencies separately from the project's `uv.lock`.

## License

[MIT](LICENSE). Dependencies retain their own licenses.
