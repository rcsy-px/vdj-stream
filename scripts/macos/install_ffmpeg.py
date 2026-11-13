"""Install private, pinned Mac tools; never modify a system FFmpeg installation."""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ('ffmpeg', 'ffprobe')
# Publisher: https://ffmpeg.martin-riedl.de/ (signed static release builds).
# Checksums are pinned here, not trusted from a mutable latest-download response.
BUILDS = {
    'x86_64': ('amd64/1789931006_9.0.2', {
        'ffmpeg': '7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4',
        'ffprobe': '2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd'}),
    'arm64': ('arm64/1789931890_9.0.2', {
        'ffmpeg': 'c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924',
        'ffprobe': 'fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6'}),
}
MAX_SIZE = 200 * 1024 * 1024


def working(path):
    if not path.is_file() or not os.access(path, os.X_OK):
        return False
    try:
        return subprocess.run([str(path), '-version'], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def download(url, destination):
    started = time.monotonic()
    size = 0
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        with client.stream('GET', url) as response:
            response.raise_for_status()
            if response.url.scheme != 'https':
                raise RuntimeError('FFmpeg download must use HTTPS.')
            with destination.open('wb') as output:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_SIZE or time.monotonic() - started > 300:
                        raise RuntimeError('FFmpeg download exceeded its size or time limit.')
                    output.write(chunk)


def unpack(archive, target, expected):
    with archive.open('rb') as source:
        actual = hashlib.file_digest(source, 'sha256').hexdigest()
    if actual != expected:
        raise RuntimeError('FFmpeg checksum mismatch. No tools were installed; retry setup.')
    with zipfile.ZipFile(archive) as package:
        matches = [item for item in package.infolist() if item.filename == target.name]
        if len(matches) != 1:
            raise RuntimeError('FFmpeg archive does not contain the expected executable.')
        item = matches[0]
        if item.file_size > MAX_SIZE or stat.S_ISLNK(item.external_attr >> 16) or item.is_dir():
            raise RuntimeError('Invalid FFmpeg executable in archive.')
        # Extract only the exact root member; never extract arbitrary archive paths.
        with package.open(item) as source, target.open('wb') as output:
            shutil.copyfileobj(source, output)
    target.chmod(0o755)


def install(root=ROOT, architecture=None, override=None):
    architecture = architecture or platform.machine()
    if architecture not in BUILDS:
        raise RuntimeError('Unsupported Mac CPU architecture.')
    parent = root / 'tools/ffmpeg'
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / 'bin'
    if not override and all(working(destination / name) for name in TOOLS):
        print('FFmpeg and ffprobe are ready (existing private tools).')
        return
    with tempfile.TemporaryDirectory(prefix='install-', dir=parent) as temporary:
        stage = Path(temporary) / 'bin'
        stage.mkdir()
        if override:
            sources = [(Path(override).expanduser() / name).resolve(strict=True) for name in TOOLS]
            if not all(working(path) for path in sources):
                raise RuntimeError('FFMPEG_BIN_DIR must contain working ffmpeg and ffprobe executables.')
            # A later launch may point at the managed directory itself.
            if all(source == (destination / name).resolve() for source, name in zip(sources, TOOLS)):
                return
            for source, name in zip(sources, TOOLS):
                (stage / name).symlink_to(source)
        else:
            build, checksums = BUILDS[architecture]
            for name in TOOLS:
                print(f'Downloading {name} for {architecture}…', flush=True)
                archive = Path(temporary) / (name + '.zip')
                download(f'https://ffmpeg.martin-riedl.de/download/macos/{build}/{name}.zip', archive)
                unpack(archive, stage / name, checksums[name])
                subprocess.run(['codesign', '--verify', '--strict', str(stage / name)], check=True, capture_output=True)
                subprocess.run(['lipo', str(stage / name), '-verify_arch', architecture], check=True, capture_output=True)
                if not working(stage / name):
                    raise RuntimeError(f'{name} could not run on this Mac. Existing tools were not changed.')
        # Validate both tools before replacing anything; preserve old symlinks as symlinks.
        backup = Path(temporary) / 'previous'
        existed = destination.exists() or destination.is_symlink()
        if existed:
            destination.rename(backup)
        try:
            stage.rename(destination)
        except BaseException:
            if existed:
                backup.rename(destination)
            raise
    print('FFmpeg and ffprobe are ready. No Homebrew installation is needed.')


if __name__ == '__main__':
    if platform.system() != 'Darwin':
        raise SystemExit('This installer requires macOS.')
    try:
        install(override=os.environ.get('FFMPEG_BIN_DIR'))
    except Exception as exc:
        raise SystemExit(f'FFmpeg setup failed: {exc}\nRetry START.command, or set FFMPEG_BIN_DIR to your existing tools folder.')
