"""Locate the exact Windows Chromium revision shipped with installed Playwright."""

import json
from importlib.resources import files
from pathlib import Path


def chromium_executable(browser_root: Path) -> Path | None:
    manifest = files("playwright").joinpath("driver/package/browsers.json")
    browser = next(item for item in json.loads(manifest.read_text())['browsers']
                   if item['name'] == 'chromium')
    revision = browser.get('revisionOverrides', {}).get('win64', browser['revision'])
    directory = browser_root / f"chromium-{revision}"
    return next(directory.glob("*/chrome.exe"), None)
