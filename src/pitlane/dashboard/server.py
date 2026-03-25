from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from jinja2 import Environment, FileSystemLoader

from pitlane.dashboard.scanner import scan_runs

_tmpl_dir = Path(__file__).parent.parent / "reporting" / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_tmpl_dir)), autoescape=True)


class DashboardHandler(BaseHTTPRequestHandler):
    """Request handler for the trends dashboard."""

    runs_dir: Path  # set via subclass before starting server

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._serve_html()
        elif path == "/api/runs":
            self._serve_runs_api(parsed.query)
        else:
            self.send_error(404)

    def _serve_html(self) -> None:
        template = _jinja_env.get_template("trends.html.j2")
        html = template.render(runs_dir=str(self.runs_dir))
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_runs_api(self, query_string: str) -> None:
        params = parse_qs(query_string)
        date_from = params.get("from", [None])[0]
        date_to = params.get("to", [None])[0]

        runs = scan_runs(self.runs_dir, date_from=date_from, date_to=date_to)

        all_assistants: set[str] = set()
        all_tasks: set[str] = set()
        for r in runs:
            all_assistants.update(r.assistants)
            all_tasks.update(r.tasks)

        payload = {
            "runs": [r.to_dict() for r in runs],
            "meta": {
                "total_runs": len(runs),
                "all_assistants": sorted(all_assistants),
                "all_tasks": sorted(all_tasks),
            },
        }

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Suppress default stderr logging
        pass


def start_server(runs_dir: Path, port: int = 8095, open_browser: bool = True) -> None:
    """Start the trends dashboard HTTP server."""
    handler = type("Handler", (DashboardHandler,), {"runs_dir": runs_dir})
    server = HTTPServer(("127.0.0.1", port), handler)

    url = f"http://127.0.0.1:{port}"
    print(f"Trends dashboard: {url}")
    print(f"Scanning runs in: {runs_dir.resolve()}")
    print("Press Ctrl+C to stop.")

    if open_browser:
        import webbrowser

        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server.")
    finally:
        server.server_close()
