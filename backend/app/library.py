"""Private media library, explicit setlists and read-only VirtualDJ history import."""
import asyncio
from contextlib import contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import unquote

log = logging.getLogger(__name__)
ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS tracks(id TEXT PRIMARY KEY, title TEXT, artist TEXT, duration INTEGER, cover TEXT);
CREATE TABLE IF NOT EXISTS lists(id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entries(list_id TEXT, track TEXT, added REAL, PRIMARY KEY(list_id,track));
CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS downloads(track TEXT PRIMARY KEY, state TEXT, error TEXT, filename TEXT, size INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS history(event TEXT PRIMARY KEY, track TEXT, day TEXT, position INTEGER);
'''


def track_parts(track):
    video = track.startswith('video:')
    video_id = track[6:] if video else track
    if not ID.fullmatch(video_id):
        raise ValueError('Invalid track ID')
    return video_id, video


def clean(value):
    return str(value or '').replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')


def vdj_home():
    if os.environ.get('VDJ_HOME'):
        return Path(os.environ['VDJ_HOME'])
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\VirtualDJ') as key:
                return Path(winreg.QueryValueEx(key, 'HomeFolder')[0])
        except OSError:
            pass
    candidates = [Path.home() / 'Library/Application Support/VirtualDJ',
                  Path.home() / 'AppData/Local/VirtualDJ', Path.home() / 'Documents/VirtualDJ']
    return next((p for p in candidates if p.is_dir()), None)


class Library:
    def __init__(self, root, runner, ffmpeg, history_home=None):
        self.root, self.runner, self.ffmpeg = Path(root), runner, Path(ffmpeg)
        self.history_home = history_home
        self.tasks = {}
        self.semaphore = asyncio.Semaphore(1)
        self.poller = None
        self.history_seen = {}

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.root / 'library.sqlite3', timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'media').mkdir(exist_ok=True)
        with self.db() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO lists VALUES ('default','My setlist')")
            db.execute("INSERT OR IGNORE INTO config VALUES ('active','default')")
            db.execute("UPDATE downloads SET state='interrupted', error='Interrupted by shutdown; retry the download.' WHERE state IN ('queued','downloading')")
        # Only our disposable staging directory, never saved media or user folders.
        stage = self.root / 'staging'
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()

    async def start(self):
        self.initialize()
        async def poll():
            while True:
                try:
                    await asyncio.to_thread(self.import_history)
                except Exception:
                    log.exception('History import failed')
                await asyncio.sleep(30)
        self.poller = asyncio.create_task(poll())

    async def close(self):
        tasks = list(self.tasks.values()) + ([self.poller] if self.poller else [])
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def remember(self, items):
        with self.db() as db:
            db.executemany('INSERT OR REPLACE INTO tracks VALUES (?,?,?,?,?)', [
                (t.videoId, t.title, t.channelName or '', t.durationSeconds or 0, t.thumbnailUrl or '') for t in items])

    def remember_search(self, query, items):
        self.remember(items)
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO config VALUES (?,?)', ('last_search', json.dumps([t.videoId for t in items])))
            db.execute('INSERT OR REPLACE INTO config VALUES (?,?)', ('last_query', clean(query)))

    def active(self):
        with self.db() as db:
            return db.execute("SELECT value FROM config WHERE key='active'").fetchone()[0]

    def create_list(self, name):
        name = clean(name).strip()
        if not name or len(name) > 80:
            raise ValueError('Setlist name must contain 1–80 characters.')
        key = uuid.uuid4().hex
        with self.db() as db:
            if db.execute('SELECT COUNT(*) FROM lists').fetchone()[0] >= 100:
                raise ValueError('Maximum 100 setlists.')
            db.execute('INSERT INTO lists VALUES (?,?)', (key, name))
            db.execute("UPDATE config SET value=? WHERE key='active'", (key,))
        return key

    def activate(self, key):
        with self.db() as db:
            if not db.execute('SELECT 1 FROM lists WHERE id=?', (key,)).fetchone():
                raise ValueError('Setlist not found.')
            db.execute("UPDATE config SET value=? WHERE key='active'", (key,))

    def delete_list(self, key):
        if key == 'default':
            raise ValueError('The default setlist cannot be deleted.')
        with self.db() as db:
            db.execute('DELETE FROM entries WHERE list_id=?', (key,))
            db.execute('DELETE FROM lists WHERE id=?', (key,))
            db.execute("UPDATE config SET value='default' WHERE key='active' AND value=?", (key,))

    def add(self, track):
        track_parts(track)
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO entries VALUES (?,?,?)', (self.active(), track, time.time()))

    def remove(self, track):
        track_parts(track)
        with self.db() as db:
            db.execute('DELETE FROM entries WHERE list_id=? AND track=?', (self.active(), track))

    def folders(self):
        with self.db() as db:
            lists = db.execute('SELECT * FROM lists ORDER BY name').fetchall()
        return [('last-search', 'Last search'), ('downloads', 'Downloaded audio'), ('videos', 'Downloaded videos'), ('history', 'Played in VirtualDJ')] + [
            ('set-' + row['id'], 'Setlist: ' + row['name']) for row in lists]

    def tracks(self, folder):
        with self.db() as db:
            if folder == 'last-search':
                saved = db.execute("SELECT value FROM config WHERE key='last_search'").fetchone()
                keys = json.loads(saved[0]) if saved else []
            elif folder in ('downloads', 'videos'):
                keys = [r[0] for r in db.execute("SELECT track FROM downloads WHERE state='ready' ORDER BY rowid DESC")
                        if r[0].startswith('video:') == (folder == 'videos') and self.media(r[0])]
            elif folder == 'history':
                keys = [r[0] for r in db.execute('SELECT track FROM history GROUP BY track ORDER BY MAX(day) DESC, MAX(position) DESC LIMIT 1000')]
            elif folder.startswith('set-'):
                keys = [r[0] for r in db.execute('SELECT track FROM entries WHERE list_id=? ORDER BY added', (folder[4:],))]
            else:
                raise ValueError('Unknown library folder.')
            result = []
            for track in keys:
                video_id, video = track_parts(track)
                row = db.execute('SELECT * FROM tracks WHERE id=?', (video_id,)).fetchone()
                result.append({'id': track, 'title': row['title'] if row else video_id,
                    'artist': row['artist'] if row else '', 'duration': row['duration'] if row else 0,
                    'cover': row['cover'] if row else '', 'video': video})
        return result

    def tsv(self, folder):
        return '\n'.join('\t'.join(clean(x) for x in (t['id'], t['title'], t['artist'], t['duration'], t['cover'], int(t['video']))) for t in self.tracks(folder))

    def export(self, key):
        rows = ['#EXTM3U']
        for item in self.tracks('set-' + key):
            rows += [f"#EXTINF:{item['duration']},{clean(item['artist'])} - {clean(item['title'])}",
                     'netsearch://plugin-VDJ Companion Source/' + item['id']]
        return '\n'.join(rows) + '\n'

    def import_history(self):
        home = self.history_home if self.history_home is not None else vdj_home()
        if not home:
            return 0
        files = sorted((Path(home) / 'History').glob('*.m3u*'), reverse=True)[:60]
        count = 0
        updated = {}
        with self.db() as db:
            for path in files:
                stamp = (path.stat().st_mtime_ns, path.stat().st_size)
                if stamp[1] > 4 * 1024**2 or self.history_seen.get(path) == stamp:
                    continue
                title, artist, duration = '', '', 0
                for position, line in enumerate(path.read_text(encoding='utf-8-sig', errors='replace').splitlines()):
                    if line.startswith('#EXTINF:'):
                        title = line.partition(',')[2]
                    if line.startswith('#EXTVDJ:'):
                        try:
                            metadata = ET.fromstring('<track>' + line[8:] + '</track>')
                            title = metadata.findtext('title') or ''
                            artist = metadata.findtext('artist') or ''
                            duration = max(0, int(float(metadata.findtext('songlength') or '0')))
                        except (ET.ParseError, ValueError, OverflowError):
                            title, artist, duration = '', '', 0
                    prefix = 'netsearch://plugin-VDJ Companion Source/'
                    line = unquote(line.strip())
                    if not line.startswith(prefix):
                        if line and not line.startswith('#'):
                            title, artist, duration = '', '', 0
                        continue
                    track = line[len(prefix):]
                    try:
                        video_id, _ = track_parts(track)
                    except ValueError:
                        continue
                    event = hashlib.sha256(f'{path.name}:{position}:{track}'.encode()).hexdigest()
                    db.execute('INSERT OR IGNORE INTO tracks VALUES (?,?,?,?,?)', (video_id, title or video_id, artist, duration, ''))
                    if title:
                        db.execute('UPDATE tracks SET title=?,artist=?,duration=? WHERE id=? AND title=?', (title, artist, duration, video_id, video_id))
                    count += db.execute('INSERT OR IGNORE INTO history VALUES (?,?,?,?)', (event, track, path.stem, position)).rowcount
                    title, artist, duration = '', '', 0
                updated[path] = stamp
        self.history_seen.update(updated)
        return count

    def media(self, track):
        track_parts(track)
        with self.db() as db:
            row = db.execute("SELECT filename FROM downloads WHERE track=? AND state='ready'", (track,)).fetchone()
        if not row or not row[0]:
            return None
        path = (self.root / 'media' / row[0]).resolve()
        return path if path.parent == (self.root / 'media').resolve() and path.is_file() else None

    def state(self):
        with self.db() as db:
            lists = [dict(r) for r in db.execute('SELECT * FROM lists ORDER BY name')]
            jobs = [dict(r) for r in db.execute('SELECT * FROM downloads ORDER BY rowid DESC')]
            for job in jobs:
                row = db.execute('SELECT title FROM tracks WHERE id=?', (track_parts(job['track'])[0],)).fetchone()
                job['title'] = row[0] if row else job['track']
                if job['state'] == 'ready' and not self.media(job['track']):
                    job['state'] = 'missing'
        return {'lists': lists, 'active': self.active(), 'downloads': jobs,
                'usedBytes': sum(p.stat().st_size for p in (self.root / 'media').iterdir() if p.is_file()),
                'quotaBytes': None, 'freeBytes': shutil.disk_usage(self.root).free,
                'history': self.tracks('history')}

    def open_download_folder(self):
        folder = (self.root / 'media').resolve()
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(str(folder))
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(folder)], check=True, timeout=10, capture_output=True)
        else:
            raise RuntimeError('Opening the download folder is supported on Windows and macOS.')

    async def run_download(self, *args):
        task = asyncio.create_task(self.runner.run(*args, timeout=900))
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=1)
                if shutil.disk_usage(self.root).free < 2 * 1024**3:
                    raise ValueError('Download stopped: less than 2 GB of free disk space remains.')
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def enqueue(self, track):
        track_parts(track)
        if self.media(track) or track in self.tasks:
            return
        if len(self.tasks) >= 20:
            raise ValueError('Download queue is full (20 tracks).')
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO downloads(track,state,error) VALUES (?,'queued','')", (track,))
        self.tasks[track] = asyncio.create_task(self._download(track))

    def mark(self, track, state, error=''):
        with self.db() as db:
            db.execute('UPDATE downloads SET state=?,error=? WHERE track=?', (state, error, track))

    async def _download(self, track):
        video_id, video = track_parts(track)
        stage = self.root / 'staging' / uuid.uuid4().hex
        try:
            async with self.semaphore:
                if shutil.disk_usage(self.root).free < 2 * 1024**3:
                    raise ValueError('At least 2 GB of free disk space is required.')
                stage.mkdir()
                self.mark(track, 'downloading')
                fmt = ('bestvideo[height<=720][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[height<=720][ext=mp4][vcodec^=avc1]'
                       if video else 'bestaudio[ext=m4a]/bestaudio')
                args = ['--no-playlist', '--no-progress', '--no-warnings',
                        '--socket-timeout', '20', '--retries', '2', '--fragment-retries', '2',
                        '--ffmpeg-location', str(self.ffmpeg), '-f', fmt,
                        '-o', str(stage / 'media.%(ext)s'), '--print', 'after_move:%(filepath)s',
                        '--no-simulate']
                if video:
                    args += ['--merge-output-format', 'mp4']
                await self.run_download(*args, f'https://www.youtube.com/watch?v={video_id}')
                files = [p for p in stage.glob('media.*') if p.suffix in ('.mp4', '.m4a', '.webm', '.opus', '.ogg')]
                if len(files) != 1 or files[0].stat().st_size <= 0:
                    raise ValueError('Download did not produce a complete supported file.')
                source = files[0]
                # Verify tracks, not merely extension: a partial/video-only file is not playable.
                executable = self.ffmpeg / ('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
                probe = await asyncio.create_subprocess_exec(str(executable), '-v', 'error', '-show_streams', '-of', 'json', str(source), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                try:
                    output, _ = await asyncio.wait_for(probe.communicate(), 30)
                except BaseException:
                    if probe.returncode is None:
                        probe.kill()
                    await probe.communicate()
                    raise
                types = {s.get('codec_type') for s in json.loads(output).get('streams', [])} if probe.returncode == 0 else set()
                if 'audio' not in types or (video and 'video' not in types):
                    raise ValueError('Downloaded file is missing its audio or video stream.')
                filename = ('video-' if video else 'audio-') + video_id + source.suffix
                target = self.root / 'media' / filename
                source.replace(target)
                with self.db() as db:
                    db.execute("UPDATE downloads SET state='ready',filename=?,size=?,error='' WHERE track=?", (filename, target.stat().st_size, track))
        except asyncio.CancelledError:
            self.mark(track, 'cancelled', 'Download cancelled; retry when ready.')
            raise
        except Exception as exc:
            log.warning('Download failed for %s: %s', track, exc)
            self.mark(track, 'failed', str(exc)[:300])
        finally:
            if stage.exists():
                shutil.rmtree(stage)
            self.tasks.pop(track, None)

    async def cancel(self, track):
        track_parts(track)
        task = self.tasks.get(track)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.tasks.pop(track, None)
            self.mark(track, 'cancelled')

    async def delete(self, track):
        await self.cancel(track)
        path = self.media(track)
        if path:
            path.unlink()
        with self.db() as db:
            db.execute('DELETE FROM downloads WHERE track=?', (track,))
