from __future__ import annotations

import json
import threading
import urllib.request
from http.server import HTTPServer

import pytest

from tests.helpers import make_run
from pitlane.dashboard.server import DashboardHandler


_SERVER_TEST_RESULTS = {
    "claude-baseline": {
        "task-1": {
            "metrics": {"weighted_score": 90.0, "assertion_pass_rate": 100.0},
            "assertions": [{"name": "check", "passed": True, "message": ""}],
            "all_passed": True,
        }
    }
}


@pytest.fixture
def runs_dir(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    make_run(runs, "run1", "2026-01-15T10:00:00+00:00", _SERVER_TEST_RESULTS)
    make_run(runs, "run2", "2026-02-15T10:00:00+00:00", _SERVER_TEST_RESULTS)
    return runs


@pytest.fixture
def server_url(runs_dir):
    """Start a test server on a random port and yield its base URL."""
    handler = type("TestHandler", (DashboardHandler,), {"runs_dir": runs_dir})
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_root_returns_html(server_url):
    req = urllib.request.Request(server_url + "/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "text/html" in content_type
        body = resp.read().decode()
        assert "Pitlane Trends" in body


def test_api_runs_returns_json(server_url):
    req = urllib.request.Request(server_url + "/api/runs")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "application/json" in content_type
        data = json.loads(resp.read())
        assert "runs" in data
        assert "meta" in data
        assert data["meta"]["total_runs"] == 2


def test_api_runs_with_date_filter(server_url):
    req = urllib.request.Request(server_url + "/api/runs?from=2026-02-01")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
        assert data["meta"]["total_runs"] == 1
        assert data["runs"][0]["run_id"] == "run2"


def test_api_runs_structure(server_url):
    req = urllib.request.Request(server_url + "/api/runs")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
        run = data["runs"][0]
        assert "run_id" in run
        assert "timestamp" in run
        assert "suites" in run
        suite = run["suites"][0]
        assert "assistant" in suite
        assert "task" in suite
        assert "weighted_score" in suite


def test_unknown_path_returns_404(server_url):
    req = urllib.request.Request(server_url + "/nonexistent")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 404


def test_api_runs_empty_dir(tmp_path):
    """Server with empty runs dir returns zero runs."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    handler = type("TestHandler", (DashboardHandler,), {"runs_dir": empty_dir})
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/runs")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            assert data["meta"]["total_runs"] == 0
            assert data["runs"] == []
    finally:
        httpd.shutdown()
