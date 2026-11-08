#!/usr/bin/env python3
"""Shows Arnheim on this computer: run `python3 serve.py`, then open the address it prints.

It serves the page and its files from this folder to this computer only, and nothing else:
no other folders, no listings, nothing cached, so a change shows on the next reload.
Pass a port number to use another port: `python3 serve.py 8741`.
"""
import http.server
import os
import sys
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
SHOWN = ("src", "sample", "vendor")
TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jpg": "image/jpeg", ".hdr": "image/vnd.radiance",  # the real materials walk mode loads (vendor/polyhaven)
}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, *_args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def send_head(self):
        path = unquote(self.path.split("?", 1)[0].split("#", 1)[0])
        if path in ("/", "/index.html"):
            path = "/index.html"
        else:
            parts = path.split("/")[1:]
            if len(parts) < 2 or parts[0] not in SHOWN or any(p in ("", ".", "..") or p.startswith(".") for p in parts):
                self.send_error(404)
                return None
        full = os.path.realpath(os.path.join(ROOT, *path.split("/")[1:]))
        kind = TYPES.get(os.path.splitext(full)[1])
        if not kind or not full.startswith(ROOT + os.sep) or not os.path.isfile(full):
            self.send_error(404)
            return None
        handle = open(full, "rb")
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(os.fstat(handle.fileno()).st_size))
        self.end_headers()
        return handle


class Server(http.server.ThreadingHTTPServer):
    request_queue_size = 128  # one page load asks for about 25 files at once


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8740
    server = Server(("127.0.0.1", port), Handler)
    print(f"Arnheim is at http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
