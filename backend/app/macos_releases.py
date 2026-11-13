"""Independent Mac release channel; Windows and yt-dlp keep their stable feeds."""
import re
import secrets
import httpx
from .update_checker import GitHubReleaseChecker


def mac_version(value: str):
    match = re.fullmatch(r"(?:macos-v|v)?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?", value)
    if not match:
        return None
    major, minor, patch, beta = match.groups()
    return (int(major), int(minor), int(patch), int(beta) if beta else float('inf'))


class MacReleaseChecker(GitHubReleaseChecker):
    async def _fetch(self):
        prefix = f"https://github.com/{self.repository}/releases/"
        candidates = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True,
                                     headers={'Accept': 'application/vnd.github+json',
                                              'Cache-Control': 'no-cache',
                                              'User-Agent': 'VDJ-Companion-macOS'}) as client:
            response = await client.get(f"https://api.github.com/repos/{self.repository}/releases?per_page=100&_={secrets.token_hex(16)}")
            response.raise_for_status()
        for release in response.json():
            tag = str(release.get('tag_name', ''))
            version = mac_version(tag)
            if release.get('draft') or version is None:
                continue
            url = prefix + 'tag/' + tag
            if release.get('html_url') != url:
                continue
            assets = {item['name']: item for item in release.get('assets', [])}
            for name, asset in assets.items():
                if not name.endswith('-macos-universal.zip'):
                    continue
                download = prefix + 'download/' + tag + '/' + name
                checksum = assets.get(name + '.sha256', {})
                if asset.get('browser_download_url') != download:
                    continue
                if checksum.get('browser_download_url') != download + '.sha256':
                    continue
                candidates.append((version, {'latestVersion': tag.removeprefix('macos-v').removeprefix('v'),
                    'releaseUrl': url, 'downloadUrl': download, 'checksumUrl': download + '.sha256',
                    'assetName': name, 'assetDigest': asset.get('digest')}))
        current = mac_version(self.current_version)
        if not candidates:
            return {'currentVersion': self.current_version, 'latestVersion': None,
                    'updateAvailable': False, 'releaseUrl': None, 'downloadUrl': None,
                    'error': 'No compatible macOS release was found.'}
        version, result = max(candidates, key=lambda item: item[0])
        return {'currentVersion': self.current_version, **result,
                'updateAvailable': bool(current and version > current)}
