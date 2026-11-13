"""Install and run the actual archive in a path containing spaces on a clean Mac runner."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import re
import zipfile
import hashlib

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
    # Fresh setup must install actual private tools, even if Homebrew exists on CI.
    for name in ('ffmpeg', 'ffprobe'):
        binary = app / 'tools/ffmpeg/bin' / name
        assert binary.is_file() and not binary.is_symlink(), binary
        subprocess.run([str(binary), '-version'], check=True, capture_output=True)
    sample = destination / 'test audio.mp3'
    subprocess.run([str(app / 'tools/ffmpeg/bin/ffmpeg'), '-v', 'error',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.2', '-c:a', 'libmp3lame', str(sample)], check=True)
    subprocess.run([str(app / 'tools/ffmpeg/bin/ffprobe'), '-v', 'error', str(sample)], check=True)
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
            subprocess.run([str(app / "START.command")], cwd=app, env=env, check=True, timeout=15)
            assert process.poll() is None, "Opening the launcher again must reuse the existing backend"
            subprocess.run([str(app / "STOP.command")], cwd=app, env=env, check=True, timeout=10)
            assert process.wait(timeout=15) in (0, -15)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
            log.seek(0)
            print(log.read())
    # Offer a fixture release through the real authenticated update endpoint.
    # It uses the actual packaged files and native bundle, with a newer version.
    fixture = destination / 'next-macos-universal.zip'
    next_version = '0.2.0-beta.999'
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(fixture, 'w', zipfile.ZIP_DEFLATED) as output:
        for item in source.infolist():
            content = source.read(item)
            if item.filename.endswith('/MACOS_VERSION'):
                content = (next_version + '\n').encode()
            output.writestr(item, content)
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    harness = destination / 'update_harness.py'
    harness.write_text('''
import hashlib, os, runpy, sys
from pathlib import Path
import httpx
sys.path.insert(0, os.getcwd())
from backend.app import main
payload = Path(os.environ['UPDATE_FIXTURE']).read_bytes()
digest = hashlib.sha256(payload).hexdigest()
async def fetch():
    return {'currentVersion': main.settings.version, 'latestVersion': '0.2.0-beta.999',
        'updateAvailable': True, 'assetName': 'next-macos-universal.zip',
        'releaseUrl': 'https://github.com/rcsy-px/vdj-stream/releases/tag/macos-v0.2.0-beta.999',
        'downloadUrl': 'https://fixture.invalid/next-macos-universal.zip',
        'checksumUrl': 'https://fixture.invalid/next-macos-universal.zip.sha256',
        'assetDigest': 'sha256:' + digest}
main.update_checker._fetch = fetch
original = httpx.AsyncClient
def handler(request):
    assert request.url.host == 'fixture.invalid'
    return httpx.Response(200, content=(digest + '  next-macos-universal.zip\\n').encode()
        if request.url.path.endswith('.sha256') else payload)
httpx.AsyncClient = lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)
sys.argv = ['runtime.py', 'start']
runpy.run_path('scripts/macos/runtime.py', run_name='__main__')
''', encoding='utf-8')
    with (destination / 'update-runtime.log').open('w+') as log:
        process = subprocess.Popen([python, str(harness)], cwd=app,
            env={**env, 'UPDATE_FIXTURE': str(fixture)}, stdout=log, stderr=log)
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError('Update test backend exited before becoming ready')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8765/') as response:
                        html = response.read().decode()
                    break
                except OSError:
                    time.sleep(.5)
            else:
                raise TimeoutError('Update test backend did not start')
            token = re.search(r'<meta name="control-token" content="([^"]+)"', html)[1]
            with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8765/api/update/install',
                    method='POST', headers={'X-Shutdown-Token': token}), timeout=180) as response:
                job = json.load(response)
            for _ in range(600):
                if process.poll() is not None:
                    raise RuntimeError('Updater/launcher exited before restarting')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=1) as response:
                        health = json.load(response)
                    if health.get('appUpdateResult', {}).get('id') == job['id']:
                        assert health['appUpdateResult']['ok'], health
                        assert health['version'] == next_version and health['ok'], health
                        break
                except OSError:
                    pass
                time.sleep(1)
            else:
                raise TimeoutError('Automatic update did not restart the backend')
            assert list((app / '.cache').glob('app-update-*/backup'))
            subprocess.run([str(app / 'STOP.command')], cwd=app, env=env, check=True, timeout=15)
            assert process.wait(timeout=15) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
            log.seek(0)
            print(log.read())
            for update_log in (app / '.cache').glob('app-update-*/update.log'):
                print(update_log.read_text())
print("Extracted package: setup, plugin install, Chromium, health and shutdown passed.")
print('Automatic app update: authenticated download, checksum, backup, install and restart passed.')
