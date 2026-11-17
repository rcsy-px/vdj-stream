import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.library import Library, track_parts
from backend.app.library_api import routes

TRACK = 'abcdefghijk'


@pytest.fixture
def library(tmp_path):
    lib = Library(tmp_path / 'library', None, tmp_path / 'ffmpeg', history_home=tmp_path / 'vdj')
    lib.initialize()
    lib.remember([SimpleNamespace(videoId=TRACK, title='Árvíz <script>', channelName='Artist', durationSeconds=12, thumbnailUrl='')])
    return lib


def test_setlist_persists_ids_order_and_video_without_duplicates(library):
    key = library.create_list('Friday night')
    library.add(TRACK)
    library.add('video:' + TRACK)
    library.add(TRACK)
    other = Library(library.root, None, library.ffmpeg)
    other.initialize()
    assert other.active() == key
    assert [t['id'] for t in other.tracks('set-' + key)] == [TRACK, 'video:' + TRACK]
    exported = other.export(key)
    assert exported.count('netsearch://plugin-VDJ Companion Source/') == 2
    assert '\t1' in other.tsv('set-' + key)
    other.remove(TRACK)
    assert len(other.tracks('set-' + key)) == 1


def test_history_import_is_read_only_deduplicated_and_provider_specific(library):
    home = library.history_home / 'History'
    home.mkdir(parents=True)
    file = home / '2026-11-17.m3u'
    content = f'#EXTM3U\n#EXTINF:12,Artist - title\nnetsearch://plugin-VDJ Companion Source/{TRACK}\nnetsearch://plugin-Other/{TRACK}\nC:/Music/unrelated.mp3\n'
    file.write_text(content, encoding='utf-8')
    assert library.import_history() == 1
    assert library.import_history() == 0
    assert file.read_text(encoding='utf-8') == content
    assert [t['id'] for t in library.tracks('history')] == [TRACK]


def test_real_virtualdj_extvdj_metadata_is_imported(library):
    home = library.history_home / 'History'
    home.mkdir(parents=True)
    (home / '2026-11-17.m3u').write_text('#EXTVDJ:<time>19:46</time><artist>Artist</artist><title>A &amp; B</title><songlength>221.704</songlength>\nnetsearch://plugin-VDJ Companion Source/12345678901\n', encoding='utf-8')
    assert library.import_history() == 1
    track, = library.tracks('history')
    assert track['title'] == 'A & B' and track['artist'] == 'Artist' and track['duration'] == 221


@pytest.mark.parametrize('key', ['../anything', 'video:../abc', 'http://example.org', 'a'*12, ''])
def test_invalid_track_cannot_access_files(library, key):
    with pytest.raises(ValueError):
        library.media(key)


def test_recovery_marks_inflight_jobs_interrupted(library):
    with library.db() as db:
        db.execute("INSERT INTO downloads(track,state) VALUES (?,'downloading')", (TRACK,))
    staging = library.root / 'staging' / 'partial'
    staging.mkdir()
    (staging / 'media.part').write_bytes(b'partial')
    library.initialize()
    assert library.state()['downloads'][0]['state'] == 'interrupted'
    assert not staging.exists()


def test_mutations_require_control_token_and_native_token_rejects_browser(library):
    app = FastAPI()
    app.include_router(routes(library, 'secret'))
    with TestClient(app) as client:
        assert client.post(f'/api/library/tracks/{TRACK}/add').status_code == 403
        assert client.get('/api/library/native-token').status_code == 403
        headers = {'X-VDJ-Companion': '1', 'Origin': 'https://evil.test'}
        assert client.get('/api/library/native-token', headers=headers).status_code == 403
        assert client.get('/api/library/native-token', headers={'X-VDJ-Companion': '1'}).text == 'secret'
        assert client.post(f'/api/library/tracks/{TRACK}/add', headers={'X-Shutdown-Token': 'secret'}).status_code == 200
        assert len(library.tracks('set-default')) == 1


def test_offline_file_supports_head_ranges_and_survives_network_absence(library):
    path = library.root / 'media/test.m4a'
    path.write_bytes(b'0123456789')
    with library.db() as db:
        db.execute("INSERT INTO downloads(track,state,filename,size) VALUES (?,'ready','test.m4a',10)", (TRACK,))
    app = FastAPI()
    app.include_router(routes(library, 'secret'))
    with TestClient(app) as client:
        response = client.get(f'/stream/library/{TRACK}/whatever.m4a', headers={'Range': 'bytes=3-6'})
        assert response.status_code == 206 and response.content == b'3456'
        assert response.headers['content-range'] == 'bytes 3-6/10'
        assert client.head(f'/stream/library/{TRACK}/file.m4a').content == b''
        assert client.get(f'/stream/library/{TRACK}/file.m4a', headers={'Range': 'bytes=50-'}).status_code == 416


async def test_cancellation_leaves_no_partial_download_or_stuck_queue(library):
    entered = asyncio.Event()
    class Runner:
        async def run(self, *args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
    library.runner = Runner()
    library.enqueue(TRACK)
    await asyncio.wait_for(entered.wait(), 2)
    await library.cancel(TRACK)
    assert not library.tasks and not list((library.root / 'staging').iterdir())
    assert library.state()['downloads'][0]['state'] == 'cancelled'


async def test_quota_failure_does_not_start_network_download(library):
    library.quota_bytes = 100
    library.enqueue(TRACK)
    await asyncio.gather(*library.tasks.values())
    job = library.state()['downloads'][0]
    assert job['state'] == 'failed' and 'storage limit' in job['error']


@pytest.mark.parametrize('video,streams,expected', [(False, ['audio'], 'ready'), (True, ['audio','video'], 'ready'), (True, ['video'], 'failed')])
async def test_download_validates_streams_before_exposing_media(library, monkeypatch, video, streams, expected):
    class Runner:
        async def run(self, *args, **kwargs):
            output = Path(args[args.index('-o') + 1].replace('%(ext)s', 'mp4' if video else 'm4a'))
            output.write_bytes(b'valid fixture')
    class Probe:
        returncode = 0
        async def communicate(self):
            return json.dumps({'streams': [{'codec_type': kind} for kind in streams]}).encode(), b''
    async def spawn(*args, **kwargs):
        return Probe()
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    library.runner = Runner()
    key = 'video:' + TRACK if video else TRACK
    library.enqueue(key)
    await asyncio.gather(*library.tasks.values())
    assert library.state()['downloads'][0]['state'] == expected
    assert bool(library.media(key)) == (expected == 'ready')
    assert not list((library.root / 'staging').iterdir())
