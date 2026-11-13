"""Foreground macOS launcher; lock lifetime prevents duplicate owned instances."""
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8765"
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / "tools/playwright-browsers")
os.environ["PATH"] = str(ROOT / "tools/ffmpeg/bin") + os.pathsep + os.environ.get("PATH", "")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, **kwargs):
    with OPENER.open(urllib.request.Request(BASE + path, **kwargs), timeout=3) as response:
        return response.read()


def healthy():
    try:
        result = json.loads(request("/api/health"))
        return result.get("service") == "vdj-youtube-companion"
    except (OSError, ValueError):
        return False


def main():
    (ROOT / "data").mkdir(exist_ok=True)
    with (ROOT / "data/macos-runtime.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            running = False
        except BlockingIOError:
            running = True
        if sys.argv[1:] == ["status"]:
            raise SystemExit(0 if running else 1)
        if sys.argv[1:] == ["stop"]:
            if not running:
                print("This copy of Companion is not running.")
                return
            if not healthy():
                raise SystemExit("Backend is not ready. Use Ctrl+C in its Terminal window.")
            html = request("/").decode()
            token = re.search(r'<meta name="control-token" content="([^"]+)"', html)
            if not token:
                raise SystemExit("Could not read the backend control token.")
            request("/api/shutdown", method="POST", headers={"X-Shutdown-Token": token[1]})
            print("Shutdown requested.")
            return
        if running:
            if not healthy():
                raise SystemExit("Companion is already starting; wait a moment.")
            if os.environ.get("VDJ_NO_BROWSER") != "1":
                subprocess.run(["open", BASE], check=True)
            return
        # Refuse to share a port with another copy or another application.
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", 8765))
            except OSError:
                raise SystemExit("Port 8765 is occupied. Stop the other Companion copy first.")
        def open_when_ready():
            for _ in range(60):
                if healthy():
                    if os.environ.get("VDJ_NO_BROWSER") != "1":
                        subprocess.run(["open", BASE], check=False)
                    return
                time.sleep(.5)
        threading.Thread(target=open_when_ready, daemon=True).start()
        import uvicorn
        print("Leave this Terminal window open. Use STOP.command or Ctrl+C to stop.")
        uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
