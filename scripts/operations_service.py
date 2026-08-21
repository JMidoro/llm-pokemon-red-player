from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.operations import OperationsPaths, OperationsStore  # noqa: E402


class OperationsHandler(BaseHTTPRequestHandler):
    store: OperationsStore

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.write_json({"schema": "operations_health_v1", "status": "ok"})
            return
        if parsed.path in {"/", "/snapshot"}:
            self.write_json(self.store.snapshot())
            return
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) == 3 and parts[0] == "artifacts":
            run_id, kind = parts[1], parts[2]
            try:
                if kind == "summary":
                    self.write_json(self.store.summary_payload(run_id))
                    return
                path, content_type, filename = self.store.artifact_path(run_id, kind)
                self.write_file(path, content_type=content_type, filename=filename)
                return
            except (FileNotFoundError, ValueError) as exc:
                self.write_json({"error": str(exc)}, status=404)
                return
        self.write_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/control":
            self.write_json({"error": "not found"}, status=404)
            return
        try:
            body = self.read_json_body()
            result = self.store.command(str(body.get("action") or ""), source=str(body.get("source") or "operations_ui"))
            self.write_json(result, status=202)
        except (json.JSONDecodeError, ValueError) as exc:
            self.write_json({"error": "Unsupported or invalid control command.", "type": exc.__class__.__name__}, status=400)

    def read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("content-length", "0"))
        if length <= 0 or length > 16_384:
            raise ValueError("A small JSON body is required")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value

    def write_json(self, payload: dict[str, object], *, status: int = 200) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("x-content-type-options", "nosniff")
        self.send_header("content-length", str(len(encoded)))
        try:
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def write_file(self, path: Path, *, content_type: str, filename: str) -> None:
        size = path.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get("range")
        status = 200
        if range_header and range_header.startswith("bytes="):
            requested = range_header[6:].split(",", 1)[0]
            first, _, last = requested.partition("-")
            try:
                start = int(first) if first else 0
                end = int(last) if last else size - 1
            except ValueError:
                self.send_error(416)
                return
            if start < 0 or end < start or start >= size:
                self.send_error(416)
                return
            end = min(end, size - 1)
            status = 206
        length = max(end - start + 1, 0)
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-disposition", f'inline; filename="{filename}"')
        self.send_header("accept-ranges", "bytes")
        self.send_header("cache-control", "private, no-store")
        self.send_header("x-content-type-options", "nosniff")
        self.send_header("content-length", str(length))
        if status == 206:
            self.send_header("content-range", f"bytes {start}-{end}/{size}")
        try:
            self.end_headers()
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def log_message(self, format: str, *args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the private, sanitized Pokemon Player Operations API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--state-dir", default="research/artifacts/operations")
    parser.add_argument("--report-root", default="research/artifacts/local-gemma-chapter-runs")
    parser.add_argument("--dropbox-root", default="D:/Dropbox")
    parser.add_argument("--director-url", default="http://127.0.0.1:8765")
    parser.add_argument("--director-report-root", default="research/artifacts/llm-director-runs")
    parser.add_argument("--director-status-dir", default="research/artifacts/director-player")
    parser.add_argument("--supervisor-root", default="research/artifacts/segment-supervisor")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Operations service must bind to loopback; use the private access proxy for remote viewing.")
    dropbox_root = Path(args.dropbox_root).resolve() if args.dropbox_root else None
    store = OperationsStore(
        OperationsPaths(
            state_dir=(ROOT / args.state_dir).resolve(),
            report_root=(ROOT / args.report_root).resolve(),
            dropbox_root=dropbox_root,
            director_report_root=(ROOT / args.director_report_root).resolve(),
            director_status_dir=(ROOT / args.director_status_dir).resolve(),
            supervisor_root=(ROOT / args.supervisor_root).resolve(),
        ),
        director_url=args.director_url,
    )
    OperationsHandler.store = store
    server = ThreadingHTTPServer((args.host, args.port), OperationsHandler)
    print(f"Operations service listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
