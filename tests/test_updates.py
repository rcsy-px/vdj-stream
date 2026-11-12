import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app, shutdown_token
from backend.app.update_checker import GitHubReleaseChecker
from backend.app.ytdlp_updates import YtDlpUpdates


@pytest.mark.asyncio
async def test_failed_release_check_recovers_after_one_minute(monkeypatch):
    checker = GitHubReleaseChecker("0.1.2", "rcsy-px/vdj-stream")
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("network blocked")
        return {"latestVersion": "0.1.3", "updateAvailable": True}

    monkeypatch.setattr(checker, "_fetch", fetch)
    assert "network permissions" in (await checker.check())["errorDetail"]
    assert (await checker.check())["error"]
    assert calls == 1
    checker._cached_at -= 61
    assert (await checker.check())["latestVersion"] == "0.1.3"
    assert calls == 2


@pytest.mark.asyncio
async def test_manual_check_bypasses_success_cache(monkeypatch):
    checker = GitHubReleaseChecker("0.1.2", "rcsy-px/vdj-stream")
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return {"latestVersion": f"0.1.{calls + 2}"}

    monkeypatch.setattr(checker, "_fetch", fetch)
    assert (await checker.check())["latestVersion"] == "0.1.3"
    assert (await checker.check())["latestVersion"] == "0.1.3"
    assert (await checker.check(force=True))["latestVersion"] == "0.1.4"


def test_manual_check_endpoint_forces_refresh(monkeypatch):
    async def check(force=False):
        return {"forced": force}

    monkeypatch.setattr("backend.app.main.update_checker.check", check)
    with TestClient(app) as client:
        response = client.get("/api/update?refresh=true")
        assert response.json() == {"forced": True}
        assert response.headers["cache-control"] == "no-store"


async def test_manual_checks_bypass_upstream_cache_without_extra_polling(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"tag_name": f"v0.2.{len(requests)}"})
    original_client = httpx.AsyncClient
    monkeypatch.setattr("backend.app.update_checker.httpx.AsyncClient", lambda **kwargs:
                        original_client(transport=httpx.MockTransport(handler), **kwargs))
    checker = GitHubReleaseChecker("0.2.0", "rcsy-px/vdj-stream")
    assert (await checker.check())["latestVersion"] == "0.2.1"
    assert (await checker.check())["latestVersion"] == "0.2.1"
    assert len(requests) == 1
    assert (await checker.check(force=True))["latestVersion"] == "0.2.2"
    assert len(requests) == 2
    assert requests[0].url.params["_"] != requests[1].url.params["_"]
    for request in requests:
        assert "no-cache" in request.headers["cache-control"]
        assert request.headers["pragma"] == "no-cache"


def test_engine_version_response_is_not_cached(monkeypatch):
    async def check(force=False):
        return {"forced": force}
    monkeypatch.setattr("backend.app.main.ytdlp_updates.check", check)
    with TestClient(app) as client:
        response = client.get("/api/ytdlp?refresh=true")
        assert response.json() == {"forced": True}
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_ytdlp_version_re_read_even_when_latest_is_cached(tmp_path, monkeypatch):
    manager = YtDlpUpdates(tmp_path / "yt-dlp.exe")
    versions = iter(["2026.06.09", "2026.10.26"])

    async def installed():
        return next(versions)

    async def fetch():
        return {"latestVersion": "2026.10.26"}

    monkeypatch.setattr(manager, "installed_version", installed)
    monkeypatch.setattr(manager.releases, "_fetch", fetch)
    assert (await manager.check())["updateAvailable"] is True
    result = await manager.check()
    assert result["currentVersion"] == "2026.10.26"
    assert result["updateAvailable"] is False


@pytest.mark.asyncio
async def test_ytdlp_missing_reports_error_without_claiming_current(tmp_path, monkeypatch):
    manager = YtDlpUpdates(tmp_path / "missing.exe")

    async def fetch():
        return {"latestVersion": "2026.10.26"}

    monkeypatch.setattr(manager.releases, "_fetch", fetch)
    result = await manager.check()
    assert result["currentVersion"] is None
    assert "missing" in result["error"]
    assert result["updateAvailable"] is False


@pytest.mark.asyncio
async def test_ytdlp_update_verifies_installed_version(tmp_path, monkeypatch):
    manager = YtDlpUpdates(tmp_path / "yt-dlp.exe")
    versions = iter(["2026.06.09", "2026.10.26", "2026.10.26"])
    commands = []

    async def run(*args, **kwargs):
        commands.append(args)
        return next(versions) if args == ("--version",) else "Updated"

    async def fetch():
        return {"latestVersion": "2026.10.26"}

    monkeypatch.setattr(manager.runner, "_execute", run)
    monkeypatch.setattr(manager.releases, "_fetch", fetch)
    result = await manager.update()
    assert ("--update-to", "stable") in commands
    assert result["currentVersion"] == "2026.10.26"
    assert "Updated yt-dlp" in result["message"]
    assert result["updateAvailable"] is False
    assert result["updating"] is False


@pytest.mark.asyncio
async def test_ytdlp_update_failure_releases_lock(tmp_path, monkeypatch):
    manager = YtDlpUpdates(tmp_path / "yt-dlp.exe")

    async def run(*args, **kwargs):
        if args == ("--version",):
            return "2026.06.09"
        raise TimeoutError()

    monkeypatch.setattr(manager.runner, "_execute", run)
    with pytest.raises(RuntimeError, match="timed out"):
        await manager.update()
    assert manager._update_lock.locked() is False
    assert "timed out" in manager.last_error


@pytest.mark.asyncio
async def test_ytdlp_duplicate_update_rejected(tmp_path):
    manager = YtDlpUpdates(tmp_path / "yt-dlp.exe")
    async with manager._update_lock:
        with pytest.raises(RuntimeError, match="already running"):
            await manager.update()


@pytest.mark.asyncio
async def test_ytdlp_process_timeout_kills_and_reaps(tmp_path, monkeypatch):
    executable = tmp_path / "yt-dlp.exe"
    executable.touch()
    manager = YtDlpUpdates(executable)

    class Process:
        returncode = None
        killed = False
        reaped = False

        async def communicate(self):
            if self.killed:
                self.reaped = True
                return b"", b""
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True

    process = Process()

    async def spawn(*args, **kwargs):
        assert args == (str(executable), "--ignore-config", "--version")
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(TimeoutError):
        await manager._run("--version", timeout=.01)
    assert process.killed and process.reaped


def test_ytdlp_update_requires_local_control_token(monkeypatch):
    called = False

    async def update():
        nonlocal called
        called = True
        return {"currentVersion": "2026.10.26"}

    monkeypatch.setattr("backend.app.main.ytdlp_updates.update", update)
    with TestClient(app) as client:
        assert client.post("/api/ytdlp/update").status_code == 403
        assert not called
        response = client.post("/api/ytdlp/update", headers={"X-Shutdown-Token": shutdown_token})
        assert response.status_code == 200
        assert response.json()["currentVersion"] == "2026.10.26"
    with TestClient(app, client=("203.0.113.10", 1234)) as client:
        assert client.post("/api/ytdlp/update", headers={"X-Shutdown-Token": shutdown_token}).status_code == 403


def test_ytdlp_update_failure_is_actionable(monkeypatch):
    async def update():
        raise RuntimeError("Update timed out. Retry.")

    monkeypatch.setattr("backend.app.main.ytdlp_updates.update", update)
    with TestClient(app) as client:
        response = client.post("/api/ytdlp/update", headers={"X-Shutdown-Token": shutdown_token})
        assert response.status_code == 502
        assert response.json()["detail"] == "Update timed out. Retry."
