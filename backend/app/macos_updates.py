"""Download and validate an update while the backend is still available."""
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
    result = subprocess.run(['pgrep', '-ix', 'VirtualDJ'], capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError('Could not check VirtualDJ. Close it and retry.')
    return result.returncode == 0


def extract_update(archive: Path, destination: Path, version: str):
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > 3000 or sum(item.file_size for item in entries) > 200 * 1024 * 1024:
            raise RuntimeError('Update archive exceeds the allowed size.')
        wrapper = None
        seen = set()
        for item in entries:
            path = PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in item.filename or ':' in item.filename:
                raise RuntimeError('Unsafe path in update archive.')
            if not path.parts:
                raise RuntimeError('Empty archive path.')
            wrapper = wrapper or path.parts[0]
            if path.parts[0] != wrapper:
                raise RuntimeError('Update must have a single root directory.')
            if item.is_dir():
                continue
            relative = PurePosixPath(*path.parts[1:])
            allowed = relative.parts and (relative.parts[0] in {
                'START.command', 'STOP.command', 'VERSION', 'MACOS_VERSION', 'LICENSE',
                'README.md', 'pyproject.toml', 'uv.lock', 'backend', 'docs'} or
                relative.as_posix().startswith(('scripts/macos/', 'plugin/online-source/prebuilt/macos/')))
            if not allowed or relative in seen or stat.S_ISLNK(item.external_attr >> 16):
                raise RuntimeError('Unexpected or duplicate file in update archive.')
            seen.add(relative)
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if (item.external_attr >> 16) & 0o111 else 0o644)
    required = ['MACOS_VERSION', 'VERSION', 'pyproject.toml', 'uv.lock', 'START.command',
                'STOP.command', 'backend/app/main.py', 'scripts/macos/setup.sh',
                'scripts/macos/runtime.py', 'scripts/macos/install_plugin.py',
                'scripts/macos/apply_update.py',
                'plugin/online-source/prebuilt/macos/VDJ Companion Source.bundle/Contents/MacOS/VDJCompanionSource']
    if any(not (destination / name).is_file() for name in required):
        raise RuntimeError('Incomplete macOS update archive.')
    if (destination / 'MACOS_VERSION').read_text().strip() != version:
        raise RuntimeError('Update package version does not match the release.')


class MacAppUpdates:
    def __init__(self, root: Path, checker):
        self.root, self.checker = root, checker
        self.in_progress = False

    @property
    def supported(self):
        return sys.platform == 'darwin' and os.environ.get('VDJ_MANAGED_LAUNCHER') == '1'

    async def prepare(self):
        if not self.supported:
            raise RuntimeError('Start Companion with START.command to install app updates.')
        if self.in_progress:
            raise RuntimeError('An application update is already running.')
        self.in_progress = True
        job = None
        try:
            if await asyncio.to_thread(virtualdj_running):
                raise RuntimeError('Close VirtualDJ before updating Companion.')
            release = await self.checker.check(force=True)
            if not release.get('updateAvailable'):
                raise RuntimeError(release.get('error') or 'No newer macOS release is available.')
            cache = self.root / '.cache'
            cache.mkdir(exist_ok=True)
            job = Path(tempfile.mkdtemp(prefix='app-update-', dir=cache))
            archive = job / 'update.zip'
            async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
                checksum = await client.get(release['checksumUrl'])
                checksum.raise_for_status()
                match = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?([^\r\n]+)\s*', checksum.text)
                if not match or match[2].strip() != release['assetName']:
                    raise RuntimeError('Invalid update checksum file.')
                expected = match[1].lower()
                if release.get('assetDigest') and release['assetDigest'] != 'sha256:' + expected:
                    raise RuntimeError('GitHub asset digest does not match the checksum.')
                size = 0
                digest = hashlib.sha256()
                async with client.stream('GET', release['downloadUrl']) as response:
                    response.raise_for_status()
                    with archive.open('wb') as output:
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > 32 * 1024 * 1024:
                                raise RuntimeError('Update download exceeds the allowed size.')
                            digest.update(chunk)
                            output.write(chunk)
                if digest.hexdigest() != expected:
                    raise RuntimeError('Update checksum mismatch. Nothing was installed.')
            staged = job / 'staged'
            await asyncio.to_thread(extract_update, archive, staged, release['latestVersion'])
            bundle = staged / 'plugin/online-source/prebuilt/macos/VDJ Companion Source.bundle'
            await asyncio.to_thread(subprocess.run, ['codesign', '--verify', '--strict', str(bundle)], check=True, capture_output=True)
            if await asyncio.to_thread(virtualdj_running):
                raise RuntimeError('VirtualDJ was opened. Close it and retry the update.')
            # Run the trusted installed helper, not code from an unverified download.
            shutil.copy2(self.root / 'scripts/macos/apply_update.py', job / 'apply_update.py')
            request = {'id': uuid.uuid4().hex, 'job': job.name, 'version': release['latestVersion']}
            pending = self.root / 'data/macos-update-pending.json'
            temporary = pending.with_suffix('.tmp')
            temporary.write_text(json.dumps(request), encoding='utf-8')
            temporary.replace(pending)
            return request
        except BaseException:
            self.in_progress = False
            if job:
                shutil.rmtree(job, ignore_errors=True)
            raise
