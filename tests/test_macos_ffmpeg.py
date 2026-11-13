import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('mac_ffmpeg', Path(__file__).resolve().parents[1] / 'scripts/macos/install_ffmpeg.py')
ffmpeg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ffmpeg)


def archive(path, name, content=b'binary'):
    with zipfile.ZipFile(path, 'w') as output:
        output.writestr(name, content)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_hash_failure_never_extracts(tmp_path):
    source = tmp_path / 'tool.zip'
    archive(source, 'ffmpeg')
    with pytest.raises(RuntimeError, match='checksum'):
        ffmpeg.unpack(source, tmp_path / 'ffmpeg', '0' * 64)
    assert not (tmp_path / 'ffmpeg').exists()


@pytest.mark.parametrize('name', ['../ffmpeg', '/ffmpeg', 'bin/ffmpeg'])
def test_only_exact_archive_member_is_accepted(tmp_path, name):
    source = tmp_path / 'tool.zip'
    digest = archive(source, name)
    with pytest.raises(RuntimeError, match='expected executable'):
        ffmpeg.unpack(source, tmp_path / 'ffmpeg', digest)
    assert not (tmp_path / 'ffmpeg').exists()


def test_symlink_is_rejected(tmp_path):
    source = tmp_path / 'tool.zip'
    item = zipfile.ZipInfo('ffmpeg')
    item.external_attr = 0o120777 << 16
    with zipfile.ZipFile(source, 'w') as output:
        output.writestr(item, '/etc/passwd')
    with pytest.raises(RuntimeError, match='Invalid'):
        ffmpeg.unpack(source, tmp_path / 'ffmpeg', hashlib.sha256(source.read_bytes()).hexdigest())


def test_second_download_failure_preserves_existing_pair(tmp_path, monkeypatch):
    destination = tmp_path / 'tools/ffmpeg/bin'
    destination.mkdir(parents=True)
    for name in ffmpeg.TOOLS:
        (destination / name).write_bytes(b'old')
    monkeypatch.setattr(ffmpeg, 'working', lambda path: path.parent != destination)
    monkeypatch.setattr(ffmpeg.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0))
    # The selected dictionary is retained during installation.
    checksums = {'ffmpeg': '', 'ffprobe': ''}
    monkeypatch.setitem(ffmpeg.BUILDS, 'arm64', ('test', checksums))
    def fetch(url, path):
        if 'ffprobe.zip' in url:
            raise RuntimeError('network failure')
        checksums['ffmpeg'] = archive(path, 'ffmpeg', b'new')
    monkeypatch.setattr(ffmpeg, 'download', fetch)
    with pytest.raises(RuntimeError, match='network failure'):
        ffmpeg.install(tmp_path, 'arm64')
    assert all((destination / name).read_bytes() == b'old' for name in ffmpeg.TOOLS)


@pytest.mark.parametrize('architecture', ['arm64', 'x86_64'])
def test_install_pair_and_reuse_without_network(tmp_path, monkeypatch, architecture):
    checksums = dict.fromkeys(ffmpeg.TOOLS, '')
    monkeypatch.setitem(ffmpeg.BUILDS, architecture, ('test/' + architecture, checksums))
    monkeypatch.setattr(ffmpeg.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr(ffmpeg, 'working', lambda path: path.is_file())
    urls = []
    def fetch(url, path):
        urls.append(url)
        name = path.stem
        checksums[name] = archive(path, name, name.encode())
    monkeypatch.setattr(ffmpeg, 'download', fetch)
    ffmpeg.install(tmp_path, architecture)
    assert len(urls) == 2 and all(architecture in url for url in urls)
    assert all((tmp_path / 'tools/ffmpeg/bin' / name).read_bytes() == name.encode() for name in ffmpeg.TOOLS)
    ffmpeg.install(tmp_path, architecture)
    assert len(urls) == 2


def test_invalid_override_does_not_fall_back_to_download(tmp_path, monkeypatch):
    monkeypatch.setattr(ffmpeg, 'download', lambda *a: pytest.fail('Unexpected download'))
    with pytest.raises(FileNotFoundError):
        ffmpeg.install(tmp_path, 'arm64', str(tmp_path / 'missing'))
