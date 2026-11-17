"""Prepare a Windows update; the standalone helper installs after shutdown."""
import asyncio
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile

import httpx


def virtualdj_running():
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq virtualdj.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('Could not check VirtualDJ. Close it and retry.')
    return b'"virtualdj.exe"' in result.stdout.lower()


def extract_update(archive, destination, version):
    allowed_files = {'START.bat', 'START-DEBUG.bat', 'STOP.bat', 'VERSION', 'README.md',
                     'CONTRIBUTING.md', 'LICENSE', 'CHANGELOG.md', 'SECURITY.md', 'pyproject.toml', 'uv.lock'}
    seen = set()
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > 3000 or sum(i.file_size for i in entries) > 200 * 1024**2:
            raise RuntimeError('Update archive exceeds the allowed size.')
        for item in entries:
            # Windows ZIPs can contain backslash separators.
            path = PurePosixPath(item.filename.replace('\\', '/'))
            if path.is_absolute() or not path.parts or any(
                part in ('.', '..') or ':' in part or part.endswith((' ', '.')) or
                re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I)
                for part in path.parts
            ):
                raise RuntimeError('Unsafe path in update archive.')
            if stat.S_ISLNK(item.external_attr >> 16):
                raise RuntimeError('Links are not allowed in an update.')
            if item.is_dir():
                continue
            key = path.as_posix().casefold()
            if key in seen or not (path.as_posix() in allowed_files or path.parts[0] in ('backend', 'docs', 'scripts') or
                                  path.as_posix().startswith('plugin/online-source/prebuilt/x64/')):
                raise RuntimeError('Unexpected or duplicate file in update archive.')
            seen.add(key)
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
    required = ('VERSION', 'pyproject.toml', 'uv.lock', 'START.bat', 'backend/app/main.py',
                'scripts/start-backend.ps1', 'scripts/windows/apply_update.py',
                'scripts/windows/recover-update.ps1',
                'plugin/online-source/prebuilt/x64/VDJ Companion Source.dll',
                'plugin/online-source/prebuilt/x64/build-info.json')
    if any(not (destination / name).is_file() for name in required):
        raise RuntimeError('This release does not support automatic Windows updates. Install it manually.')
    if (destination / 'VERSION').read_text(encoding='utf-8').strip() != version:
        raise RuntimeError('Package version does not match the release.')
    plugin = destination / 'plugin/online-source/prebuilt/x64'
    info = json.loads((plugin / 'build-info.json').read_text(encoding='utf-8-sig'))
    if info.get('version') != version or info.get('sha256') != hashlib.sha256((plugin / 'VDJ Companion Source.dll').read_bytes()).hexdigest():
        raise RuntimeError('Plugin checksum or version mismatch.')


class WindowsAppUpdates:
    def __init__(self, root, checker):
        self.root, self.checker = Path(root), checker
        self.in_progress = False

    @property
    def supported(self):
        return sys.platform == 'win32' and os.environ.get('VDJ_WINDOWS_UPDATER') == '1'

    async def prepare(self):
        if not self.supported:
            raise RuntimeError('Start Companion with START.bat to install app updates.')
        if self.in_progress or (self.root / 'data/windows-update-active.json').exists():
            raise RuntimeError('An update is already active. Restart Companion to recover it.')
        self.in_progress = True
        job = None
        marker = self.root / 'data/windows-update-active.json'
        try:
            if await asyncio.to_thread(virtualdj_running):
                raise RuntimeError('Close VirtualDJ before updating Companion.')
            release = await self.checker.check(force=True)
            if not release.get('updateAvailable') or not release.get('checksumUrl'):
                raise RuntimeError(release.get('error') or 'No compatible Windows update is available.')
            cache = self.root / '.cache'
            cache.mkdir(exist_ok=True)
            job = Path(tempfile.mkdtemp(prefix='app-update-', dir=cache))
            archive = job / 'update.zip'
            async with asyncio.timeout(240):
                async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                    checksum = await client.get(release['checksumUrl'])
                    checksum.raise_for_status()
                    match = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?([^\r\n]+)\s*', checksum.text)
                    if not match or match[2].strip() != release['assetName']:
                        raise RuntimeError('Invalid update checksum file.')
                    expected = match[1].lower()
                    if release.get('assetDigest') and release['assetDigest'] != 'sha256:' + expected:
                        raise RuntimeError('GitHub digest does not match the checksum.')
                    size, digest = 0, hashlib.sha256()
                    async with client.stream('GET', release['downloadUrl']) as response:
                        response.raise_for_status()
                        with archive.open('wb') as output:
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > 32 * 1024**2:
                                    raise RuntimeError('Update download exceeds the allowed size.')
                                digest.update(chunk)
                                output.write(chunk)
                    if digest.hexdigest() != expected:
                        raise RuntimeError('Update checksum mismatch. Nothing was installed.')
            await asyncio.to_thread(extract_update, archive, job / 'staged', release['latestVersion'])
            if await asyncio.to_thread(virtualdj_running):
                raise RuntimeError('VirtualDJ was opened. Close it and retry.')
            shutil.copy2(self.root / 'scripts/windows/apply_update.py', job / 'apply_update.py')
            request = {'id': uuid.uuid4().hex, 'job': job.name, 'version': release['latestVersion'], 'parent': os.getpid()}
            temporary = marker.with_suffix('.tmp')
            temporary.write_text(json.dumps(request), encoding='utf-8')
            temporary.replace(marker)
            # Base Python is outside .venv, so the stopped application's environment can be replaced.
            with (job / 'update.log').open('ab') as log:
                subprocess.Popen([sys._base_executable, str(job / 'apply_update.py'), str(self.root)],
                                 cwd=self.root, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            return request
        except BaseException:
            self.in_progress = False
            marker.unlink(missing_ok=True)
            if job:
                shutil.rmtree(job, ignore_errors=True)
            raise
