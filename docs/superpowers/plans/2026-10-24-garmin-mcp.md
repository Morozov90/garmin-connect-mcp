# Garmin Training MCP Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. The user's brief authorizes continuous execution without repeated confirmation.

**Goal:** Retrieve documented Garmin data through five read-only local stdio tools.
**Architecture:** Official Garmin SDK adapter, typed projections and bounded service operations behind official MCP FastMCP.
**Tech Stack:** Python >=3.12, uv, mcp==1.30.0, garmin-connect-personal-api-python==1.0.0, Pydantic, pytest, Ruff.
**Spec:** docs/superpowers/specs/2026-10-24-garmin-design.md

## Global Constraints
Local Mac only; Personal API Key only; no secrets in repository or logs; no arbitrary URLs;
no publishing/pushing; no live tests without locally configured credentials.

## Review Focus
- Empty env override must fail rather than use another key (task 1).
- SDK override/redirect must never send a key elsewhere (task 2).
- Null, absent and zero must remain distinct (task 3).
- Full page must expose a next offset rather than claim completion (task 3).
- MCP validation errors must not echo submitted secrets (task 4).

### Task 1: Configuration and credential setup
Files: pyproject.toml, .gitignore, src/garmin_training_mcp/config.py, tests/test_config.py.
Interface: Settings.from_env(); credential_lock(settings); read_key(settings); save_key(settings, key).
- [x] Write failing tests for hidden setup, local paths, permissions, blank overrides and locking.
- [x] Run pytest tests/test_config.py, verify missing implementation, implement and rerun.

### Task 2: Official Garmin adapter
Files: adapter.py, tests/test_adapter.py.
Interface: GarminAdapter(settings, session_factory=...).call(method, *args, **kwargs), close().
- [x] Write failing HTTP boundary tests for auth cache/renewal, 401, timeout, rate limits,
  JSON/body errors, forbidden origin override, redirects and atomic cache writes.
- [x] Implement bounded HTTP Session and official-client adapter; run focused and full tests.

### Task 3: Validated contracts and service
Files: models.py, normalize.py, service.py, tests/test_service.py.
Interface: TrainingService(adapter, settings) exposes the five tool names returning ToolResponse.
- [x] Test invalid dates/IDs, ranges, pagination, units, timezone, missing/partial records,
  unsupported sample/location requests and payload limits with synthetic Swagger-shaped data.
- [x] Implement allowlisted mapping and range operations; run focused and full tests.

### Task 4: MCP and executable
Files: server.py, __main__.py, tests/stdio_fixture_server.py, tests/test_stdio.py.
Interface: create_server(service); garmin-mcp [serve|setup|check].
- [x] Test real subprocess MCP initialization/discovery/output schemas, successful fixture
  invocation, invalid inputs, missing credentials, safe error content and clean EOF shutdown.
- [x] Implement FastMCP tools with read-only annotations and worker-thread calls.
- [x] Run full pytest, ruff check, ruff format --check and locked dependency sync.

### Task 5: Documentation and verification
Files: README.md, docs/capabilities.md, uv.lock.
- [x] Document exact source-backed capabilities/limits, auth behavior, local installation,
  both client registrations/removal, privacy and separate live-account checklist.
- [x] Verify CLI help and executable from unrelated cwd, review complete diff and rerun checks.

## Execution ledger
- Research: blank repository, clean main; no ticket supplied, no branch created.
- Ruling: preserve the existing local checkout and make a local commit including uv.lock,
  as the brief requests a committed lockfile. No new branch is named because no ticket ID
  was supplied. No remote operations or client registrations are performed.
- SDK/API interfaces inspected before implementation. No live Garmin requests made.

- Task 1: complete — private storage, hidden prompt, empty-override and thread/process locking tests pass.
- Task 2: complete — real official SDK exercised through synthetic HTTP; cache renewal,
  one 401 refresh, retries, rate limits, origin guard, size cap and body interruption tested.
- Task 3: complete — all five projections, strict validation, pagination, missing/null/zero,
  historical DST, range boundaries and empty activity handling tested.
- Task 4: complete — actual stdio subprocess discovery, all five fixture calls, safe errors,
  credential-free production startup and transport cleanup tested.
- Task 5: complete — capability matrix/README include official links and both client commands;
  checked installed CLI help and ran executable successfully from /private/tmp.
- Independent Superpowers review found two issues: getpass echo fallback and slow streaming
  body deadline. Both regression tests failed first and passed after fixes. Reviewer checked
  the fixes and reported no remaining important issue.
- Ruling: Vancouver 2026 DST assumption was invalid for the installed IANA database.
  Use a 2025 historical overlap to test offset conversion, retaining system zone behavior.
- Final verification: Python 3.13, 47 pytest tests pass; Ruff lint and format checks pass;
  uv lock --check --offline and uv sync --locked --offline pass; git diff --check passes.
- Still unverified: actual Garmin account/device data, history/units/date association,
  key expiry/revocation behavior on Garmin, and live invocations from registered AI clients.
