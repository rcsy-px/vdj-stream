"""Exercise real ZIP validation and atomic replacement with interrupted downloads."""
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows launcher')
def test_interrupted_download_is_retried_without_replacing_destination(tmp_path):
    helper = Path('scripts/download-tools.ps1').resolve()
    script = tmp_path / 'test.ps1'
    script.write_text(r'''
param($Helper, $Work)
. $Helper
$destination = Join-Path $Work 'tool.zip'
$valid = Join-Path $Work 'valid.zip'
$content = Join-Path $Work 'source'
New-Item -ItemType Directory $content | Out-Null
Set-Content (Join-Path $content 'payload.txt') 'complete payload'
Compress-Archive (Join-Path $content '*') $valid
Set-Content $destination 'old broken download'
$script:attempt = 0
function Invoke-ToolDownload {
    param($Uri, $OutFile)
    $script:attempt++
    if ((Get-Content $destination -Raw).Trim() -ne 'old broken download') { throw 'Destination replaced too early' }
    if ($script:attempt -eq 1) {
        Set-Content $OutFile 'partial'
        throw 'Interrupted network'
    }
    Copy-Item $valid $OutFile
}
Download-File 'https://example.invalid/tool.zip' $destination
if ($script:attempt -ne 2) { throw 'Retry did not run' }
if (-not (Test-ToolDownload $destination '.zip')) { throw 'Invalid final ZIP' }
if (Test-Path "$destination.part.zip") { throw 'Leaked partial file' }
Download-File 'https://example.invalid/tool.zip' $destination
if ($script:attempt -ne 2) { throw 'Valid cached file downloaded again' }
''', encoding='utf-8')
    result = subprocess.run([shutil.which('powershell'), '-NoProfile', '-ExecutionPolicy', 'Bypass',
                             '-File', str(script), str(helper), str(tmp_path)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows launcher')
def test_download_deadline_interrupts_stalled_response_body(tmp_path):
    release = threading.Event()
    class StalledBody(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', '10000')
            self.end_headers()
            self.wfile.write(b'x')
            self.wfile.flush()
            release.wait(15)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), StalledBody)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    script = tmp_path / 'deadline.ps1'
    script.write_text(r'''
param($Helper, $Destination, $Url)
. $Helper
try { Invoke-ToolDownload -Uri $Url -OutFile $Destination -TimeoutSeconds 1 }
catch {
    if ($_.Exception.Message -like '*curl exit 28*') { exit 0 }
    throw
}
throw 'Stalled download did not time out'
''', encoding='utf-8')
    try:
        result = subprocess.run([shutil.which('powershell'), '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(script), str(Path('scripts/download-tools.ps1').resolve()),
                                 str(tmp_path / 'partial.zip'), f'http://127.0.0.1:{server.server_port}/tool'],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
