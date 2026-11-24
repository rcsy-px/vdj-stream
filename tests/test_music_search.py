import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.library import Library
from backend.app.library_api import routes
from backend.app.db.database import QueryCache
from backend.app.search.youtube_music import YouTubeMusicSearchProvider


def item(key='abcdefghijk', kind='song'):
    return {'videoId': key, 'title': 'Árvíz & Song', 'resultType': kind,
            'artists': [{'name': 'Artist One'}, {'name': 'Artist Two'}],
            'duration': '4:06', 'duration_seconds': 246,
            'thumbnails': [{'url': 'https://example.org/cover.jpg'}]}


@pytest.fixture
def library(tmp_path):
    lib = Library(tmp_path / 'library', None, tmp_path)
    lib.initialize()
    return lib


@pytest.mark.parametrize('source', ['youtube', 'music_songs', 'music_videos'])
def test_search_source_is_protected_and_survives_restart(library, source):
    app = FastAPI()
    app.include_router(routes(library, 'secret'))
    with TestClient(app) as client:
        endpoint = '/api/library/search-source'
        assert client.post(endpoint, json={'source': source}).status_code == 403
        headers = {'X-Shutdown-Token': 'secret'}
        assert client.post(endpoint, headers=headers, json={'source': 'untrusted'}).status_code == 422
        assert library.search_source() == 'youtube'
        assert client.post(endpoint, headers=headers, json={'source': source}).status_code == 200
        assert client.get('/api/library').json()['searchSource'] == source
    restarted = Library(library.root, None, library.ffmpeg)
    restarted.initialize()
    assert restarted.search_source() == source


@pytest.mark.parametrize('category,kind', [('songs', 'song'), ('videos', 'video')])
def test_music_metadata_mapping_filters_invalid_unavailable_duplicates(category, kind):
    provider = YouTubeMusicSearchProvider(category)
    data = [item(kind=kind), item(kind=kind), item('../bad', kind),
            {**item('12345678901', kind), 'isAvailable': False}, item('98765432109', 'album'),
            {**item('ABCDEFGHIJK', kind), 'duration_seconds': None, 'thumbnails': []}]
    tracks = provider.parse(data, 25)
    assert len(tracks) == 2
    assert tracks[0].title == 'Árvíz & Song'
    assert tracks[0].channelName == 'Artist One, Artist Two'
    assert tracks[0].durationSeconds == 246
    assert tracks[0].thumbnailUrl == 'https://example.org/cover.jpg'
    assert tracks[1].durationSeconds == 246
    assert tracks[1].thumbnailUrl.endswith('/ABCDEFGHIJK/hqdefault.jpg')
    assert len(provider.parse(data, 1)) == 1


async def test_search_sources_have_separate_cache_and_native_metadata(library, tmp_path, monkeypatch):
    from backend.app import main
    monkeypatch.setattr(main, 'library', library)
    cache = QueryCache(tmp_path / 'cache.db', Path('backend/app/db/schema.sql'))
    await cache.initialize()
    monkeypatch.setattr(main, 'cache', cache)
    calls = []
    def search_for(source, key):
        async def search(query, limit):
            calls.append(source)
            return YouTubeMusicSearchProvider('songs').parse([item(key)], limit)
        return search
    monkeypatch.setattr(main.ytdlp_search, 'search', search_for('youtube', 'abcdefghijk'))
    monkeypatch.setattr(main.music_search['music_songs'], 'search', search_for('music_songs', 'ABCDEFGHIJK'))
    monkeypatch.setattr(main.music_search['music_videos'], 'search', search_for('music_videos', '12345678901'))
    for source, expected in [('youtube', 'abcdefghijk'), ('music_songs', 'ABCDEFGHIJK'), ('music_videos', '12345678901')]:
        library.set_search_source(source)
        assert (await main.search('same query', 1)).results[0].videoId == expected
        response = await main.vdj_source_search('same query', 1)
        columns = response.body.decode().split('\t')
        assert columns[:4] == [expected, 'Árvíz & Song', 'Artist One, Artist Two', '246']
        assert columns[4] == 'https://example.org/cover.jpg'
    assert calls == ['youtube', 'music_songs', 'music_videos']
    library.set_search_source('youtube')
    assert (await main.search('same query', 1)).cached
    assert len(calls) == 3


@pytest.mark.parametrize('failure', [False, True])
async def test_music_empty_or_failure_never_silently_switches_to_youtube(library, monkeypatch, failure):
    from backend.app import main
    monkeypatch.setattr(main, 'library', library)
    library.set_search_source('music_songs')
    async def miss(*args):
        return None
    async def music(*args):
        if failure:
            raise RuntimeError('Music unavailable')
        return []
    async def forbidden(*args):
        pytest.fail('Music search must not silently return normal YouTube results')
    monkeypatch.setattr(main.cache, 'get', miss)
    monkeypatch.setattr(main.music_search['music_songs'], 'search', music)
    monkeypatch.setattr(main.ytdlp_search, 'search', forbidden)
    monkeypatch.setattr(main.browser_search, 'search', forbidden)
    response = await main.vdj_source_search('query', 5)
    assert response.status_code == (502 if failure else 200)


@pytest.mark.parametrize('cancel', [False, True])
async def test_music_worker_is_killed_and_reaped_on_timeout_or_cancel(monkeypatch, cancel):
    entered = asyncio.Event()
    class Process:
        returncode = None
        calls = 0
        def kill(self):
            self.returncode = -9
        async def communicate(self):
            self.calls += 1
            entered.set()
            if self.returncode is None:
                await asyncio.Event().wait()
            return b'', b''
    process = Process()
    async def spawn(*args, **kwargs):
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    provider = YouTubeMusicSearchProvider('songs', .05 if not cancel else 10)
    task = asyncio.create_task(provider.search('test', 1))
    await entered.wait()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
        await task
    assert process.returncode == -9 and process.calls == 2
    assert not provider.slots.locked()
