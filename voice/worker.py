"""Arnheim's voice: Kokoro, an open text-to-speech model, speaking on this computer, and Whisper
(OpenAI's open speech recognition model, base.en) listening, if it is installed.

voice/bridge.py starts this with the Python that has Kokoro installed (README, "Voice") and talks to
it over stdin and stdout, one request a line. Every answer is one line of JSON; "say" is followed by
the sound itself: 16-bit mono samples, 24,000 a second. "hear" sends 16-bit mono samples at 16,000 a
second after its line and is answered with the words heard. Nothing is fetched from the internet unless
ARNHEIM_VOICE_FETCH=1, so the model and its voices must already be on this computer otherwise.
"""
import json
import os
import re
import sys
import time

REPO = "hexgrad/Kokoro-82M"
RATE = 24000
NAME = re.compile(r"^[ab][fm]_[a-z]+$")  # American (a) and British (b) English voices
FIRST = ("af_heart", "af_bella", "af_nicole", "am_michael", "am_fenrir", "bf_emma", "bm_george")  # fetched on first use


def main():
    # Keep the answers' channel clean: anything a library prints goes to the log instead.
    proto = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    if os.environ.get("ARNHEIM_VOICE_FETCH") != "1":
        os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    def reply(head, data=b""):
        proto.write((json.dumps(head) + "\n").encode())
        if data:
            proto.write(data)
        proto.flush()

    started = time.time()
    try:
        import numpy as np
        import torch
        from huggingface_hub import hf_hub_download
        from kokoro import KModel, KPipeline

        torch.set_grad_enabled(False)
        model = KModel(repo_id=REPO).eval()
        if os.environ.get("ARNHEIM_VOICE_FETCH") == "1":
            for name in FIRST:
                hf_hub_download(REPO, f"voices/{name}.pt")
        folder = os.path.join(os.path.dirname(hf_hub_download(REPO, "config.json")), "voices")
        voices = sorted(n[:-3] for n in os.listdir(folder) if n.endswith(".pt") and NAME.match(n[:-3]))
        pipes = {code: KPipeline(lang_code=code, repo_id=REPO, model=model) for code in ("a", "b")}
    except Exception as error:  # the model, a voice or a library is missing
        reply({"ok": False, "error": f"{type(error).__name__}: {error}"[:300]})
        return

    # Listening: Whisper base.en, kept in this Python's own folder (README, "Voice").
    ear = None
    try:
        import whisper

        root = os.path.join(sys.prefix, "whisper")
        if os.path.isfile(os.path.join(root, "base.en.pt")) or os.environ.get("ARNHEIM_VOICE_FETCH") == "1":
            ear = whisper.load_model("base.en", device="cpu", download_root=root)
    except Exception as error:
        print(f"Arnheim: no listening ({type(error).__name__}: {error})", file=sys.stderr)

    def hear(raw):
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        if audio.size < 16000 * 0.3:
            return ""
        mel = whisper.log_mel_spectrogram(whisper.pad_or_trim(audio)).to(ear.device)
        out = whisper.decode(ear, mel, whisper.DecodingOptions(language="en", without_timestamps=True, fp16=False, sample_len=96))
        if out.no_speech_prob > 0.6 and out.avg_logprob < -0.7:
            return ""
        text = re.sub(r"(\s*[^\w\s']+)(\1){2,}.*$", "", out.text)  # a known slip: marks repeated after the words
        return " ".join(text.split())

    def say(text, voice, speed):
        names = voice.split(",")
        if not 1 <= len(names) <= 2 or any(n not in voices for n in names):
            raise ValueError("That voice is not on this computer.")
        parts = []
        for _, _, audio in pipes[names[0][0]](text, voice=voice, speed=speed):
            if audio is not None:
                parts.append(audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio))
        wave = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        return (np.clip(wave, -1, 1) * 32767).astype("<i2").tobytes()

    if voices:
        say("Ready.", voices[0], 1.0)  # the first sentence is slower; take it now
    if ear:
        hear(np.zeros(16000, dtype="<i2").tobytes())
    reply({"ok": True, "ready": True, "voices": voices, "hear": bool(ear), "rate": RATE, "ms": round((time.time() - started) * 1000)})

    stdin = sys.stdin.buffer
    while True:
        line = stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
        except ValueError:
            reply({"ok": False, "error": "Not a request."})
            continue
        if req.get("op") == "say":
            began = time.time()
            try:
                speed = min(1.3, max(0.8, float(req.get("speed") or 1.0)))
                pcm = say(str(req.get("text") or "")[:600], str(req.get("voice") or ""), speed)
            except Exception as error:
                reply({"ok": False, "error": str(error)[:300]})
                continue
            reply({"ok": True, "rate": RATE, "bytes": len(pcm), "ms": round((time.time() - began) * 1000)}, pcm)
        elif req.get("op") == "hear":
            raw = stdin.read(max(0, min(int(req.get("bytes") or 0), 16000 * 2 * 30)))
            began = time.time()
            try:
                text = hear(raw) if ear else None
            except Exception as error:
                reply({"ok": False, "error": str(error)[:300]})
                continue
            if text is None:
                reply({"ok": False, "error": "Listening is not set up on this computer yet."})
            else:
                reply({"ok": True, "text": text, "ms": round((time.time() - began) * 1000)})
        else:
            reply({"ok": False, "error": "Unknown request."})


if __name__ == "__main__":
    main()
