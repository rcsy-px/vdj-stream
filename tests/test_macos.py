import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.app.browser_tools import chromium_executable
from backend.app.update_checker import GitHubReleaseChecker


@pytest.mark.parametrize("arch", ["arm64", "x86_64"])
def test_mac_chromium_matches_revision_and_arch(tmp_path, monkeypatch, arch):
    manifest = tmp_path / 'driver/package/browsers.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'browsers': [{'name': 'chromium', 'revision': '123',
        'revisionOverrides': {'mac15-arm64': '124'}}]}))
    monkeypatch.setattr('backend.app.browser_tools.files', lambda _: tmp_path)
    monkeypatch.setattr('backend.app.browser_tools.sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr('backend.app.browser_tools.platform', SimpleNamespace(mac_ver=lambda: ('15.0', '', ''), machine=lambda: arch))
    stale = tmp_path / 'chromium-122/chrome-mac/Chromium.app/Contents/MacOS/Chromium'
    stale.parent.mkdir(parents=True)
    stale.touch()
    assert chromium_executable(tmp_path) is None
    revision = '124' if arch == 'arm64' else '123'
    current = tmp_path / f'chromium-{revision}/chrome-mac-{arch}/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
    current.parent.mkdir(parents=True)
    current.touch()
    assert chromium_executable(tmp_path) == current


async def test_mac_never_offers_windows_download(monkeypatch):
    monkeypatch.setattr('backend.app.update_checker.sys', SimpleNamespace(platform='darwin'))
    def handler(request):
        return httpx.Response(200, json={'tag_name': 'v0.3.0', 'assets': [{
            'name': 'companion-windows-x64.zip',
            'browser_download_url': 'https://github.com/rcsy-px/vdj-stream/releases/download/v0.3.0/companion-windows-x64.zip'}]})
    original = httpx.AsyncClient
    monkeypatch.setattr('backend.app.update_checker.httpx.AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    result = await GitHubReleaseChecker('0.2.0', 'rcsy-px/vdj-stream').check()
    assert result['downloadUrl'] is None
    assert result['updateAvailable'] is False


def test_plugin_paths_refuse_ambiguous_home(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'scripts/macos/install_plugin.py'
    spec = importlib.util.spec_from_file_location('mac_install', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv('VDJ_HOME', raising=False)
    modern = tmp_path / 'Library/Application Support/VirtualDJ'
    legacy = tmp_path / 'Documents/VirtualDJ'
    (modern / 'PluginsMacArm').mkdir(parents=True)
    assert module.destinations(tmp_path) == [modern / 'PluginsMacArm/OnlineSources']
    legacy.mkdir(parents=True)
    with pytest.raises(RuntimeError, match='multiple/custom'):
        module.destinations(tmp_path)
    monkeypatch.setenv('VDJ_HOME', str(modern))
    assert module.destinations(tmp_path) == [modern / 'PluginsMacArm/OnlineSources']
