import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import httpx
import pytest

from backend.app import windows_updates as updates

spec = importlib.util.spec_from_file_location('windows_installer', Path(__file__).parents[1] / 'scripts/windows/apply_update.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def archive(path, extras=None):
    dll = b'MZ-test-plugin'
    files = {'VERSION': b'0.3.1', 'pyproject.toml': b'project', 'uv.lock': b'lock',
             'START.bat': b'launcher', 'backend/app/main.py': b'app',
             'scripts/start-backend.ps1': b'start', 'scripts/windows/apply_update.py': b'helper',
             'scripts/windows/recover-update.ps1': b'recover',
             'plugin/online-source/prebuilt/x64/VDJ Companion Source.dll': dll,
             'plugin/online-source/prebuilt/x64/build-info.json': json.dumps({'version': '0.3.1', 'sha256': hashlib.sha256(dll).hexdigest()}).encode()}
    files.update(extras or {})
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


@pytest.mark.parametrize('name', ['../escape', 'C:/escape', '/escape', 'data/library.sqlite3',
    'tools/python.exe', '.env', 'docs/file:stream', 'docs/CON.txt', 'docs/name.', 'docs/name ',
    'BACKEND/app/main.py'])
def test_archive_rejects_unsafe_or_user_data_paths(tmp_path, name):
    with pytest.raises(RuntimeError):
        updates.extract_update(archive(tmp_path / 'update.zip', {name: b'bad'}), tmp_path / 'stage', '0.3.1')


def test_archive_version_plugin_and_helper_validation(tmp_path):
    path = archive(tmp_path / 'update.zip')
    updates.extract_update(path, tmp_path / 'good', '0.3.1')
    with pytest.raises(RuntimeError, match='version'):
        updates.extract_update(path, tmp_path / 'wrong', '0.3.2')
    path = archive(tmp_path / 'bad.zip', {'plugin/online-source/prebuilt/x64/VDJ Companion Source.dll': b'corrupt'})
    with pytest.raises(RuntimeError, match='checksum'):
        updates.extract_update(path, tmp_path / 'corrupt', '0.3.1')


@pytest.fixture
def install_tree(tmp_path, monkeypatch):
    root = tmp_path / 'App with spaces'
    root.mkdir()
    (root / 'VERSION').write_text('0.3.0')
    (root / 'backend').mkdir()
    (root / 'backend/old.py').write_text('old app')
    (root / '.venv').mkdir()
    (root / '.venv/old').write_text('old environment')
    (root / 'data/library').mkdir(parents=True)
    (root / 'data/library/private.sqlite3').write_bytes(b'user lists')
    (root / 'data/library/media.mp4').write_bytes(b'user video')
    target = tmp_path / 'VirtualDJ/plugin.dll'
    target.parent.mkdir()
    target.write_bytes(b'old plugin')
    job = root / '.cache/app-update-test'
    job.mkdir(parents=True)
    updates.extract_update(archive(job / 'update.zip'), job / 'staged', '0.3.1')
    monkeypatch.setattr(installer, 'plugin_target', lambda: target)
    monkeypatch.setattr(installer, 'check_virtualdj', lambda: None)
    monkeypatch.setattr(installer, 'install_dependencies', lambda root: (root / '.venv').mkdir())
    monkeypatch.setattr(installer, 'start_backend', lambda root: SimpleNamespace(poll=lambda: 0))
    monkeypatch.setattr(installer, 'healthy', lambda process, version: None)
    return root, job, target


def test_success_preserves_library_and_keeps_backup(install_tree):
    root, job, target = install_tree
    assert installer.apply(root, job, {'version': '0.3.1'})['ok']
    assert (root / 'VERSION').read_text() == '0.3.1'
    assert target.read_bytes() == b'MZ-test-plugin'
    assert (root / 'data/library/private.sqlite3').read_bytes() == b'user lists'
    assert (root / 'data/library/media.mp4').read_bytes() == b'user video'
    assert json.loads((job / 'journal.json').read_text())['phase'] == 'complete'
    assert installer.apply(root, job, {}, recover=True)['ok']


@pytest.mark.parametrize('step', ['install_dependencies', 'healthy'])
def test_failed_dependency_or_startup_restores_app_venv_plugin(install_tree, monkeypatch, step):
    root, job, target = install_tree
    def fail(*args):
        raise RuntimeError('simulated failure')
    monkeypatch.setattr(installer, step, fail)
    with pytest.raises(RuntimeError):
        installer.apply(root, job, {'version': '0.3.1'})
    assert (root / 'VERSION').read_text() == '0.3.0'
    assert (root / 'backend/old.py').read_text() == 'old app'
    assert (root / '.venv/old').read_text() == 'old environment'
    assert target.read_bytes() == b'old plugin'
    assert (root / 'data/library/media.mp4').read_bytes() == b'user video'
    assert json.loads((job / 'journal.json').read_text())['phase'] == 'rolled-back'


def test_interrupted_install_is_recovered(install_tree, monkeypatch):
    root, job, target = install_tree
    original = installer.rollback
    monkeypatch.setattr(installer, 'install_dependencies', lambda root: (_ for _ in ()).throw(RuntimeError('failure')))
    monkeypatch.setattr(installer, 'rollback', lambda *args: (_ for _ in ()).throw(RuntimeError('interrupted')))
    with pytest.raises(RuntimeError):
        installer.apply(root, job, {'version': '0.3.1'})
    monkeypatch.setattr(installer, 'rollback', original)
    assert not installer.apply(root, job, {}, recover=True)['ok']
    assert (root / 'VERSION').read_text() == '0.3.0'
    assert target.read_bytes() == b'old plugin'


async def test_bad_checksum_never_launches_helper(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.WindowsAppUpdates, 'supported', property(lambda self: True))
    monkeypatch.setattr(updates, 'virtualdj_running', lambda: False)
    async def check(**kwargs):
        return {'updateAvailable': True, 'latestVersion': '0.3.1', 'assetName': 'update.zip',
                'checksumUrl': 'https://example.test/checksum', 'downloadUrl': 'https://example.test/update.zip'}
    original = httpx.AsyncClient
    def handler(request):
        return httpx.Response(200, content=(b'0'*64 + b'  update.zip\n') if request.url.path == '/checksum' else b'bad')
    monkeypatch.setattr(updates.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    manager = updates.WindowsAppUpdates(tmp_path, SimpleNamespace(check=check))
    with pytest.raises(RuntimeError, match='checksum mismatch'):
        await manager.prepare()
    assert not manager.in_progress
    assert not (tmp_path / 'data/windows-update-active.json').exists()
    assert not list((tmp_path / '.cache').iterdir())


async def test_running_virtualdj_blocks_before_download(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.WindowsAppUpdates, 'supported', property(lambda self: True))
    monkeypatch.setattr(updates, 'virtualdj_running', lambda: True)
    manager = updates.WindowsAppUpdates(tmp_path, None)
    with pytest.raises(RuntimeError, match='Close VirtualDJ'):
        await manager.prepare()
    assert not manager.in_progress and not (tmp_path / '.cache').exists()
