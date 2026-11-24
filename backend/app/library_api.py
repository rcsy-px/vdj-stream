import asyncio
import subprocess
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from .library import track_parts, clean


class ListName(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PlaybackSettings(BaseModel):
    mode: Literal['audio', 'video']


class FilenameSettings(BaseModel):
    mode: Literal['id', 'title']


class SearchSettings(BaseModel):
    source: Literal['youtube', 'music_songs', 'music_videos']


def routes(library, token, app_busy=lambda: False):
    router = APIRouter()

    def authorize(request):
        if not request.client or request.client.host not in ('127.0.0.1', '::1', 'testclient') or request.headers.get('x-shutdown-token') != token:
            raise HTTPException(403, 'Use the local Companion panel or plugin.')
        if app_busy():
            raise HTTPException(409, 'Wait for the application update to finish.')

    @router.get('/api/library/native-token', response_class=PlainTextResponse)
    async def native_token(request: Request):
        if (not request.client or request.client.host not in ('127.0.0.1', '::1', 'testclient')
                or request.headers.get('x-vdj-companion') != '1'
                or request.headers.get('origin') or request.headers.get('sec-fetch-site')):
            raise HTTPException(403, 'Native plugin only.')
        return PlainTextResponse(token, headers={'Cache-Control': 'no-store'})

    @router.get('/api/library')
    async def state():
        return library.state()

    @router.post('/api/library/playback')
    async def playback(request: Request, body: PlaybackSettings):
        authorize(request)
        library.set_playback_mode(body.mode)
        return {'ok': True}

    @router.post('/api/library/open-download-folder')
    async def open_download_folder(request: Request):
        authorize(request)
        try:
            await asyncio.to_thread(library.open_download_folder)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise HTTPException(503, 'Could not open the download folder. Try again from the computer running Companion.') from exc
        return {'ok': True}

    @router.post('/api/library/filenames')
    async def filenames(request: Request, body: FilenameSettings):
        authorize(request)
        library.set_filename_mode(body.mode)
        return {'ok': True}

    @router.post('/api/library/search-source')
    async def search_source(request: Request, body: SearchSettings):
        authorize(request)
        library.set_search_source(body.source)
        return {'ok': True}

    @router.post('/api/library/setlists')
    async def create(request: Request, body: ListName):
        authorize(request)
        try:
            return {'id': library.create_list(body.name)}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @router.post('/api/library/setlists/{key}/activate')
    async def activate(key: str, request: Request):
        authorize(request)
        try:
            library.activate(key)
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        return {'ok': True}

    @router.get('/api/library/setlists/{key}/export')
    async def export(key: str):
        return PlainTextResponse(library.export(key), media_type='audio/x-mpegurl',
            headers={'Content-Disposition': 'attachment; filename="companion-setlist.m3u8"'})

    @router.post('/api/library/setlists/{key}/delete')
    async def delete_setlist(key: str, request: Request):
        authorize(request)
        try:
            library.delete_list(key)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return {'ok': True}

    @router.get('/api/library/folders/{folder}')
    async def folder(folder: str):
        try:
            return library.tracks(folder)
        except ValueError as exc:
            raise HTTPException(404, str(exc))

    @router.post('/api/library/history/refresh')
    async def history(request: Request):
        authorize(request)
        import asyncio
        return {'imported': await asyncio.to_thread(library.import_history)}

    @router.post('/api/library/tracks/{track}/{action}')
    async def action(track: str, action: str, request: Request):
        authorize(request)
        try:
            video_id, _ = track_parts(track)
            if action == 'audio':
                library.enqueue(video_id)
            elif action == 'video':
                library.enqueue('video:' + video_id)
            elif action == 'add':
                library.add(track)
            elif action == 'remove':
                library.remove(track)
            elif action == 'cancel':
                await library.cancel(video_id)
                await library.cancel('video:' + video_id)
            elif action == 'delete':
                await library.delete(track)
            else:
                raise ValueError('Unknown library action.')
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except OSError as exc:
            raise HTTPException(409, 'File is in use. Unload the track before removing its download.') from exc
        return {'ok': True}

    @router.get('/api/vdj/source/folders', response_class=PlainTextResponse)
    async def native_folders():
        return '\n'.join(key + '\t' + clean(name) for key, name in library.folders())

    @router.get('/api/vdj/source/folder/{folder}', response_class=PlainTextResponse)
    async def native_folder(folder: str):
        try:
            return library.tsv(folder)
        except ValueError as exc:
            raise HTTPException(404, str(exc))

    @router.api_route('/stream/library/{track}/{filename}', methods=['GET', 'HEAD'])
    async def media(track: str, filename: str):
        try:
            path = library.media(track)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        if not path:
            raise HTTPException(404, 'Saved media is not available. Download it again.')
        return FileResponse(path, filename=path.name, content_disposition_type='inline')

    return router
