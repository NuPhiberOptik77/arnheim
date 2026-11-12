"""serve.py's rules: it shows Arnheim's own files and nothing else, only to the names it answers
to, and the voice only to its own page. Standard library only.

Run from the repository's folder: python3 -m unittest discover tests
"""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import serve  # noqa: E402  (after the path is set)


class ServeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = serve.Server(("127.0.0.1", 0), serve.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def ask(self, path, host=None, method="GET", headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", f"127.0.0.1:{self.port}" if host is None else host)
            for name, value in (headers or {}).items():
                conn.putheader(name, value)
            if body is not None:
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body)
            reply = conn.getresponse()
            return reply.status, reply.read()
        finally:
            conn.close()

    def test_the_page_and_its_files(self):
        for path in ("/", "/index.html", "/src/demo.js", "/src/demo.css", "/sample/company.json", "/vendor/three/three.module.js"):
            self.assertEqual(self.ask(path)[0], 200, path)
        self.assertEqual(self.ask("/", host=f"localhost:{self.port}")[0], 200)

    def test_nothing_else(self):
        for path in ("/serve.py", "/README.md", "/.git/config", "/.gitignore", "/voice/worker.py", "/src/", "/src",
                     "/src/../serve.py", "/src/%2e%2e/serve.py", "/sample/../serve.py", "/data/../serve.py",
                     "/sample/.hidden.json", "/tests/test_serve.py", "/src/demo.js.map",
                     "/data/x%5C..%5C..%5Cserve.py", "/src/demo.js%3A", "/src/demo%00.js"):
            self.assertEqual(self.ask(path)[0], 404, path)

    def test_other_names_are_refused(self):
        for host in (f"example.com:{self.port}", f"192.168.1.5:{self.port}", f"computer.local:{self.port}",
                     f"127.0.0.1:{self.port + 1}", "127.0.0.1", ""):
            self.assertEqual(self.ask("/", host=host)[0], 403, host)
            self.assertEqual(self.ask("/voice/status", host=host)[0], 403, host)

    def test_names_on_a_network(self):
        self.assertTrue(serve.host_ok("192.168.1.5:8740", 8740, lan=True))
        self.assertTrue(serve.host_ok("[fe80::1]:8740", 8740, lan=True))
        self.assertTrue(serve.host_ok("Computer.local:8740", 8740, lan=True))
        self.assertTrue(serve.host_ok("localhost:8740", 8740, lan=True))
        self.assertFalse(serve.host_ok("example.com:8740", 8740, lan=True))
        self.assertFalse(serve.host_ok("192.168.1.5.example.com:8740", 8740, lan=True))
        self.assertFalse(serve.host_ok("192.168.1.5:8741", 8740, lan=True))
        self.assertFalse(serve.host_ok("192.168.1.5:8740", 8740, lan=False))
        self.assertTrue(serve.host_ok("127.0.0.1", 80))
        self.assertTrue(serve.host_ok("[::1]:8740", 8740))

    def test_the_voice_answers_only_its_own_page(self):
        status, body = self.ask("/voice/status")
        self.assertEqual(status, 200)
        self.assertIn("say", json.loads(body))
        own = f"http://127.0.0.1:{self.port}"
        for origin in ("http://example.com", None, f"http://localhost:{self.port}"):
            headers = {"Origin": origin} if origin else {}
            self.assertEqual(self.ask("/voice/wake", method="POST", headers=headers, body=b"")[0], 403, origin)
        # Its own page may ask, but not for anything outside /voice/ (this asks nothing of the voice itself).
        self.assertEqual(self.ask("/voice/wake", method="POST", headers={"Origin": own, "Content-Length": "many"})[0], 400)
        self.assertEqual(self.ask("/sample/company.json", method="POST", headers={"Origin": own}, body=b"")[0], 404)

    def test_control_is_off_unless_asked(self):
        status, body = self.ask("/control/token")
        self.assertEqual((status, json.loads(body)), (200, {"on": False}))
        own = f"http://127.0.0.1:{self.port}"
        self.assertEqual(self.ask("/control/state")[0], 404)
        self.assertEqual(self.ask("/control/say", method="POST", headers={"Origin": own}, body=b"{}")[0], 404)


class CompanyServeTest(unittest.TestCase):
    """data/company.json reaches the page without "pings": its ntfy topic reads like a password."""

    def test_the_page_never_gets_the_pings(self):
        company = {"company": "Example Studio", "pings": {"ntfy": "https://ntfy.sh/a-secret-topic"}, "floors": []}
        shown = json.loads(serve.without_pings(json.dumps(company).encode()))
        self.assertEqual(shown, {"company": "Example Studio", "floors": []})
        self.assertEqual(serve.without_pings(b'{"company": "x"}'), b'{"company": "x"}')  # nothing to take out: as it is
        self.assertEqual(serve.without_pings(b"not json"), b"not json")
        with tempfile.TemporaryDirectory() as base:
            os.makedirs(os.path.join(base, "data"))
            with open(os.path.join(base, "data", "company.json"), "w", encoding="utf-8") as handle:
                json.dump(company, handle)
            root = serve.ROOT
            serve.ROOT = os.path.realpath(base)
            server = serve.Server(("127.0.0.1", 0), serve.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                replies = []
                for name in ("company.json", "Company.json", "COMPANY.JSON", "./company.json"):
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
                    conn.request("GET", f"/data/{name}", headers={"Host": f"127.0.0.1:{server.server_address[1]}"})
                    got = conn.getresponse()
                    replies.append((got.status, got.read()))
                    conn.close()
            finally:
                serve.ROOT = root
                server.shutdown()
                server.server_close()
        status, body = replies[0]
        self.assertEqual(status, 200)
        self.assertNotIn(b"secret", body)
        self.assertEqual(json.loads(body)["company"], "Example Studio")
        for status, body in replies[1:]:  # another spelling, on a disk that ignores case: never the topic either
            self.assertNotIn(b"secret", body)


class ControlServeTest(ServeTest):
    """With --control: only its own page on this computer, and only with the page's token."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = tempfile.TemporaryDirectory()  # never the data/ of the copy being tested
        cls.server.control = serve.Control(data=cls.data.name)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.data.cleanup()

    def test_control_is_off_unless_asked(self):
        status, body = self.ask("/control/token")
        token = json.loads(body)["token"]
        self.assertEqual(status, 200)
        self.assertEqual(self.ask("/control/token", host=f"example.com:{self.port}")[0], 403)
        self.assertEqual(self.ask("/control/state")[0], 403)
        self.assertEqual(self.ask("/control/state", headers={"X-Arnheim-Control": "guess"})[0], 403)
        self.assertEqual(self.ask("/control/state", headers={"X-Arnheim-Control": token})[0], 200)
        own = f"http://127.0.0.1:{self.port}"
        body = json.dumps({"key": "cc-nobody", "text": "hi"}).encode()
        for origin in ("http://example.com", None):
            headers = {"X-Arnheim-Control": token, **({"Origin": origin} if origin else {})}
            self.assertEqual(self.ask("/control/say", method="POST", headers=headers, body=body)[0], 403, origin)
        status, reply = self.ask("/control/say", method="POST", headers={"X-Arnheim-Control": token, "Origin": own}, body=body)
        self.assertEqual(status, 400)  # its own page, but no such conversation
        self.assertIn("left the building", json.loads(reply)["error"])

    def test_never_with_lan(self):
        import subprocess
        done = subprocess.run([sys.executable, os.path.join(ROOT, "serve.py"), "--control", "--lan", "8765"], capture_output=True, text=True, timeout=20)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("only on this computer", done.stderr)



class ShareServeTest(unittest.TestCase):
    """With --share: another computer gets in only through the view-only link, and then only to look. Never the
    founder's notes, nor control's mail with Claude Code (that one never leaves this computer, link or not)."""

    KEY = "k" * 32

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        base = cls.base.name
        for name, text in (("index.html", "<!doctype html><title>Arnheim</title>"),
                           ("data/company.json", '{"company": "Example Studio", "howtos": [{"id": "ship", "title": "Ship it", "file": "howtos/ship.md"}]}'),
                           ("data/notes.json", '{"notes": ["private"]}'), ("data/control/box.json", '{"mail": "private"}'),
                           ("data/howtos/ship.md", "# Ship it\n"), ("data/private.md", "private plans\n")):
            os.makedirs(os.path.dirname(os.path.join(base, name)), exist_ok=True)
            with open(os.path.join(base, name), "w", encoding="utf-8") as handle:
                handle.write(text)
        cls.root = serve.ROOT
        serve.ROOT = os.path.realpath(base)

        class Away(serve.Handler):  # a request marked "away" stands for one from another computer
            def here(self):
                return self.headers.get("X-Test-From") != "away"
        cls.server = serve.Server(("127.0.0.1", 0), Away)
        cls.server.lan = True
        cls.server.share = cls.KEY
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        serve.ROOT = cls.root
        cls.server.shutdown()
        cls.server.server_close()
        cls.base.cleanup()

    def ask(self, path, headers=None, method="GET", body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers={"Host": f"127.0.0.1:{self.port}", **(headers or {})})
            reply = conn.getresponse()
            return reply.status, dict(reply.getheaders()), reply.read()
        finally:
            conn.close()

    def test_only_through_the_link(self):
        away = {"X-Test-From": "away"}
        for path in ("/", "/?view=wrong", "/?view=", "/data/company.json", f"/data/company.json?view={self.KEY}"):
            self.assertEqual(self.ask(path, away)[0], 403, path)
        self.assertEqual(self.ask("/", {**away, "Cookie": "arnheim_view=wrong"})[0], 403)
        status, headers, _ = self.ask(f"/?view={self.KEY}", away)
        self.assertEqual((status, headers["Location"]), (303, "/"))  # the key leaves the address bar
        self.assertIn(f"arnheim_view={self.KEY}; Path=/; HttpOnly; SameSite=Lax", headers["Set-Cookie"])
        viewer = {**away, "Cookie": f"other=1; arnheim_view={self.KEY}"}
        for path in ("/", "/data/company.json", "/data/howtos/ship.md"):
            self.assertEqual(self.ask(path, viewer)[0], 200, path)
        self.assertEqual(self.ask("/data/howtos/ship.md", viewer)[1]["Content-Type"], "text/markdown; charset=utf-8")
        for path in ("/data/notes.json", "/data/Notes.json", "/data/NOTES.json", "/data/control/box.json", "/data/Control/box.json",
                     "/data/CONTROL/box.json", "/data/%6Eotes.json", "/data/private.md", "/control/token", "/brain/status", "/voice/status",
                     "/Control/token"):
            for method in ("GET", "HEAD"):
                status, _, body = self.ask(path, viewer, method)
                self.assertEqual(status, 404, (path, method))
                self.assertNotIn(b"private", body)
        self.assertEqual(self.ask("/voice/say", viewer, "POST", b"{}")[0], 403)  # nothing it sends is acted on
        # This computer needs no link, and sees the notes.
        self.assertEqual(self.ask("/")[0], 200)
        self.assertEqual(self.ask("/data/notes.json")[0], 200)

    def test_control_mail_never_leaves_this_computer(self):
        self.server.share = None  # plain --lan: anyone on the network, but never control's mail
        try:
            away = {"X-Test-From": "away"}
            self.assertEqual(self.ask("/data/company.json", away)[0], 200)
            for path in ("/data/control/box.json", "/data/Control/box.json", "/data/CONTROL/box.json"):
                self.assertEqual(self.ask(path, away)[0], 404, path)
            self.assertEqual(self.ask("/data/control/box.json")[0], 200)
            self.assertEqual(self.ask("/data/howtos/ship.md", away)[0], 200)  # a listed how-to
            self.assertEqual(self.ask("/data/private.md")[0], 404)  # Markdown in data/ only if it is a listed how-to
        finally:
            self.server.share = self.KEY

    def test_the_key_is_kept_until_a_new_link(self):
        with tempfile.TemporaryDirectory() as base:
            kept = serve.SHARE_KEY
            serve.SHARE_KEY = os.path.join(base, ".share-key")
            try:
                first = serve.share_key()
                self.assertRegex(first, serve.KEY)
                self.assertEqual(serve.share_key(), first)
                self.assertEqual(os.stat(serve.SHARE_KEY).st_mode & 0o777, 0o600)
                os.chmod(serve.SHARE_KEY, 0o644)
                self.assertEqual(serve.share_key(), first)
                self.assertEqual(os.stat(serve.SHARE_KEY).st_mode & 0o777, 0o600)  # put right when read
                self.assertNotEqual(serve.share_key(new=True), first)
            finally:
                serve.SHARE_KEY = kept

    def test_flags(self):
        import subprocess
        for args, said in ((["--share", "--lan"], "Leave out one of them"), (["--share", "--control"], "second copy"),
                           (["--share", "--brain"], "only on this computer"), (["--new-link"], "goes with --share")):
            done = subprocess.run([sys.executable, os.path.join(ROOT, "serve.py"), *args, "8766"], capture_output=True, text=True, timeout=20)
            self.assertNotEqual(done.returncode, 0, args)
            self.assertIn(said, done.stderr, args)


if __name__ == "__main__":
    unittest.main()
