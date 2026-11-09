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


if __name__ == "__main__":
    unittest.main()
