"""Install and run the actual archive in a path containing spaces on a clean Mac runner."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
archive, = (ROOT / "dist").glob("*-macos-universal.zip")
with tempfile.TemporaryDirectory(prefix="Companion clean install ") as temporary:
    destination = Path(temporary)
    subprocess.run(["ditto", "-xk", str(archive), str(destination)], check=True)
    app, = destination.glob("vdj-companion-*")
    assert os.access(app / "START.command", os.X_OK)
    home = destination / "Test VirtualDJ"
    (home / "PluginsMacArm").mkdir(parents=True)
    (home / "Plugins64").mkdir()
    env = {**os.environ, "VDJ_HOME": str(home), "VDJ_NO_BROWSER": "1"}
    subprocess.run(["bash", "scripts/macos/setup.sh"], cwd=app, env=env, check=True, timeout=1200)
    for folder in ("PluginsMacArm", "Plugins64"):
        assert (home / folder / "OnlineSources/VDJ Companion Source.bundle/Contents/MacOS/VDJCompanionSource").is_file()
    python = str(app / ".venv/bin/python")
    # Reinstall is idempotent and does not create backups for unchanged content.
    subprocess.run([python, "scripts/macos/install_plugin.py"], cwd=app, env=env, check=True)
    assert not list(home.rglob("*.backup-*"))
    subprocess.run([python, "-c", """
import asyncio, os
from backend.app.browser_tools import chromium_executable
from backend.app.config import get_settings
from playwright.async_api import async_playwright
settings = get_settings()
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(settings.playwright_browsers_path)
async def check():
    async with async_playwright() as p:
        executable = chromium_executable(settings.playwright_browsers_path)
        assert executable is not None
        browser = await p.chromium.launch(executable_path=str(executable))
        page = await browser.new_page()
        await page.set_content('<title>Companion smoke</title>')
        assert await page.title() == 'Companion smoke'
        await browser.close()
asyncio.run(check())
"""], cwd=app, env=env, check=True, timeout=60)
    with (destination / "runtime.log").open("w+") as log:
        process = subprocess.Popen([python, "scripts/macos/runtime.py", "start"], cwd=app, env=env, stdout=log, stderr=log)
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError("Backend exited early")
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=1) as response:
                        health = json.load(response)
                    assert health['ok'], health
                    break
                except OSError:
                    time.sleep(.5)
            else:
                raise TimeoutError("Backend startup timed out")
            subprocess.run([str(app / "STOP.command")], cwd=app, env=env, check=True, timeout=10)
            assert process.wait(timeout=15) in (0, -15)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
            log.seek(0)
            print(log.read())
print("Extracted package: setup, plugin install, Chromium, health and shutdown passed.")
