"""Standalone Windows installer. Runs on portable base Python, never the replaced venv."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

MANAGED = ('backend', 'docs', 'scripts', 'plugin/online-source/prebuilt/x64',
           'START.bat', 'START-DEBUG.bat', 'STOP.bat', 'README.md', 'LICENSE', 'VERSION',
           'CHANGELOG.md', 'SECURITY.md', 'CONTRIBUTING.md', 'pyproject.toml', 'uv.lock', '.venv')
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value), encoding='utf-8')
    temporary.replace(path)


def remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


def plugin_target():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\VirtualDJ') as key:
            home = Path(winreg.QueryValueEx(key, 'HomeFolder')[0])
    except OSError:
        home = Path.home() / 'Documents/VirtualDJ'
    return home / 'Plugins64/OnlineSources/VDJ Companion Source.dll'


def check_virtualdj():
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq virtualdj.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, timeout=15, creationflags=FLAGS)
    if result.returncode or b'"virtualdj.exe"' in result.stdout.lower():
        raise RuntimeError('Close VirtualDJ before installing the update.')


def wait_for_parent(pid):
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # Process already exited.
            return
        raise RuntimeError('Could not safely wait for the backend to stop.')
    try:
        if kernel.WaitForSingleObject(handle, 60000) != 0:
            raise RuntimeError('Backend did not stop; no files were changed.')
    finally:
        kernel.CloseHandle(handle)


def environment(root):
    return {**os.environ, 'VDJ_WINDOWS_UPDATER': '1',
            'UV_CACHE_DIR': str(root / '.cache/uv'),
            'UV_PYTHON_INSTALL_DIR': str(root / 'tools/python'),
            'PLAYWRIGHT_BROWSERS_PATH': str(root / 'tools/playwright-browsers')}


def run(command, root, timeout=600):
    subprocess.run(command, cwd=root, env=environment(root), check=True, timeout=timeout, creationflags=FLAGS)


def install_dependencies(root):
    run([str(root / 'tools/uv/uv.exe'), 'sync', '--locked', '--python', sys.executable], root)
    run([str(root / '.venv/Scripts/python.exe'), '-m', 'playwright', 'install', 'chromium'], root)


def start_backend(root):
    logs = root / 'data/logs'
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / 'backend-stdout.log').open('ab') as out, (logs / 'backend-stderr.log').open('ab') as err:
        process = subprocess.Popen([str(root / '.venv/Scripts/python.exe'), '-m', 'uvicorn',
            'backend.app.main:app', '--host', '127.0.0.1', '--port', '8765', '--no-access-log'],
            cwd=root, env=environment(root), stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            creationflags=FLAGS, close_fds=True)
    return process


def healthy(process, version):
    for _ in range(60):
        if process.poll() is not None:
            break
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=2) as response:
                state = json.load(response)
            if state.get('ok') and state.get('version') == version:
                return
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    raise RuntimeError('Updated backend did not pass its startup health check.')


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        process.wait(timeout=20)


def rollback(plan, backup):
    for item in plan:
        target = Path(item['target'])
        remove(target)
        if item['existed']:
            copy(backup / str(item['index']), target)


def apply(root, job, request, recover=False):
    journal, backup = job / 'journal.json', job / 'backup'
    if recover:
        check_virtualdj()
        if journal.exists():
            state = json.loads(journal.read_text(encoding='utf-8'))
            if state['phase'] == 'complete':
                return {'ok': True, 'message': 'Companion was updated successfully.'}
            if state['phase'] == 'installing':
                rollback(state['plan'], backup)
                write_json(journal, {**state, 'phase': 'rolled-back'})
        return {'ok': False, 'message': 'Interrupted update recovered. The previous version is available.'}
    check_virtualdj()
    staged = job / 'staged'
    if (staged / 'VERSION').read_text(encoding='utf-8').strip() != request['version']:
        raise RuntimeError('Staged version changed.')
    target = plugin_target()
    targets = [root / name for name in MANAGED] + [target]
    plan = [{'index': i, 'target': str(p), 'existed': p.exists()} for i, p in enumerate(targets)]
    backup.mkdir()
    for item in plan:
        if item['existed']:
            copy(Path(item['target']), backup / str(item['index']))
    check_virtualdj()
    write_json(journal, {'phase': 'installing', 'plan': plan})
    process = None
    try:
        for name in MANAGED:
            remove(root / name)
            if (staged / name).exists():
                copy(staged / name, root / name)
        install_dependencies(root)
        check_virtualdj()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / 'plugin/online-source/prebuilt/x64/VDJ Companion Source.dll', target)
        process = start_backend(root)
        healthy(process, request['version'])
        write_json(journal, {'phase': 'complete', 'plan': plan})
        return {'ok': True, 'message': 'Companion was updated successfully.'}
    except BaseException:
        stop(process)
        rollback(plan, backup)
        write_json(journal, {'phase': 'rolled-back', 'plan': plan})
        raise


def main():
    import msvcrt
    root = Path(sys.argv[1]).resolve()
    marker = root / 'data/windows-update-active.json'
    if not marker.exists():
        return
    request = json.loads(marker.read_text(encoding='utf-8'))
    job = (root / '.cache' / request['job']).resolve()
    if job.parent != (root / '.cache').resolve() or not job.name.startswith('app-update-'):
        raise RuntimeError('Invalid update job path.')
    with (job / 'install.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SystemExit('Update is still running. Wait before starting Companion.')
        recover = '--recover' in sys.argv
        if not recover:
            wait_for_parent(request['parent'])
        try:
            result = apply(root, job, request, recover)
        except Exception as exc:
            print(f'Update failed: {exc}', file=sys.stderr, flush=True)
            journal = job / 'journal.json'
            if journal.exists() and json.loads(journal.read_text(encoding='utf-8'))['phase'] == 'installing':
                raise  # Keep recovery marker when rollback itself fails.
            result = {'ok': False, 'message': 'Update failed; the previous version was kept. See the update log in .cache/' + job.name + '/update.log.'}
            if not recover:
                process = start_backend(root)
                healthy(process, (root / 'VERSION').read_text(encoding='utf-8').strip())
        write_json(root / 'data/windows-update-result.json', {'id': request['id'], **result})
        marker.unlink()


if __name__ == '__main__':
    main()
