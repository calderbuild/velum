"""Review interface: python -m velum serve. Standard library only, no outside requests from the page."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import anonymize_document, from_dicts, review
from .anonymize import available_packs, load_pack
from .llm import LLMError

STATIC = Path(__file__).parent / "static"
MAX_BODY = 4_000_000


class Handler(BaseHTTPRequestHandler):
    results = Path("out/demo")

    def do_GET(self):
        if self.path == "/":
            return self.send(
                200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8"
            )
        if self.path == "/api/cases":
            packs = [
                {"id": p, "title": load_pack(p)["title"]} for p in available_packs()
            ]
            return self.json(
                200,
                {"cases": [_brief(c) for c in self.cases().values()], "packs": packs},
            )
        if self.path.startswith("/api/case/"):
            case = self.cases().get(self.path.removeprefix("/api/case/"))
            if case:
                return self.json(200, case)
        self.json(404, {"error": "No such page."})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self.json(
                413, {"error": "The decision is too long for one request (4 MB)."}
            )
        body = json.loads(self.rfile.read(length) or b"{}")
        if body.get("pack") not in available_packs():
            return self.json(400, {"error": "Unknown rule pack."})
        if self.path == "/api/anonymize":
            if not body.get("text", "").strip():
                return self.json(400, {"error": "Paste the text of a decision first."})
            try:
                result = anonymize_document(
                    body["text"],
                    body.get("language", ""),
                    body["pack"],
                    body.get("legal_area", ""),
                )
            except (
                LLMError,
                SystemExit,
            ) as e:  # config() exits with a message when no endpoint is set
                return self.json(502, {"error": f"Apertus could not be reached: {e}"})
            return self.json(
                200,
                result
                | {"id": "pasted", "docket": body.get("title") or "Pasted decision"},
            )
        if self.path == "/api/review":
            mentions = from_dicts(body["mentions"])
            return self.json(
                200,
                review(
                    body["original"],
                    body["language"],
                    body.get("legal_area", ""),
                    body["pack"],
                    mentions,
                    body["reader"],
                ),
            )
        self.json(404, {"error": "No such endpoint."})

    def cases(self):
        found = (
            json.loads(p.read_text()) for p in sorted(self.results.glob("*.velum.json"))
        )
        return {c["id"]: c for c in found if "id" in c}

    def json(self, status, data):
        self.send(
            status,
            json.dumps(data, ensure_ascii=False).encode(),
            "application/json; charset=utf-8",
        )

    def send(self, status, body, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep decision text and paths out of the console
        pass


def _brief(case):
    return {
        k: case.get(k, "")
        for k in ("id", "docket", "court", "language", "decision_date", "pack")
    }


def serve(host, port, results):
    Handler.results = Path(results)
    print(f"Velum review: http://localhost:{port}  (Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
