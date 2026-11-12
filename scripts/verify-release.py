"""Validate archive contents, checksums, and a fresh extracted app without network."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
version = (root / "VERSION").read_text().strip()
archive = root / "dist" / f"vdj-companion-{version}-windows-x64.zip"
expected = Path(str(archive) + ".sha256").read_text().split()[0]
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected, "Archive checksum mismatch"
required = {
    "START.bat", "STOP.bat", "VERSION", "README.md", "CONTRIBUTING.md", "uv.lock",
    "backend/app/web/index.html", "backend/app/web/app.js", "backend/app/web/style.css",
    "docs/assets/companion-bot.png", "scripts/download-tools.ps1", "scripts/setup-and-start.ps1",
    "docs/assets/companion-bot.svg",
    "plugin/online-source/prebuilt/x64/VDJ Companion Source.dll",
    "plugin/online-source/prebuilt/x64/build-info.json",
}
with zipfile.ZipFile(archive) as package, tempfile.TemporaryDirectory(prefix="vdj-release-") as temporary:
    names = {name.replace("\\", "/") for name in package.namelist()}
    assert required <= names, f"Missing: {required - names}"
    for name in names:
        path = Path(name)
        assert not path.is_absolute() and ".." not in path.parts
        assert not {"mockups", ".cache", ".git", ".venv", "__pycache__", "tests"}.intersection(path.parts), name
        assert path.suffix not in {".pyc", ".log", ".sqlite", ".sqlite3"}, name
        assert path.name != ".env", name
    assert package.testzip() is None
    package.extractall(temporary)
    extracted = Path(temporary)
    metadata = json.loads((extracted / "plugin/online-source/prebuilt/x64/build-info.json").read_text(encoding="utf-8-sig"))
    assert metadata["version"] == version
    assert metadata["sha256"] == hashlib.sha256((extracted / "plugin/online-source/prebuilt/x64/VDJ Companion Source.dll").read_bytes()).hexdigest()
    subprocess.run([sys.executable, "-c", """
from fastapi.testclient import TestClient
from backend.app.main import app
with TestClient(app) as client:
    for path in ('/', '/static/app.js', '/static/style.css', '/assets/logo.svg', '/api/health'):
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
    assert client.post('/api/diagnostics').status_code == 403
print('Extracted application smoke check passed')
"""], cwd=temporary, check=True)
print(f"Archive verified: {archive.name}")
