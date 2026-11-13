import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app, shutdown_token
from backend.app.macos_releases import MacReleaseChecker, mac_version
from backend.app.macos_updates import MacAppUpdates, extract_update


def release(tag, platform='macos-universal', draft=False):
    prefix = 'https://github.com/rcsy-px/vdj-stream/releases/'
    name = f'companion-{tag}-{platform}.zip'
    return {'tag_name': tag, 'draft': draft, 'html_url': prefix + 'tag/' + tag,
            'assets': [{'name': name + suffix, 'browser_download_url': prefix + 'download/' + tag + '/' + name + suffix}
                       for suffix in ('', '.sha256')]}


async def test_mac_channel_sorts_betas_and_filters_windows_and_drafts(monkeypatch):
    items = [release('macos-v0.2.0-beta.3'), release('v9.0.0', 'windows-x64'),
             release('macos-v0.2.0-beta.11'), release('macos-v0.4.0-beta.1', draft=True)]
    original = httpx.AsyncClient
    def handler(request):
        assert '/releases?' in str(request.url)
        return httpx.Response(200, json=items)
    monkeypatch.setattr('backend.app.macos_releases.httpx.AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    result = await MacReleaseChecker('0.2.0-beta.2', 'rcsy-px/vdj-stream').check()
    assert result['latestVersion'] == '0.2.0-beta.11' and result['updateAvailable']
    assert mac_version('0.2.0') > mac_version('0.2.0-beta.999')
    assert mac_version('v0.3.0-beta.1') > mac_version('0.2.0')


async def test_mac_channel_rejects_foreign_assets_and_missing_checksum(monkeypatch):
    items = [release('macos-v0.3.0-beta.1'), release('macos-v0.3.0-beta.2')]
    items[0]['assets'][0]['browser_download_url'] = 'https://evil.example/payload.zip'
    items[1]['assets'].pop()
    original = httpx.AsyncClient
    monkeypatch.setattr('backend.app.macos_releases.httpx.AsyncClient', lambda **kwargs: original(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=items)), **kwargs))
    result = await MacReleaseChecker('0.2.0-beta.2', 'rcsy-px/vdj-stream').check()
    assert not result['updateAvailable'] and result['downloadUrl'] is None


@pytest.mark.parametrize('name', ['../escape', 'root/../../escape', '/absolute', 'root/data/database', 'root/.env', 'root/tools/python', 'root\\escape'])
def test_archive_rejects_paths_outside_managed_files(tmp_path, name):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr(name, b'bad')
    with pytest.raises(RuntimeError):
        extract_update(archive, tmp_path / 'staged', '0.2.0-beta.2')
    assert not (tmp_path / 'escape').exists()


def test_archive_rejects_symlink(tmp_path):
    archive = tmp_path / 'bad.zip'
    item = zipfile.ZipInfo('root/backend/link')
    item.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr(item, '/tmp/outside')
    with pytest.raises(RuntimeError, match='Unexpected'):
        extract_update(archive, tmp_path / 'staged', '0.2.0-beta.2')


async def test_checksum_failure_never_schedules_install(tmp_path, monkeypatch):
    monkeypatch.setattr('backend.app.macos_updates.sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setenv('VDJ_MANAGED_LAUNCHER', '1')
    monkeypatch.setattr('backend.app.macos_updates.virtualdj_running', lambda: False)
    async def check(**kwargs):
        return {'updateAvailable': True, 'checksumUrl': 'https://example.test/file.sha256',
                'downloadUrl': 'https://example.test/file.zip', 'assetName': 'file.zip', 'latestVersion': '0.2.0-beta.3'}
    original = httpx.AsyncClient
    def handler(request):
        return httpx.Response(200, content=(b'0' * 64 + b'  file.zip\n') if request.url.path.endswith('sha256') else b'wrong payload')
    monkeypatch.setattr('backend.app.macos_updates.httpx.AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    manager = MacAppUpdates(tmp_path, SimpleNamespace(check=check))
    with pytest.raises(RuntimeError, match='checksum mismatch'):
        await manager.prepare()
    assert not manager.in_progress
    assert not (tmp_path / 'data/macos-update-pending.json').exists()
    assert not list((tmp_path / '.cache').iterdir())


def test_installer_endpoint_requires_local_control_token():
    with TestClient(app) as client:
        assert client.post('/api/update/install').status_code == 403
    with TestClient(app, client=('203.0.113.1', 1)) as client:
        assert client.post('/api/update/install', headers={'X-Shutdown-Token': shutdown_token}).status_code == 403


def load_helper():
    path = Path(__file__).resolve().parents[1] / 'scripts/macos/apply_update.py'
    spec = importlib.util.spec_from_file_location('apply_mac_update', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transaction_rolls_back_files_venv_and_plugin_on_setup_failure(tmp_path, monkeypatch):
    module = load_helper()
    root, job, plugin = tmp_path / 'app', tmp_path / 'job', tmp_path / 'plugins'
    root.mkdir(); job.mkdir(); plugin.mkdir()
    (root / 'data').mkdir()
    (root / 'data/user.sqlite3').write_bytes(b'user state')
    (root / '.venv').mkdir()
    (root / '.venv/original').write_text('old dependencies')
    (root / 'MACOS_VERSION').write_text('0.2.0-beta.2')
    (root / 'scripts/macos').mkdir(parents=True)
    (root / 'scripts/macos/install_plugin.py').write_text(
        f'from pathlib import Path\nBUNDLE="plugin.bundle"\ndef destinations(*args): return [Path({str(plugin)!r})]\n')
    (plugin / 'plugin.bundle').mkdir()
    (plugin / 'plugin.bundle/old').write_text('old native plugin')
    staged = job / 'staged'
    staged.mkdir()
    (staged / 'MACOS_VERSION').write_text('0.2.0-beta.3')
    def fail(command, **kwargs):
        if command[0] == 'pgrep': return SimpleNamespace(returncode=1)
        (root / '.venv/original').write_text('partially updated dependencies')
        raise RuntimeError('offline during setup')
    monkeypatch.setattr(module.subprocess, 'run', fail)
    with pytest.raises(RuntimeError, match='offline'):
        module.apply(root, job, {'version': '0.2.0-beta.3'})
    assert (root / 'MACOS_VERSION').read_text() == '0.2.0-beta.2'
    assert (root / '.venv/original').read_text() == 'old dependencies'
    assert (root / 'data/user.sqlite3').read_bytes() == b'user state'
    assert (plugin / 'plugin.bundle/old').read_text() == 'old native plugin'
    assert json.loads((job / 'journal.json').read_text())['phase'] == 'rolled-back'
