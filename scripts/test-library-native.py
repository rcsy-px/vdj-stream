"""Run the Windows SDK host against a local fixture server; never start VirtualDJ."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import sys
import threading
from urllib.parse import unquote

actions = []
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def do_GET(self):
        assert self.headers.get('X-VDJ-Companion') == '1'
        path = unquote(self.path)
        responses = {
            '/api/vdj/source/folders': 'downloads\tDownloaded audio\nvideos\tDownloaded videos',
            '/api/vdj/source/folder/videos': 'video:abcdefghijk\tVideo\tArtist\t12\t\t1',
            '/api/vdj/source/stream/video:abcdefghijk': 'http://127.0.0.1:8765/stream/library/video:abcdefghijk/video.mp4',
            '/api/library/native-token': 'test-token',
        }
        self.send_response(200 if path in responses else 404)
        self.end_headers()
        self.wfile.write(responses.get(path, '').encode())
    def do_POST(self):
        assert self.headers.get('X-Shutdown-Token') == 'test-token'
        actions.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

if __name__ == '__main__':
    # Binding refuses to run if an existing Companion owns the port.
    with ThreadingHTTPServer(('127.0.0.1', 8765), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            subprocess.run(sys.argv[1:], check=True, timeout=30)
            assert actions == ['/api/library/tracks/abcdefghijk/add', '/api/library/tracks/abcdefghijk/video'], actions
        finally:
            server.shutdown()
    print('Native DLL: folder enumeration, video flag/URL, context menu and authenticated POST actions passed.')
