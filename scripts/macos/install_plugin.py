"""Install only our bundle; preserve existing copies as timestamped backups."""
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = "VDJ Companion Source.bundle"


def destinations(home: Path, override: str | None = None) -> list[Path]:
    if override:
        target = Path(override).expanduser().resolve()
        if not target.is_dir():
            raise RuntimeError("VDJ_PLUGIN_DIR must be an existing OnlineSources folder.")
        return [target]
    configured = os.environ.get("VDJ_HOME")
    homes = [Path(configured).expanduser()] if configured else [
        home / "Library/Application Support/VirtualDJ", home / "Documents/VirtualDJ"]
    homes = [path for path in homes if path.is_dir()]
    if len(homes) != 1:
        raise RuntimeError("Open VirtualDJ once, then close it. If multiple/custom folders exist, set VDJ_HOME (see docs/MACOS.md).")
    # Install the universal binary for every architecture already used by VirtualDJ.
    folders = [homes[0] / name / "OnlineSources"
               for name in ("PluginsMacArm", "PluginsArm", "Plugins64", "PluginsMac")
               if (homes[0] / name).is_dir()]
    if not folders:
        raise RuntimeError("No known VirtualDJ plugin folder found. Set VDJ_PLUGIN_DIR explicitly; see docs/MACOS.md.")
    return folders


def install() -> None:
    source = ROOT / "plugin/online-source/prebuilt/macos" / BUNDLE
    if not source.is_dir():
        raise RuntimeError("macOS bundle missing. Download the macOS preview ZIP, not GitHub's source archive.")
    subprocess.run(["codesign", "--verify", "--strict", str(source)], check=True)
    for directory in destinations(Path.home(), os.environ.get("VDJ_PLUGIN_DIR")):
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / BUNDLE
        executable = Path("Contents/MacOS/VDJCompanionSource")
        if (target / executable).is_file() and (target / executable).read_bytes() == (source / executable).read_bytes():
            print(f"Plugin already installed: {target}")
            continue
        if subprocess.run(["pgrep", "-ix", "VirtualDJ"], capture_output=True).returncode == 0:
            raise RuntimeError("Close VirtualDJ before installing the plugin.")
        staged = directory / f".{BUNDLE}.{os.getpid()}.tmp"
        shutil.copytree(source, staged)
        backup = None
        try:
            if target.exists():
                backup = directory / f"{BUNDLE}.backup-{time.time_ns()}"
                target.rename(backup)
            staged.rename(target)
        except Exception:
            if backup and not target.exists():
                backup.rename(target)
            raise
        finally:
            if staged.exists():
                shutil.rmtree(staged)
        print(f"Installed: {target}")


if __name__ == "__main__":
    try:
        install()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc
