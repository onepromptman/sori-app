"""Run real local Whisper in a browser against a supplied synthetic WAV fixture."""

import argparse
import io
import threading
import wave
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--browser", choices=("chromium", "webkit"), default="chromium")
    parser.add_argument("--channel")
    args = parser.parse_args()
    wav = args.audio.read_bytes()
    with wave.open(io.BytesIO(wav)) as sample:
        frames = sample.readframes(sample.getnframes())
        repetitions = 2 + (31 * sample.getframerate()) // sample.getnframes()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as extended:
            extended.setparams(sample.getparams())
            extended.writeframes(frames * repetitions)
    long_wav = buffer.getvalue()
    files = {
        "/": (
            "text/html",
            b"<!doctype html><title>Whisper smoke test</title><link rel='icon' href='data:,'>",
        ),
        "/smoke.wav": ("audio/wav", wav),
        "/smoke-long.wav": ("audio/wav", long_wav),
    }

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path in files:
                media_type, content = files[self.path]
                self.send_response(200)
                self.send_header("Content-Type", media_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                super().do_GET()

        def log_message(self, *_args):
            pass

    web_root = Path(__file__).resolve().parents[1]
    with ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=web_root)) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_port}"
        try:
            with sync_playwright() as playwright:
                browser_type = getattr(playwright, args.browser)
                options = {"channel": args.channel} if args.channel else {}
                browser = browser_type.launch(headless=True, **options)
                context = browser.new_context()
                page = context.new_page()
                outbound = []
                context.on("request", lambda request: outbound.append((request.method, request.url)))
                page.on("console", lambda msg: print(msg.text) if msg.type == "error" else None)
                page.goto(base)
                result = page.evaluate(
                    """async () => {
                        const { transcribeAudio } = await import('/transcription/index.js');
                        const audio = await (await fetch('/smoke.wav')).blob();
                        const controller = new AbortController();
                        controller.abort();
                        try {
                          await transcribeAudio(audio, { signal: controller.signal });
                          throw Error('Pre-canceled transcription ran');
                        } catch (err) {
                          if (err.name !== 'AbortError') throw err;
                        }
                        const stages = [];
                        const transcript = await transcribeAudio(audio, {
                          language: 'english',
                          onProgress: ({ stage }) => { if (!stages.includes(stage)) stages.push(stage); },
                        });
                        const longAudio = await (await fetch('/smoke-long.wav')).blob();
                        const warmStages = [];
                        const warm = await transcribeAudio(longAudio, {
                          language: 'english',
                          onProgress: ({ stage }) => warmStages.push(stage),
                        });
                        if (warmStages.includes('model')) throw Error('Warm run reloaded the model');
                        if (!warm.segments.some(({ end }) => end > 30)) throw Error('Long audio was truncated');
                        const active = new AbortController();
                        try {
                          await transcribeAudio(audio, {
                            signal: active.signal,
                            onProgress: ({ stage }) => { if (stage === 'transcribing') active.abort(); },
                          });
                          throw Error('Active cancellation failed');
                        } catch (err) {
                          if (err.name !== 'AbortError') throw err;
                        }
                        const retried = await transcribeAudio(audio, { language: 'english' });
                        if (retried.text !== transcript.text) throw Error('Retry changed the transcript');
                        return { ...transcript, stages, longEnd: warm.segments.at(-1).end };
                    }"""
                )
                assert "sori" in result["text"].lower() or "speech model" in result["text"].lower(), result
                assert result["segments"] and all(0 <= s["start"] <= s["end"] for s in result["segments"]), (
                    result
                )
                assert result["stages"] == ["decoding", "model", "transcribing"], result
                assert all(method in {"GET", "HEAD"} for method, _url in outbound), outbound
                print(
                    f"PASS: local Whisper transcribed {result['longEnd']:.1f}s of synthetic speech with timestamps, "
                    "reused the model, canceled and retried, and only downloaded assets."
                )
                print(result["text"])
                browser.close()
        finally:
            httpd.shutdown()


if __name__ == "__main__":
    main()
