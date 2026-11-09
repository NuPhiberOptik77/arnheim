#!/usr/bin/env python3
"""Shows Arnheim: run `python3 serve.py`, then open the address it prints.

  python3 serve.py          on this computer only, at http://127.0.0.1:8740
  python3 serve.py 8741     on another port
  python3 serve.py --lan    on phones and other computers on this network too (README, "Phones")
  python3 serve.py --control  and let the page talk to your Claude Code agents, answer their
                            permission requests, and start and stop them (docs/connect.md)

It serves the page and its files from this folder, and nothing else: no other folders, no
listings, nothing cached, so a change shows on the next reload. Your own company goes in data/
(README, "Make it yours"); without it, the page shows the made-up sample. It answers only to the
names it was opened by (127.0.0.1 and localhost, and with --lan an IP address or a name ending
.local), so a web page elsewhere can't read it by pointing a name of its own here.
It also answers /voice/, the voice the walk's people speak with, if this computer has one
(voice/bridge.py, and README, "Voice"), and with --control, /control/ (connect/control.py), only
to the page on this computer: never with --lan.
"""
import argparse
import errno
import http.server
import io
import ipaddress
import json
import os
import socket
import sys
from urllib.parse import unquote

from connect.control import Control
from voice.bridge import Voice

ROOT = os.path.dirname(os.path.realpath(__file__))  # links resolved, as every file below is
SHOWN = ("src", "sample", "vendor", "data")
TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jpg": "image/jpeg", ".hdr": "image/vnd.radiance",  # the real materials walk mode loads (vendor/polyhaven)
}
PORT_TAKEN = {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE)}


VOICE = Voice()


def host_ok(host, port, lan=False):
    """Whether a request's Host is a name this server answers to, with its port: 127.0.0.1 or
    localhost, and with --lan an address or a name ending .local. A page elsewhere can point a name
    of its own at this computer, but it can't make the browser send one of these."""
    name, colon, given = host.rpartition(":")
    if not colon or "]" in given:  # no port, or an IPv6 address with none
        name, given = host, ""
    if given != str(port) and not (port == 80 and given == ""):
        return False
    name = name.lower()
    if name in ("127.0.0.1", "localhost", "[::1]"):
        return True
    if not lan:
        return False
    if name.endswith(".local"):
        return True
    try:
        ipaddress.ip_address(name[1:-1] if name.startswith("[") else name)
    except ValueError:
        return False
    return True


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, *_args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def allowed(self):
        """A name this server answers to, and on a POST its own page (the Origin)."""
        host = self.headers.get("Host", "")
        if not host_ok(host, self.server.server_address[1], self.server.lan):
            return False
        return self.command != "POST" or self.headers.get("Origin") == f"http://{host}"

    def voice(self, path, body=b""):
        code, kind, data, extra = VOICE.handle(self.command if self.command != "HEAD" else "GET", path[len("/voice/"):], body)
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        for name, value in extra.items():
            self.send_header(name, value)
        self.end_headers()
        return io.BytesIO(data)

    def control(self, path, body=b""):
        """/control/: off unless serve.py was started with --control, and then only for this computer."""
        method = self.command if self.command != "HEAD" else "GET"
        name = path[len("/control/"):]
        control = self.server.control
        if control is None:
            off = name == "token" and method == "GET"
            code, data = (200, {"on": False}) if off else (404, {"error": "Control is off. Start Arnheim with --control to switch it on."})
            kind, data, extra = "application/json; charset=utf-8", json.dumps(data).encode(), {}
        elif self.client_address[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            code, kind, data, extra = 403, "application/json; charset=utf-8", b'{"error": "Only on this computer."}', {}
        else:
            code, kind, data, extra = control.handle(method, name, body, self.headers.get("X-Arnheim-Control", ""))
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        for header, value in extra.items():
            self.send_header(header, value)
        self.end_headers()
        return io.BytesIO(data)

    def do_POST(self):
        path = unquote(self.path.split("?", 1)[0])
        if not self.allowed():
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.send_error(400)
            return
        known = path.startswith(("/voice/", "/control/"))
        if not known or not 0 <= size <= 2_000_000:
            self.send_error(404 if not known else 413)
            return
        body = self.rfile.read(size)
        reply = self.voice(path, body) if path.startswith("/voice/") else self.control(path, body)
        self.wfile.write(reply.getvalue())

    def send_head(self):
        if not self.allowed():
            self.send_error(403)
            return None
        path = unquote(self.path.split("?", 1)[0].split("#", 1)[0])
        if path.startswith("/voice/"):
            return self.voice(path)
        if path.startswith("/control/"):
            return self.control(path)
        if path in ("/", "/index.html"):
            path = "/index.html"
        else:
            parts = path.split("/")[1:]
            if len(parts) < 2 or parts[0] not in SHOWN or any(p in ("", ".", "..") or p.startswith(".") or any(c in p for c in "\\:\0") for p in parts):
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
    lan = False
    control = None  # connect/control.py's Control, with --control


def network_address():
    """This computer's address on its network, as a phone would reach it. Nothing is sent: a UDP
    socket only picks the way out when it is connected."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # an address kept for examples, never reached
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    return None if address.startswith(("0.", "127.")) else address


def company_note():
    """Which company the page will show, and why any of data/'s files can't be read."""
    def shown(name):  # as the page will get it: a file inside this folder, links resolved
        path = os.path.realpath(os.path.join(ROOT, "data", name))
        return path if path.startswith(ROOT + os.sep) and os.path.isfile(path) else None

    if not shown("company.json"):
        if os.path.exists(os.path.join(ROOT, "data", "company.json")):
            return ["data/company.json links to somewhere outside this folder, which serve.py doesn't show, "
                    "so the page shows the made-up sample. Copy the files into data/ instead."]
        return ["Showing the sample company, which is made up. To show your own, see \"Make it yours\" in README.md."]
    lines = ["Showing your own company, from data/."]
    then = {"notes.json": "The founder's office has no notes until it is fixed."}
    for name in ("company.json", "work.json", "notes.json"):
        path = shown(name)
        if path:
            try:
                with open(path, encoding="utf-8-sig") as handle:  # as a browser reads it, a BOM or not
                    json.load(handle)
            except ValueError as error:  # not JSON, or not UTF-8
                lines.append(f"data/{name} can't be read: {error}. {then.get(name, 'The page will say so until it is fixed.')}")
    return lines


def main():
    parser = argparse.ArgumentParser(description="Shows Arnheim in a browser.")
    parser.add_argument("port", nargs="?", type=int, default=8740, help="the port to use (8740 if left out)")
    parser.add_argument("--lan", action="store_true", help="show it to phones and other computers on this network too")
    parser.add_argument("--control", action="store_true",
                        help="let the page on this computer talk to your Claude Code agents, answer their permission requests, and start and stop them")
    args = parser.parse_args()
    if not 0 < args.port < 65536:
        parser.error("the port is a number from 1 to 65535")
    if args.control and args.lan:
        sys.exit("Control works only on this computer, so it can't go with --lan. Leave out one of them.")
    try:
        server = Server(("0.0.0.0" if args.lan else "127.0.0.1", args.port), Handler)
    except OSError as error:
        if error.errno in PORT_TAKEN:
            sys.exit(f"Port {args.port} is already in use, perhaps by another copy of Arnheim. Stop that one, "
                     f"or give another port: python3 serve.py {args.port + 1 if args.port < 65535 else 8741}")
        if error.errno == errno.EACCES:
            sys.exit(f"This computer won't let Arnheim use port {args.port}. Give one above 1024: python3 serve.py 8740")
        raise
    server.lan = args.lan
    server.control = Control() if args.control else None
    print(f"Arnheim is at http://127.0.0.1:{args.port}", flush=True)
    if args.control:
        print("Control is on: the page on this computer can talk to your Claude Code agents, answer their "
              "permission requests, and start and stop them (docs/connect.md).", flush=True)
    if args.lan:
        address = network_address()
        where = f"http://{address}:{args.port}" if address else f"this computer's network address, port {args.port}"
        print(f"On phones and other computers on this network, open {where}", flush=True)
        print("Anyone on this network can open it while it runs, data/ included.", flush=True)
    for line in company_note():
        print(line, flush=True)
    print("Ctrl-C stops it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
