"""
mock_gemini.py - a stand-in for the Gemini API, for testing without a key or credits.

    python pipeline3d/tests/mock_gemini.py --port 8799 --keypoints pipeline3d/manifests/horse_keypoints.json
    export GOOGLE_GEMINI_BASE_URL=http://127.0.0.1:8799         # banana.py (google-genai SDK)
    export GEMINI_API_BASE=http://127.0.0.1:8799/v1beta         # fit_reference.py
    export GEMINI_API_KEY=anything

Image models (id contains "image") get a blank white PNG of the keypoints' image size;
every other model gets the keypoints as its JSON answer.
"""

import argparse
import base64
import json
import struct
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def blank_png(w, h):
    raw = b"".join(b"\x00" + b"\xff" * (w * 3) for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--keypoints", required=True)
    a = ap.parse_args()
    kp = json.load(open(a.keypoints))
    png = base64.b64encode(blank_png(*kp.get("image_size", (1000, 1000)))).decode()
    calls = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):          # /calls: what was asked, for tests
            self._send({"calls": calls})

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            model = self.path.split("/models/")[-1].split(":")[0]
            key = self.headers.get("x-goog-api-key", "")
            calls.append({"model": model, "has_key": bool(key)})
            if not key:
                return self._send({"error": {"code": 403, "message": "API key missing"}}, 403)
            part = ({"inlineData": {"mimeType": "image/png", "data": png}} if "image" in model
                    else {"text": json.dumps(kp)})
            self._send({"candidates": [{"content": {"role": "model", "parts": [part]}, "finishReason": "STOP"}]})

        def _send(self, obj, code=200):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    print(f"mock Gemini on http://127.0.0.1:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
