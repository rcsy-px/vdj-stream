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


def test_last_search_survives_folder_changes_and_restart(library):
    assert library.tracks('last-search') == []
    items = [SimpleNamespace(videoId=key, title=key, channelName='Artist', durationSeconds=12, thumbnailUrl='cover') for key in [TRACK, '12345678901']]
    library.remember_search('my query', items)
    library.tracks('downloads')
    library.tracks('history')
    other = Library(library.root, None, library.ffmpeg)
    other.initialize()
    assert [t['id'] for t in other.tracks('last-search')] == [TRACK, '12345678901']
    assert 'last-search' in dict(other.folders())
    assert TRACK in other.tsv('last-search')
    other.remember_search('no matches', [])
    assert other.tracks('last-search') == []


def test_playback_preference_persists_and_only_changes_search(library):
    library.remember_search('query', [SimpleNamespace(videoId=TRACK, title='Title', channelName='', durationSeconds=12, thumbnailUrl='')])
    library.add(TRACK)
    assert library.playback_mode() == 'audio'
    library.set_playback_mode('video')
    other = Library(library.root, None, library.ffmpeg)
    other.initialize()
    assert other.state()['playbackMode'] == 'video'
    assert other.tsv('last-search').startswith('video:' + TRACK + '\t')
    assert other.tsv('last-search').endswith('\t1')
    assert other.tracks('set-default')[0]['id'] == TRACK
    other.set_playback_mode('audio')
    assert other.tsv('last-search').startswith(TRACK + '\t')
    assert other.tsv('last-search').endswith('\t0')


def test_playback_setting_requires_token_and_valid_mode(library):
    app = FastAPI()
    app.include_router(routes(library, 'secret'))
    with TestClient(app) as client:
        assert client.post('/api/library/playback', json={'mode': 'video'}).status_code == 403
        headers = {'X-Shutdown-Token': 'secret'}
        assert client.post('/api/library/playback', headers=headers, json={'mode': 'invalid'}).status_code == 422
        assert library.playback_mode() == 'audio'
        assert client.post('/api/library/playback', headers=headers, json={'mode': 'video'}).status_code == 200
        assert client.get('/api/library').json()['playbackMode'] == 'video'


async def test_video_load_waits_for_shared_download_and_reuses_file(library, monkeypatch):
    track = 'video:' + TRACK
    release = asyncio.Event()
    calls = []
    async def download(key):
        calls.append(key)
        await release.wait()
        (library.root / 'media/video.mp4').write_bytes(b'fixture')
        with library.db() as db:
            db.execute("UPDATE downloads SET state='ready',filename='video.mp4' WHERE track=?", (key,))
        library.tasks.pop(key, None)
    monkeypatch.setattr(library, '_download', download)
    with pytest.raises(TimeoutError):
        await library.prepare_video(track, timeout=0.01)
    assert not library.tasks[track].done()
    waiting = asyncio.create_task(library.prepare_video(track))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert not library.tasks[track].cancelled()
    release.set()
    path = await library.prepare_video(track)
    assert path.read_bytes() == b'fixture'
    assert await library.prepare_video(track) == path
    assert calls == [track]


async def test_failed_video_preparation_does_not_return_audio(library, monkeypatch):
    async def fail(track):
        library.mark(track, 'failed', 'fixture failure')
        library.tasks.pop(track, None)
    monkeypatch.setattr(library, '_download', fail)
    with pytest.raises(RuntimeError, match='preparation failed'):
        await library.prepare_video('video:' + TRACK)


async def test_native_search_and_video_stream_use_preference(library, monkeypatch):
    from backend.app import main
    monkeypatch.setattr(main, 'library', library)
    async def search(*args):
        return SimpleNamespace(error=None, results=[SimpleNamespace(videoId=TRACK, title='Title', channelName='Artist', durationSeconds=12, thumbnailUrl='')])
    monkeypatch.setattr(main, 'search', search)
    library.set_playback_mode('video')
    result = await main.vdj_source_search('test', 25)
    assert result.body.decode().split('\t')[0] == 'video:' + TRACK
    assert result.body.decode().endswith('\t1')
    async def prepare(track):
        assert track == 'video:' + TRACK
        return library.root / 'media/video.mp4'
    monkeypatch.setattr(library, 'prepare_video', prepare)
    result = await main.vdj_source_stream('video:' + TRACK)
    assert '/stream/library/video%3A' + TRACK + '/video.mp4' in result.body.decode()
    async def pending(track):
        raise TimeoutError('Still downloading')
    monkeypatch.setattr(library, 'prepare_video', pending)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await main.vdj_source_stream('video:' + TRACK)
    assert error.value.status_code == 409


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


async def test_low_disk_space_does_not_start_network_download(library, monkeypatch):
    monkeypatch.setattr('backend.app.library.shutil.disk_usage', lambda _: SimpleNamespace(free=1024**3))
    library.enqueue(TRACK)
    await asyncio.gather(*library.tasks.values())
    job = library.state()['downloads'][0]
    assert job['state'] == 'failed' and 'free disk space' in job['error']


async def test_disk_reserve_cancels_active_download(library, monkeypatch):
    cancelled = asyncio.Event()
    class Runner:
        async def run(self, *args, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
    library.runner = Runner()
    monkeypatch.setattr('backend.app.library.shutil.disk_usage', lambda _: SimpleNamespace(free=1024**3))
    with pytest.raises(ValueError, match='free disk space'):
        await library.run_download('fixture')
    assert cancelled.is_set()


def test_storage_and_authenticated_folder_open(library, monkeypatch):
    file = library.root / 'media/saved.m4a'
    file.write_bytes(b'1234567890')
    assert library.state()['usedBytes'] == 10
    assert library.state()['quotaBytes'] is None
    assert library.state()['freeBytes'] > 0
    opened = []
    monkeypatch.setattr(library, 'open_download_folder', lambda: opened.append(True))
    app = FastAPI()
    app.include_router(routes(library, 'secret'))
    with TestClient(app) as client:
        assert client.post('/api/library/open-download-folder').status_code == 403
        assert not opened
        assert client.post('/api/library/open-download-folder', headers={'X-Shutdown-Token': 'secret'}).status_code == 200
        assert opened == [True]


@pytest.mark.parametrize('video,streams,expected', [(False, ['audio'], 'ready'), (True, ['audio','video'], 'ready'), (True, ['video'], 'failed')])
async def test_download_validates_streams_before_exposing_media(library, monkeypatch, video, streams, expected):
    library.set_filename_mode('title')
    class Runner:
        async def run(self, *args, **kwargs):
            assert '--max-filesize' not in args
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
    if expected == 'ready':
        assert library.media(key).name == library.download_filename(key, '.mp4' if video else '.m4a')
    assert not list((library.root / 'staging').iterdir())


@pytest.mark.parametrize('video', [False, True])
@pytest.mark.parametrize('record', ['missing', 'interrupted', 'stale'])
@pytest.mark.parametrize('mode', ['id', 'title'])
async def test_saved_media_recovered_without_downloader(library, monkeypatch, video, record, mode):
    key = 'video:' + TRACK if video else TRACK
    library.set_filename_mode(mode)
    file = library.root / 'media' / library.download_filename(key, '.mp4' if video else '.m4a')
    file.write_bytes(b'complete fixture')
    if record != 'missing':
        with library.db() as db:
            db.execute('INSERT INTO downloads(track,state,filename) VALUES (?,?,?)',
                       (key, 'ready' if record == 'stale' else record, 'missing.mp4' if record == 'stale' else file.name))
    checked = []
    async def validate(path, is_video):
        checked.append((path, is_video))
    monkeypatch.setattr(library, 'validate_media', validate)
    # Reuse must also work below the free-space threshold, without a runner.
    monkeypatch.setattr('backend.app.library.shutil.disk_usage', lambda _: SimpleNamespace(free=1024))
    if video:
        first, second = await asyncio.gather(library.prepare_video(key), library.prepare_video(key))
        assert first == second == file
    else:
        library.enqueue(key)
        await asyncio.gather(*library.tasks.values())
    assert library.media(key) == file
    assert checked == [(file, video)]
    assert library.state()['downloads'][0]['size'] == file.stat().st_size
    library.initialize()
    assert await library.recover_media(key) == file
    assert len(checked) == 1


async def test_recovery_checks_only_matching_final_files_and_rejects_corruption(library, monkeypatch):
    folder = library.root / 'media'
    valid_name = f'video-{TRACK}.mp4'
    for name in [valid_name, f'audio-{TRACK}.m4a', f'video-{TRACK}.mp4.part', 'video-12345678901.mp4']:
        (folder / name).write_bytes(b'corrupt')
    (library.root / 'staging' / valid_name).write_bytes(b'partial')
    checked = []
    async def validate(path, video):
        checked.append(path.name)
        raise ValueError('Invalid media')
    monkeypatch.setattr(library, 'validate_media', validate)
    assert await library.recover_media('video:' + TRACK) is None
    assert checked == [valid_name]
    assert library.media('video:' + TRACK) is None


async def test_saved_audio_recovery_prevents_online_resolution(library, monkeypatch):
    from backend.app import main
    monkeypatch.setattr(main, 'library', library)
    file = library.root / 'media' / f'audio-{TRACK}.m4a'
    file.write_bytes(b'fixture')
    async def validate(*args):
        pass
    async def resolve(*args):
        pytest.fail('Saved audio must not contact YouTube')
    monkeypatch.setattr(library, 'validate_media', validate)
    monkeypatch.setattr(main, 'resolve_video', resolve)
    response = await main.vdj_source_stream(TRACK)
    assert '/stream/library/' in response.body.decode()
    assert library.media(TRACK) == file


async def test_delete_removes_alternate_names_without_touching_other_tracks(library):
    folder = library.root / 'media'
    for name in [f'video-{TRACK}.mp4', f'video-Title [{TRACK}].mp4', f'audio-{TRACK}.m4a', 'unrelated.mp4']:
        (folder / name).write_bytes(b'fixture')
    await library.delete('video:' + TRACK)
    assert sorted(p.name for p in folder.iterdir()) == [f'audio-{TRACK}.m4a', 'unrelated.mp4']
    assert await library.recover_media('video:' + TRACK) is None


async def test_local_recovery_and_removal_do_not_wait_for_unrelated_download(library, monkeypatch):
    file = library.root / 'media' / f'audio-{TRACK}.m4a'
    file.write_bytes(b'fixture')
    async def validate(*args):
        pass
    monkeypatch.setattr(library, 'validate_media', validate)
    async with library.semaphore:
        assert await asyncio.wait_for(library.recover_media(TRACK), .5) == file
        await asyncio.wait_for(library.delete(TRACK), .5)
    assert not file.exists()
    assert not library.media_locks


def test_filename_preference_is_authenticated_validated_and_persistent(library):
    app = FastAPI()
    app.include_router(routes(library, 'secret'))
    with TestClient(app) as client:
        assert client.post('/api/library/filenames', json={'mode': 'title'}).status_code == 403
        headers = {'X-Shutdown-Token': 'secret'}
        assert client.post('/api/library/filenames', headers=headers, json={'mode': '../unsafe'}).status_code == 422
        assert library.filename_mode() == 'id'
        assert client.post('/api/library/filenames', headers=headers, json={'mode': 'title'}).status_code == 200
        assert client.get('/api/library').json()['filenameMode'] == 'title'
    library.initialize()
    assert library.filename_mode() == 'title'


@pytest.mark.parametrize('title', ['../CON: <title>?*|"\\\x00', '😀á' * 200, '', '...', 'Same title'])
def test_title_filenames_are_safe_bounded_unique_and_keep_id(library, title):
    library.set_filename_mode('title')
    other = '12345678901'
    with library.db() as db:
        for key in [TRACK, other]:
            db.execute('INSERT OR REPLACE INTO tracks(id,title) VALUES (?,?)', (key, title))
    name = library.download_filename(TRACK, '.m4a')
    assert len(name.encode('utf-8')) < 140
    assert not any(c in name for c in '<>:"/\\|?*\x00')
    assert TRACK in name
    assert name != library.download_filename(other, '.m4a')
    assert name != library.download_filename('video:' + TRACK, '.m4a')
