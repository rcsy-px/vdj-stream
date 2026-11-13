"""Create a separate macOS preview archive, never a Windows/stable release."""
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
version = (ROOT / "MACOS_VERSION").read_text().strip()
prefix = f"vdj-companion-{version}"
dist = ROOT / "dist"
dist.mkdir(exist_ok=True)
archive = dist / f"{prefix}-macos-universal.zip"
bundle = ROOT / "plugin/online-source/build/macos/VDJ Companion Source.bundle"
if not (bundle / "Contents/MacOS/VDJCompanionSource").is_file():
    raise SystemExit("Build the macOS bundle before packaging.")
entries = {}
for name in ("START.command", "STOP.command", "VERSION", "MACOS_VERSION", "LICENSE", "pyproject.toml", "uv.lock"):
    entries[name] = ROOT / name
entries["README.md"] = ROOT / "docs/MACOS.md"
for name in ("setup.sh", "runtime.py", "install_plugin.py", "install_ffmpeg.py", "apply_update.py"):
    entries[f"scripts/macos/{name}"] = ROOT / "scripts/macos" / name
for name in ("backend", "docs/assets"):
    for path in (ROOT / name).rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            entries[path.relative_to(ROOT).as_posix()] = path
entries["docs/MACOS.md"] = ROOT / "docs/MACOS.md"
for path in bundle.rglob("*"):
    if path.is_file():
        entries["plugin/online-source/prebuilt/macos/VDJ Companion Source.bundle/" + path.relative_to(bundle).as_posix()] = path
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
    for name, path in sorted(entries.items()):
        output.write(path, f"{prefix}/{name}")
with zipfile.ZipFile(archive) as output:
    assert output.testzip() is None
    for entry in output.infolist():
        assert not entry.filename.endswith((".dll", ".exe", ".bat", ".ps1"))
        if entry.filename.endswith((".command", ".sh", "/VDJCompanionSource")):
            assert (entry.external_attr >> 16) & 0o111, entry.filename
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
print(archive)
