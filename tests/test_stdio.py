"""Actual subprocess stdio tests. Fixture mode exists only in tests/stdio_fixture_server.py."""

import asyncio
import json
import os
import selectors
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def run_session(tmp_path, script, check):
    async def run():
        env = {k: v for k, v in os.environ.items() if not k.startswith("GARMIN_")}
        env["GARMIN_MCP_CONFIG_DIR"] = str(tmp_path / "config")
        params = StdioServerParameters(
            command=sys.executable, args=script, env=env, cwd=str(tmp_path)
        )
        with (tmp_path / "stderr.log").open("w+") as stderr:
            async with (
                stdio_client(params, errlog=stderr) as (read, write),
                ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session,
            ):
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "garmin-training-mcp"
                await check(session)
            stderr.seek(0)
            assert "SYNTHETIC-SECRET" not in stderr.read()

    asyncio.run(run())


def test_fixture_stdio_complete_flow_and_safe_errors(tmp_path):
    async def check(session):
        tools = (await session.list_tools()).tools
        assert {t.name for t in tools} == {
            "list_activities",
            "get_activity",
            "get_sleep",
            "get_hrv",
            "get_daily_summary",
        }
        for tool in tools:
            assert tool.annotations.readOnlyHint is True
            assert tool.annotations.openWorldHint is True
            assert tool.outputSchema is not None
        result = await session.call_tool(
            "list_activities", {"start_date": "2026-10-01", "end_date": "2026-10-24", "limit": 1}
        )
        assert not result.isError
        assert result.structuredContent["records"][0]["activity_id"] == "42"
        assert result.structuredContent["records"][0]["distance_m"] == 5000
        for name in ["get_sleep", "get_hrv", "get_daily_summary"]:
            result = await session.call_tool(name, {"start_date": "2026-10-01"})
            assert not result.isError
            assert result.structuredContent["records"][0]["calendar_date"] == "2026-10-01"
        result = await session.call_tool("get_activity", {"activity_id": "42"})
        assert not result.isError
        assert result.structuredContent["records"][0]["splits"][0]["distance_m"] == 1000
        for name, args in [
            ("get_activity", {"activity_id": "SYNTHETIC-SECRET"}),
            ("get_sleep", {"start_date": {"SYNTHETIC-SECRET": True}}),
            ("get_sleep", {"start_date": "2026-10-01", "key": "SYNTHETIC-SECRET"}),
            ("SYNTHETIC-SECRET", {}),
        ]:
            error = await session.call_tool(name, args)
            assert error.isError
            assert "SYNTHETIC-SECRET" not in error.model_dump_json()

    run_session(tmp_path, [str(ROOT / "tests/stdio_fixture_server.py")], check)


def test_production_stdio_discovers_without_credentials(tmp_path):
    async def check(session):
        assert len((await session.list_tools()).tools) == 5
        error = await session.call_tool("get_sleep", {"start_date": "2026-10-01"})
        assert error.isError
        assert "missing_credentials" in error.content[0].text

    run_session(tmp_path, ["-m", "garmin_training_mcp"], check)


def test_setup_refuses_noninteractive_input_without_echo(tmp_path):
    import subprocess

    env = {k: v for k, v in os.environ.items() if not k.startswith("GARMIN_")}
    env["GARMIN_MCP_CONFIG_DIR"] = str(tmp_path / "config")
    result = subprocess.run(
        [sys.executable, "-m", "garmin_training_mcp", "setup"],
        input="SYNTHETIC-SECRET",
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode != 0
    assert "SYNTHETIC-SECRET" not in result.stdout + result.stderr
    assert not (tmp_path / "config/personal-api-key").exists()


@pytest.mark.parametrize("malformed", ["request", "notification", "json"])
def test_malformed_protocol_never_logs_input_and_server_keeps_working(tmp_path, malformed):
    """Catch SDK root-logger leaks before the tool wrapper is reached."""
    marker = "SYNTHETIC-SECRET-PROTOCOL"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GARMIN_")}
    env["GARMIN_MCP_CONFIG_DIR"] = str(tmp_path / "config")
    with (tmp_path / "protocol-stderr.log").open("w+") as stderr:
        process = subprocess.Popen(
            [sys.executable, "-m", "garmin_training_mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            env=env,
            cwd=tmp_path,
            bufsize=0,
        )
        received = []

        def send(message):
            process.stdin.write((json.dumps(message) + "\n").encode())
            process.stdin.flush()

        def receive_until(request_id):
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                for _ in range(10):
                    assert selector.select(timeout=10), "MCP response timed out"
                    line = process.stdout.readline()
                    assert line, "MCP server exited unexpectedly"
                    received.append(line)
                    response = json.loads(line)
                    if response.get("id") == request_id:
                        return response
            pytest.fail("Expected MCP response was not returned")

        try:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "synthetic-security-test", "version": "1"},
                    },
                }
            )
            assert "result" in receive_until(1)
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            if malformed == "request":
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "get_sleep", "arguments": marker},
                    }
                )
                assert receive_until(2)["error"]["code"] == -32602
            elif malformed == "notification":
                send(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/progress",
                        "params": {"progressToken": marker, "progress": marker},
                    }
                )
            else:
                process.stdin.write(("{not-json-" + marker + "\n").encode())
                process.stdin.flush()
            send({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
            assert len(receive_until(3)["result"]["tools"]) == 5
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "get_sleep", "arguments": {"start_date": "2026-10-23"}},
                }
            )
            error = receive_until(4)["result"]
            assert error["isError"] is True
            assert "missing_credentials" in error["content"][0]["text"]
            process.stdin.close()
            assert process.wait(timeout=10) == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
        stderr.seek(0)
        diagnostics = stderr.read()
        assert marker not in diagnostics
        assert marker.encode() not in b"".join(received)
        assert "Tool failed: missing_credentials" in diagnostics
