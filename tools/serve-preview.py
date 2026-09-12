"""Local-only static preview. No leads are stored or sent to the business API."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
import gzip
import json
import os
from urllib.parse import urlsplit

DIST = Path(__file__).resolve().parents[1] / "dist"


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def log_message(self, format, *args):
        pass

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # Browser navigation may cancel an image response.

    def guess_type(self, path):
        if Path(path).suffix == "":
            return "text/html; charset=utf-8"
        return super().guess_type(path)

    def send_head(self):
        """Compress text responses like the CDN does, so a local measurement is comparable with
        production instead of counting uncompressed HTML/CSS/JS against the page."""
        path = self.translate_path(self.path)
        p = Path(path)
        if p.is_dir():
            if not self.path.endswith("/"):
                return super().send_head()          # let the base class issue the redirect
            index = p / "index.html"
            if not index.is_file():
                return super().send_head()
            p, path = index, str(index)
        ctype = self.guess_type(path)
        compressible = ctype.split(";")[0] in {
            "text/html", "text/css", "application/javascript", "text/javascript",
            "application/json", "image/svg+xml", "text/plain", "application/xml", "text/xml",
        }
        if not (compressible and "gzip" in self.headers.get("Accept-Encoding", "") and p.is_file()):
            return super().send_head()
        try:
            body = gzip.compress(p.read_bytes(), 6)
        except OSError:
            return super().send_head()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        return BytesIO(body)

    def do_POST(self):
        # Consume the body without logging or retaining personal data.
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        path = urlsplit(self.path).path
        if path == "/api/fx/event":
            status, body = 200, {"ok": True, "preview": True, "written": 0}
        elif path == "/api/fx/lead":
            status, body = 503, {"ok": False, "error": "preview_only", "message": "Local preview does not submit enquiries."}
        else:
            status, body = 404, {"ok": False, "error": "not_found"}
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    if not (DIST / "index.html").is_file():
        raise SystemExit("Run python build.py first.")
    # Порт — з PREVIEW_PORT (типово 4173); на ace-main — 8007, порт ALUMA з ~/maestro/PORTS.md.
    port = int(os.environ.get("PREVIEW_PORT", "4173"))
    print(f"Furniture preview: http://127.0.0.1:{port} (lead submission disabled)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), PreviewHandler).serve_forever()
