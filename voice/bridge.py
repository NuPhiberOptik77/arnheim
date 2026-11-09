"""Arnheim's voice, for a page's own server. Standard library only.

A server hands this the requests under /voice/ (Voice.handle). It starts voice/worker.py with the
Python that has Kokoro installed, keeps it running, and passes the sound back as WAV:

  GET  /voice/status   whether this computer can speak, and which voices it has
  POST /voice/wake     start the voice now, so the first answer is quick
  POST /voice/say      {"text", "voice"} -> audio/wav
  POST /voice/hear     audio/wav -> {"text"}, once a speech model is set up

That Python is ARNHEIM_VOICE_PYTHON, or else the one in .voice in this folder: .voice/bin/python,
or .voice/Scripts/python.exe on Windows (README, "Voice").
The worker's command is fixed; what a page sends only ever reaches it as data.
"""
import collections
import json
import os
import re
import struct
import subprocess
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "worker.py")
JSON = "application/json; charset=utf-8"
MAX_TEXT = 600
VOICE = re.compile(r"^[ab][fm]_[a-z]+(,[ab][fm]_[a-z]+)?$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


class VoiceError(Exception):
    pass


def wav(pcm, rate):
    """16-bit mono samples, wrapped as a WAV file."""
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm)


def samples16k(sound):
    """The samples in a WAV file, if it is 16-bit mono at 16,000 a second and at most 30 s long."""
    if len(sound) < 44 or sound[:4] != b"RIFF" or sound[8:12] != b"WAVE":
        raise ValueError("Send a WAV file.")
    at, fmt, data = 12, None, None
    while at + 8 <= len(sound):
        tag, size = sound[at:at + 4], struct.unpack("<I", sound[at + 4:at + 8])[0]
        if tag == b"fmt ":
            fmt = struct.unpack("<HHIIHH", sound[at + 8:at + 24])
        elif tag == b"data":
            data = sound[at + 8:at + 8 + size]
            break
        at += 8 + size + (size & 1)
    if not fmt or data is None or fmt[0] != 1 or fmt[1] != 1 or fmt[2] != 16000 or fmt[5] != 16:
        raise ValueError("Send 16-bit mono sound at 16,000 samples a second.")
    if len(data) > 16000 * 2 * 30:
        raise ValueError("That is longer than 30 seconds.")
    return data[: len(data) - (len(data) & 1)]


def clean(text):
    """One line of plain words, short enough to say."""
    text = " ".join(CONTROL.sub(" ", str(text)).split())
    if len(text) > MAX_TEXT:
        cut = max(text.rfind(". ", 0, MAX_TEXT), text.rfind("? ", 0, MAX_TEXT), text.rfind("! ", 0, MAX_TEXT))
        text = text[: cut + 1] if cut > 80 else text[:MAX_TEXT]
    return text


class Voice:
    def __init__(self, python=None):
        folder = os.path.join(os.path.dirname(HERE), ".voice")
        default = os.path.join(folder, "Scripts", "python.exe") if os.name == "nt" else os.path.join(folder, "bin", "python")
        self.python = python or os.environ.get("ARNHEIM_VOICE_PYTHON") or default
        self.proc = None
        self.lock = threading.Lock()  # one request at a time through the worker
        self.boot = threading.Lock()  # one start at a time
        self.state = "off"  # off, starting, ready, failed
        self.voices = []
        self.can_hear = False
        self.error = ""
        self.log = collections.deque(maxlen=12)  # the worker's last words, for when it fails
        self.test_hear = os.environ.get("ARNHEIM_VOICE_TEST_HEAR", "")  # tests only: these words for any sound

    def installed(self):
        return os.path.isfile(self.python) and os.access(self.python, os.X_OK)

    def status(self):
        return {
            "say": self.installed(), "state": self.state if self.installed() else "missing", "voices": self.voices,
            "hear": bool(self.test_hear) or self.can_hear, "test": bool(self.test_hear), "error": self.error,
        }

    def wake(self):
        if self.installed() and self.state not in ("starting", "ready"):
            self.state = "starting"
            threading.Thread(target=self.ready, daemon=True).start()

    def ready(self):
        with self.boot:
            if self.proc and self.proc.poll() is None and self.state == "ready":
                return True
            self.stop()
            if not self.installed():
                self.state, self.error = "failed", "This computer has no voice set up."
                return False
            self.state, self.error = "starting", ""
            env = dict(os.environ, PYTHONUNBUFFERED="1")
            if env.get("ARNHEIM_VOICE_FETCH") != "1":
                env["HF_HUB_OFFLINE"] = "1"
            try:
                self.proc = subprocess.Popen(
                    [self.python, "-I", WORKER], cwd=HERE, env=env,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
            except OSError as error:
                self.state, self.error = "failed", f"The voice could not start: {error.strerror}"
                return False
            threading.Thread(target=self._drain, args=(self.proc,), daemon=True).start()
            # Fetching the models the first time (ARNHEIM_VOICE_FETCH=1, about 470 MB) can take many minutes.
            head, _ = self._read(self.proc, 1800 if env.get("ARNHEIM_VOICE_FETCH") == "1" else 180)
            if head.get("ready"):
                self.voices, self.can_hear, self.state = head.get("voices", []), bool(head.get("hear")), "ready"
                return True
            self.state = "failed"
            self.error = head.get("error") or (self.log[-1] if self.log else "The voice stopped while starting.")
            self.stop()
            return False

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def _drain(self, proc):
        for line in proc.stderr:
            text = line.decode("utf-8", "replace").strip()
            if text:
                self.log.append(text[:300])

    def _read(self, proc, timeout):
        """One answer from the worker; the worker is stopped if it takes longer than timeout."""
        timer = threading.Timer(timeout, proc.kill)
        timer.start()
        try:
            line = proc.stdout.readline()
            head = json.loads(line) if line else {}
            size = int(head.get("bytes") or 0)
            data = proc.stdout.read(size) if size else b""
            if len(data) != size:
                head = {}
            return head, data
        except (OSError, ValueError):
            return {}, b""
        finally:
            timer.cancel()

    def say(self, text, voice):
        if not self.ready():
            raise VoiceError(self.error or "The voice is not ready.")
        with self.lock:
            proc = self.proc
            try:
                proc.stdin.write((json.dumps({"op": "say", "text": text, "voice": voice}) + "\n").encode())
                proc.stdin.flush()
            except (OSError, AttributeError):
                head = {}
            else:
                head, pcm = self._read(proc, 30)
        if not head:
            self.state, self.error = "failed", "The voice stopped."
            raise VoiceError(self.error)
        if not head.get("ok"):
            raise VoiceError(head.get("error") or "The voice could not say that.")
        return wav(pcm, head["rate"]), head.get("ms", 0)

    def hear(self, sound):
        """The words in a WAV file of 16-bit mono sound at 16,000 samples a second."""
        pcm = samples16k(sound)
        if not self.ready():
            raise VoiceError(self.error or "The voice is not ready.")
        with self.lock:
            proc = self.proc
            try:
                proc.stdin.write((json.dumps({"op": "hear", "bytes": len(pcm)}) + "\n").encode() + pcm)
                proc.stdin.flush()
            except (OSError, AttributeError):
                head = {}
            else:
                head, _ = self._read(proc, 30)
        if not head:
            self.state, self.error = "failed", "The voice stopped."
            raise VoiceError(self.error)
        if not head.get("ok"):
            raise VoiceError(head.get("error") or "Nothing was heard.")
        return head.get("text", ""), head.get("ms", 0)

    def handle(self, method, name, body=b""):
        """name is the path after /voice/. Returns (status, content type, body, extra headers)."""
        def answer(code, data):
            return code, JSON, json.dumps(data).encode(), {}

        if method == "GET" and name == "status":
            return answer(200, self.status())
        if method != "POST" or name not in ("wake", "say", "hear"):
            return answer(404, {"ok": False, "error": "Not here."})
        if name == "wake":
            self.wake()
            return answer(200, self.status())
        if name == "hear":
            if self.test_hear:
                return answer(200, {"ok": True, "text": self.test_hear, "test": True})
            if self.state == "ready" and not self.can_hear:
                return answer(501, {"ok": False, "error": "Listening is not set up on this computer yet."})
            try:
                text, ms = self.hear(body)
            except ValueError as error:
                return answer(400, {"ok": False, "error": str(error)})
            except VoiceError as error:
                return answer(503, {"ok": False, "error": str(error)})
            return answer(200, {"ok": True, "text": text, "ms": ms})
        try:
            req = json.loads(body or b"{}")
            text = clean(req.get("text", ""))
            voice = str(req.get("voice", ""))
        except (ValueError, AttributeError):
            return answer(400, {"ok": False, "error": "Send JSON with text and voice."})
        if not text or not VOICE.match(voice):
            return answer(400, {"ok": False, "error": "Send some words and a voice's name."})
        try:
            sound, ms = self.say(text, voice)
        except VoiceError as error:
            return answer(503, {"ok": False, "error": str(error)})
        return 200, "audio/wav", sound, {"X-Voice-Ms": str(ms)}
