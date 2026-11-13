"""Exercise the actual compiled bundle through its exported SDK entry point."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading

ROOT = Path(__file__).resolve().parents[2]
seen = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        seen.append(self.path)
        status, body = 404, b""
        if self.path == "/api/vdj/source/search?q=Beyonc%C3%A9%20%26%20test&limit=25":
            status, body = 200, b"abcdefghijk\tTest track\tTest artist\t123\thttps://example.com/cover.jpg\n"
        elif self.path == "/api/vdj/source/stream/abcdefghijk":
            status, body = 200, b"http://127.0.0.1:8765/stream/test.webm"
        elif self.path.endswith("/busy"):
            status = 503
        elif self.path.endswith("/timeout"):
            status = 504
        self.send_response(status)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


executable = ROOT / "plugin/online-source/build/macos/native-smoke"
subprocess.run(["xcrun", "clang++", "-std=c++17", "-Iplugin/sdk", "-framework", "CoreFoundation",
                "scripts/macos/native_smoke.cpp", "-o", str(executable)], cwd=ROOT, check=True)
with ThreadingHTTPServer(("127.0.0.1", 8765), Handler) as server:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        subprocess.run([str(executable), str(executable.parent / "VDJ Companion Source.bundle/Contents/MacOS/VDJCompanionSource")], check=True, timeout=30)
        assert len(seen) == 6, seen
    finally:
        server.shutdown()
        thread.join()
print("Native bundle: load, UTF-8 search, stream URL and HTTP errors passed.")
