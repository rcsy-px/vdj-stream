"""Locate the full Chromium build matching the installed Playwright revision."""

import json
import platform
import sys
from importlib.resources import files
from pathlib import Path


def chromium_executable(browser_root: Path) -> Path | None:
    manifest = files("playwright").joinpath("driver/package/browsers.json")
    browser = next(item for item in json.loads(manifest.read_text())['browsers']
                   if item['name'] == 'chromium')
    host = 'win64'
    pattern = '*/chrome.exe'
    if sys.platform == 'darwin':
        major = platform.mac_ver()[0].split('.')[0]
        host = f'mac{major}' + ('-arm64' if platform.machine() == 'arm64' else '')
        pattern = '*/*.app/Contents/MacOS/*'
    revision = browser.get('revisionOverrides', {}).get(host, browser['revision'])
    directory = browser_root / f"chromium-{revision}"
    return next((path for path in directory.glob(pattern) if path.is_file()), None)
