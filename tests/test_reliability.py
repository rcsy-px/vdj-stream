import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app, shutdown_token
from backend.app.diagnostics import Diagnostics
from backend.app.stream.formats import ResolvedStream
from backend.app.stream.naming import stream_filename
from backend.app.stream.proxy import proxy_youtube_stream
from backend.app.stream.resolver import YtDlpResolver
from backend.app.ytdlp_runner import YtDlpRunner, YtDlpBusyError
from backend.app.browser_tools import chromium_executable
from backend.app.stream.proxy import ManagedStreamResponse


async def test_update_drains_readers_and_blocks_new_reads(monkeypatch):
    runner = YtDlpRunner(Path('unused'), concurrency=1, queue_timeout=.02)
    entered, release = asyncio.Event(), asyncio.Event()
    async def execute(*args, **kwargs):
        entered.set()
        await release.wait()
        return 'done'
    monkeypatch.setattr(runner, '_execute', execute)
    task = asyncio.create_task(runner.run('search'))
    await entered.wait()
    async def update():
        async with runner.exclusive():
            assert runner._active == 0
            with pytest.raises(YtDlpBusyError):
                await runner.run('blocked')
    writer = asyncio.create_task(update())
    await asyncio.sleep(0)
    assert runner.updating
    assert not writer.done()
    release.set()
    await asyncio.gather(task, writer)
    assert not runner.updating
    assert await runner.run('after') == 'done'


async def test_cancelled_waiting_writer_releases_readers(monkeypatch):
    runner = YtDlpRunner(Path('unused'))
    async with runner._slot(False, 1):
        async def writer():
            async with runner.exclusive():
                pytest.fail('must wait')
        task = asyncio.create_task(writer())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not runner.updating
    assert runner._active == 0


async def test_cancelled_process_is_killed_and_reaped(tmp_path, monkeypatch):
    executable = tmp_path / 'yt-dlp.exe'
    executable.touch()
    entered = asyncio.Event()
    class Process:
        returncode = None
        killed = reaped = False
        async def communicate(self):
            if self.killed:
                self.reaped = True
                return b'', b''
            entered.set()
            await asyncio.Event().wait()
        def kill(self):
            self.killed = True
    process = Process()
    async def spawn(*args, **kwargs):
        assert '--ignore-config' in args
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    runner = YtDlpRunner(executable)
    task = asyncio.create_task(runner.run('search'))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed and process.reaped and runner._active == 0


async def test_resolver_deduplicates_and_bounds_cache(monkeypatch):
    resolver = YtDlpResolver(Path('unused'), max_cache_entries=2)
    calls = 0
    async def run(*args, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return json.dumps({'url': 'https://audio.example/file', 'ext': 'webm'})
    monkeypatch.setattr(resolver.runner, 'run', run)
    results = await asyncio.gather(*(resolver.resolve('abcdefghijk') for _ in range(5)))
    assert calls == 1 and not resolver._locks
    assert all(result.format.ext == 'webm' for result in results)
    await resolver.resolve('abcdefghij2')
    await resolver.resolve('abcdefghij3')
    assert len(resolver._cache) == 2 and 'abcdefghijk' not in resolver._cache
    assert stream_filename('Track', 'abcdefghijk', 'webm') == 'Track.webm'


@pytest.mark.parametrize('status', [206, 416, 'timeout'])
async def test_proxy_closes_connections_and_preserves_range(monkeypatch, status):
    clients = []
    async def resolve(*args, **kwargs):
        return ResolvedStream(video_id='abcdefghijk', title='Track', upstream_url='https://audio.example/file')
    def handler(request):
        assert request.headers['range'] == 'bytes=4-7'
        if status == 'timeout':
            raise httpx.ReadTimeout('slow')
        return httpx.Response(status, headers={'Content-Range': 'bytes */4' if status == 416 else 'bytes 4-7/8'}, content=b'data')
    original = httpx.AsyncClient
    def factory(**kwargs):
        client = original(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client
    monkeypatch.setattr('backend.app.stream.proxy.httpx.AsyncClient', factory)
    request = httpx.Request('GET', 'http://localhost/stream', headers={'Range': 'bytes=4-7'})
    if status == 'timeout':
        with pytest.raises(httpx.ReadTimeout):
            await proxy_youtube_stream(request, 'abcdefghijk', SimpleNamespace(resolve=resolve))
    else:
        response = await proxy_youtube_stream(request, 'abcdefghijk', SimpleNamespace(resolve=resolve))
        assert response.status_code == status
        if status == 206:
            assert b''.join([chunk async for chunk in response.body_iterator]) == b'data'
        else:
            assert response.headers['content-range'] == 'bytes */4'
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize('failure,expected', [(False, 200), (True, 502)])
def test_search_failure_differs_from_no_results(monkeypatch, failure, expected):
    async def search(*args):
        if failure:
            raise RuntimeError('offline')
        return []
    async def miss(*args):
        return None
    monkeypatch.setattr('backend.app.main.cache.get', miss)
    monkeypatch.setattr('backend.app.main.ytdlp_search.search', search)
    monkeypatch.setattr('backend.app.main.browser_search.search', search)
    with TestClient(app) as client:
        assert client.get('/api/vdj/source/search?q=test').status_code == expected


def test_resolve_timeout_and_busy_are_actionable(monkeypatch):
    with TestClient(app) as client:
        for error, status in [(TimeoutError(), 504), (YtDlpBusyError('updating'), 503)]:
            async def fail(*args):
                raise error
            monkeypatch.setattr('backend.app.main.resolver.resolve', fail)
            assert client.get('/api/vdj/source/stream/abcdefghijk').status_code == status


async def test_diagnostics_cancellation_releases_lock():
    entered = asyncio.Event()
    async def version():
        entered.set()
        await asyncio.Event().wait()
    diagnostics = Diagnostics(None, None, None, SimpleNamespace(installed_version=version))
    task = asyncio.create_task(diagnostics.run())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not diagnostics.running


def test_diagnostics_requires_local_token(monkeypatch):
    async def run():
        return {'ok': True, 'checks': []}
    monkeypatch.setattr('backend.app.main.diagnostics.run', run)
    with TestClient(app) as client:
        assert client.post('/api/diagnostics').status_code == 403
        assert client.post('/api/diagnostics', headers={'X-Shutdown-Token': shutdown_token}).json()['ok']
    with TestClient(app, client=('203.0.113.1', 1234)) as client:
        assert client.post('/api/diagnostics', headers={'X-Shutdown-Token': shutdown_token}).status_code == 403


def test_chromium_rejects_stale_revision(tmp_path, monkeypatch):
    manifest = tmp_path / 'driver/package/browsers.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'browsers': [{'name': 'chromium', 'revision': '123'}]}))
    monkeypatch.setattr('backend.app.browser_tools.files', lambda _: tmp_path)
    monkeypatch.setattr('backend.app.browser_tools.sys', SimpleNamespace(platform='win32'))
    old = tmp_path / 'chromium-122/chrome-win64/chrome.exe'
    old.parent.mkdir(parents=True)
    old.touch()
    assert chromium_executable(tmp_path) is None
    current = tmp_path / 'chromium-123/chrome-win64/chrome.exe'
    current.parent.mkdir(parents=True)
    current.touch()
    assert chromium_executable(tmp_path) == current


async def test_disconnect_before_first_body_chunk_closes_upstream():
    closed = False
    async def cleanup():
        nonlocal closed
        closed = True
    async def body():
        pytest.fail('body must not start')
        yield b''
    async def send(message):
        raise OSError('client disconnected')
    response = ManagedStreamResponse(body(), cleanup=cleanup)
    with pytest.raises(Exception):
        await response({'type': 'http', 'asgi': {'spec_version': '2.4'}}, None, send)
    assert closed


async def test_cancelled_resolver_waiter_does_not_leak_lock(monkeypatch):
    resolver = YtDlpResolver(Path('unused'))
    entered = asyncio.Event()
    async def run(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(resolver.runner, 'run', run)
    first = asyncio.create_task(resolver.resolve('abcdefghijk'))
    await entered.wait()
    second = asyncio.create_task(resolver.resolve('abcdefghijk'))
    await asyncio.sleep(0)
    second.cancel()
    first.cancel()
    await asyncio.gather(first, second, return_exceptions=True)
    assert not resolver._locks
