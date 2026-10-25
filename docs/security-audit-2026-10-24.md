# Local Garmin MCP security audit

Date: 2026-10-24 (America/Vancouver).
Scope: the entire current application, tests, pyproject/lockfile, documentation,
fresh distribution builds, and credential-file permission metadata. Includes the
committed implementation at 32fd936 and current uncommitted documentation/license
changes, plus the subsequent logging remediation and current-tree privacy cleanup.
This report is not publication approval.

## Result

**One low-severity finding was confirmed and has been remediated.** No
critical/high-severity vulnerability was identified in this scoped review. This is not a guarantee that
all vulnerabilities have been found.

An independent security reviewer inspected the full implementation and reproduced
the finding; the primary reviewer independently reproduced it. Subsequent remediation
changed the logging boundary and added regression tests. The independent reviewer
checked the fix and reported no remaining important issue in the current changes.

## Threat model

One personal account on macOS; trusted local MCP client starts the server over
stdio. There is no HTTP listener, public endpoint or multi-user account boundary.
Requests go to Garmin over HTTPS; activity names and upstream responses are
untrusted data. Relevant risks are accidental secret disclosure, malicious or
malformed inputs, credential handling, network redirection, dependency compromise,
and accidental distribution of private files.

Malware already running as the same macOS user, root access and a compromised
client can generally read the user's files/environment. Mode 600 and local stdio
do not provide isolation against those actors.

## Finding SEC-001 — malformed protocol input can leak to diagnostic logs

Severity: **Low / P3**. Status: **remediated; regression tests pass**.

Original locations (before remediation):
- `src/garmin_training_mcp/server.py:85-86`: suppresses the named `mcp` logger.
- `src/garmin_training_mcp/__main__.py:70`: installs a root stderr logging handler.
- Installed official SDK `mcp/shared/session.py`: protocol validation invokes
  root `logging.warning` with an interpolated Pydantic validation exception.

The tool wrapper sanitizes tool-level validation failures. However, protocol-level
validation happens earlier, so setting the `mcp` logger level does not cover the
SDK's root-logger warning. A malformed request can write supplied input to stderr.

Reproduction used only a synthetic temporary configuration and a fake marker,
without loading real credentials or calling Garmin. After successful MCP
initialization, send:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_sleep","arguments":"SYNTHETIC-SECRET-AUDIT"}}
```

Observed before remediation:
- Server rejects the request with JSON-RPC error `-32602`.
- The protocol error response does not include the fake secret.
- The server's stderr does include `SYNTHETIC-SECRET-AUDIT` in the SDK validation warning.

Preconditions: sensitive data is supplied in a malformed protocol message, and
stderr is observed or persisted by the client. This does **not** independently
read or disclose the saved Personal API Key or bearer-token cache. Severity is low
because the only interface is an already-authorized local stdio client.

Implemented remediation: `_PrivateDiagnostics` filters the root logging handlers
installed when creating the server. Non-application messages are replaced with a
fixed diagnostic, and exception/stack fields are removed. Application diagnostics
retain only the fixed error codes emitted by the tool boundary. No SDK source was
modified.

Three real-stdio regression cases cover malformed requests, malformed notifications
and invalid JSON. The request and notification cases leaked the synthetic marker
before the fix; all cases pass afterward. Each case verifies that the marker is
absent from stderr and protocol output, then exercises discovery and a normal tool
call to verify continued service and safe diagnostics.

## Verified controls

- Credentials are accepted through a separate hidden setup prompt or the supported
  environment variable; no credential MCP argument is defined. Hidden-input failure
  aborts instead of falling back to echoing input.
- Metadata-only inspection of the current machine: Codex user config mode 600;
  Garmin credential directory 700; saved key and token cache 600. All checked
  objects are owned by the current user and are not symlinks. Their contents were
  not read. POSIX mode checks do not constitute a full macOS ACL/backup audit.
- Credential/cache operations use a bounded cross-process lock. Key and token
  replacement are atomic; temporary files have private modes. Existing symlinked,
  nonregular, wrong-owner or permissive credential files are rejected.
- HTTP origin is fixed to `https://personal.connectapi.garmin.com`; arbitrary SDK
  origin overrides are rejected. Redirects and environment proxies/netrc are disabled.
  Default Requests TLS verification is retained. No HTTP listener is started.
- Data operations are allowlisted SDK GET methods. The only application POST is
  official authentication. No arbitrary endpoint tool, shell execution, eval,
  pickle deserialization or dynamic code execution was identified in production source.
- IDs, sport keys, dates, ordering, date ranges, offsets and page sizes are validated.
  Tool arguments cannot turn IDs into paths or choose a destination URL.
- Network timeouts, a socket-interrupting response-body deadline, a 4 MiB decoded-body
  cap, bounded retries, Retry-After handling and a single stale-token refresh limit
  the request work. These are not a process-wide resource quota or a hard total
  deadline for the entire handshake/header/retry lifecycle.
- Allowlisted response models omit raw upstream payloads and coordinates. Structured
  output is capped at 128 KiB, with explicit errors instead of silent truncation.
  Error responses and ordinary tool diagnostics use fixed messages/codes; SEC-001
  identified the earlier protocol-validation gap, now covered by root-handler redaction.
- Untrusted activity names are returned as data, and server instructions tell the
  client to treat them that way. No server-side execution of names is performed.
  This is not a guarantee against prompt injection in a consuming AI client.

## Dependency advisory check

Tool: **PyPA pip-audit 2.10.1**, default PyPI advisory service.
Input: all runtime dependencies exported from the committed `uv.lock`, selected
for the current macOS/Python 3.13 environment; dev/build tools and the unpublished
first-party project were excluded. Only public dependency names and versions were
submitted to the advisory service; no source, credentials or health data was submitted.

Result: **33 dependencies audited, 0 known vulnerabilities, 0 skipped packages**.
Includes `mcp==1.30.0`, `garmin-connect-personal-api-python==1.0.0`,
`requests==2.34.2`, `urllib3==2.8.0`, and `pydantic==2.14.1`.
The separately cached uvx environment exercised during this audit reports the same
runtime versions (normalizing distribution-name punctuation/case).

Reproduction commands (replace temporary output paths as desired):

```sh
UV_CACHE_DIR=/tmp/garmin-mcp-uv-cache uv export --locked --offline --no-dev --no-emit-project --no-hashes --format requirements-txt --output-file /private/tmp/garmin-security-requirements.txt
uvx --python 3.13 pip-audit --disable-pip --no-deps --progress-spinner off --requirement /private/tmp/garmin-security-requirements.txt --format json
```

No-known-advisory is not a source-code audit of every dependency and does not exclude
undisclosed vulnerabilities or malicious packages. `uvx --from` does not enforce the
project lockfile; reassess the actual environment after dependency refreshes.
See [pip-audit's documentation](https://github.com/pypa/pip-audit).

## Repository and package inspection

- Reviewed the application/test code and current documentation/license changes.
- Targeted private-key-block and literal Garmin-key-assignment scans over the 24
  current Git/current-source files found no unexpected matches. Example keys are
  placeholders or explicitly synthetic test values. This was a targeted scan,
  not a comprehensive secret detector over Git history or the user's disk.
- Fresh offline wheel and source-distribution builds succeeded. The wheel contains
  14 files, limited to application package/metadata; the source distribution contains
  26 files after the remediation report was added. No `.codex/`, client `config.toml`, `.env`, bearer-token or Personal API Key
  filenames were present. MIT license inclusion was verified in the preceding
  precommit check and remains configured in the package metadata.
- **50 tests passed after remediation**, including real stdio subprocesses, key/environment precedence,
  file permissions/symlinks, thread/process locking, authentication/retries,
  bounded response reads and safe tool-argument errors. Ruff lint/format checks pass.
  The suite now includes the three malformed-protocol regression cases for SEC-001.

## Operational privacy and limitations

Environment-variable configuration puts the Personal API Key in the user's local
Codex config as plaintext. That file currently has mode 600. The token cache is
also plaintext with mode 600. Backups, same-user programs, root and the trusted MCP
client remain inside the trust boundary; this is not Keychain-backed storage.

The server is read-only with respect to Garmin data and runs locally. Retrieved
health data may be sent to the connected model provider and retained in client
history. No Garmin requests were made during this security audit, and saved secret
contents were not inspected. No package was published, repository pushed, settings
changed. Logging remediation and documentation/privacy cleanup were performed only
in the local checkout.

No other confirmed security blocker for the stated local deployment was identified
by this review. This is scoped evidence, not proof that every possible diagnostic
path or dependency is free of vulnerabilities.

## Personal-data and Git-history follow-up

The current requirements brief and capability matrix were generalized to remove
personal background, device ownership and training context. The README uses generic
installation paths. Additional ignore rules cover saved keys, token caches, lock
files, project-local MCP client configurations and build output. Targeted scans of
the current source found no personal home paths, email addresses, former personal
profile details, or known live activity identifiers/location/metric fingerprints.
Credentials and health records were not read to perform these checks. Public MIT
author attribution remains intentionally present.

**The original development history is not cleared for public sharing.** Historical
blobs contain former personal profile details and a personal home path, and earlier
author/committer metadata uses a non-noreply email address. Those values are not
reproduced here. Removing them from current files does not erase old commits.

For GitHub publication, use a clean root commit containing only the sanitized source
tree, with GitHub noreply authorship and no original development commits as parents.
Preserve the original history only in a private local recovery bundle under `.git`,
which is not part of the source tree, package builds or the published branch. Replacing
an existing remote branch requires explicit approval and a lease against its checked
head. A branch rewrite does not guarantee removal of previously published metadata
from GitHub caches or existing copies.

No credentials or recorded health data are required for publication. Public MIT
author attribution and generic project documentation intentionally remain. Distribution
builds do not include `.git` history. The audit and remediation themselves made no
pushes or publication changes; publication is a separate explicitly requested action.
