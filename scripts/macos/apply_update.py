"""Standard-library-only transactional installer, run after the backend stops."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

MANAGED = ('backend', 'docs', 'scripts/macos', 'plugin/online-source/prebuilt/macos',
           'START.command', 'STOP.command', 'README.md', 'LICENSE', 'VERSION',
           'MACOS_VERSION', 'pyproject.toml', 'uv.lock')


def remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target, follow_symlinks=False)


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value), encoding='utf-8')
    temporary.replace(path)


def rollback(plan, backup):
    for item in plan:
        target = Path(item['target'])
        remove(target)
        if item['existed']:
            copy(backup / str(item['index']), target)


def apply(root, job, request, recover=False):
    backup = job / 'backup'
    journal = job / 'journal.json'
    if recover:
        if journal.exists():
            state = json.loads(journal.read_text())
            if state['phase'] == 'installing':
                rollback(state['plan'], backup)
                write_json(journal, {**state, 'phase': 'rolled-back'})
        return {'ok': False, 'message': 'An interrupted update was recovered. Retry the update.'}
    result = subprocess.run(['pgrep', '-ix', 'VirtualDJ'], capture_output=True)
    if result.returncode != 1:
        raise RuntimeError('Close VirtualDJ before updating Companion.')
    staged = job / 'staged'
    if (staged / 'MACOS_VERSION').read_text().strip() != request['version']:
        raise RuntimeError('Staged version changed; update refused.')
    spec = importlib.util.spec_from_file_location('companion_installer', root / 'scripts/macos/install_plugin.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    targets = [root / name for name in (*MANAGED, '.venv')]
    targets += [directory / installer.BUNDLE for directory in installer.destinations(Path.home(), os.environ.get('VDJ_PLUGIN_DIR'))]
    plan = [{'index': index, 'target': str(path), 'existed': path.exists() or path.is_symlink()}
            for index, path in enumerate(targets)]
    backup.mkdir()
    # No installed files are touched until the complete backup is available.
    for item in plan:
        if item['existed']:
            copy(Path(item['target']), backup / str(item['index']))
    write_json(journal, {'phase': 'installing', 'plan': plan})
    try:
        for name in MANAGED:
            remove(root / name)
            if (staged / name).exists():
                copy(staged / name, root / name)
        env = {**os.environ, 'VDJ_NO_BROWSER': '1'}
        # Python tools and user data stay in place. Restore .venv if sync fails.
        subprocess.run(['bash', 'scripts/macos/setup.sh', '--skip-plugin-install'],
                       cwd=root, env=env, check=True, timeout=1200)
        python = str(root / '.venv/bin/python')
        subprocess.run([python, 'scripts/macos/install_plugin.py'], cwd=root, env=env, check=True, timeout=60)
        subprocess.run([python, '-c',
            'from backend.app.main import _health_payload; assert _health_payload()["ok"]'],
            cwd=root, env=env, check=True, timeout=30)
        write_json(journal, {'phase': 'complete', 'plan': plan})
        return {'ok': True, 'message': 'Companion was updated successfully.'}
    except BaseException:
        rollback(plan, backup)
        write_json(journal, {'phase': 'rolled-back', 'plan': plan})
        raise


def main():
    root = Path(sys.argv[1]).resolve()
    request = json.loads((root / 'data/macos-update-active.json').read_text())
    job = (root / '.cache' / request['job']).resolve()
    if job.parent != (root / '.cache').resolve() or not job.name.startswith('app-update-'):
        raise SystemExit('Invalid update job path.')
    try:
        result = apply(root, job, request, '--recover' in sys.argv)
    except Exception as exc:
        result = {'ok': False, 'message': 'Update failed; the previous version was restored. See update.log in the update backup folder.'}
        print(f'Update failed: {exc}', file=sys.stderr)
        # If rollback itself failed, leave the recovery marker for the launcher.
        journal = job / 'journal.json'
        if journal.exists() and json.loads(journal.read_text())['phase'] == 'installing':
            raise
    write_json(root / 'data/macos-update-result.json', {'id': request['id'], **result})
    (root / 'data/macos-update-active.json').unlink()
    print(result['message'])


if __name__ == '__main__':
    main()
