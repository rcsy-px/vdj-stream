# Windows application updates

The Windows updater is being prepared for 0.3.1. It is not included in the
already published 0.3.0 or 0.2.0 packages. Those need one manual upgrade first.

Start Companion with `START.bat`. When a newer compatible Windows release is
available, close VirtualDJ, finish or cancel downloads, then choose **Install
update & restart** in the panel. Leave the tab open until Companion reconnects.

The updater verifies the release checksum and plugin checksum, checks archive
paths and version, and waits for the old backend to exit before replacing files.
It keeps `data`, `.env`, portable tools and browser profiles. Application files,
the Python environment and the installed VirtualDJ plugin are backed up under
`.cache/app-update-*/backup`. Logs are in the same job folder's `update.log`.

Dependency installation or backend startup failure triggers rollback. If the
machine is interrupted, the START launcher attempts recovery before starting.
If recovery cannot finish (for example a file is locked), close VirtualDJ and
retry; the recovery marker and backup are retained. Do not delete that job folder.

The application and plugin must be installed in folders writable by your Windows
account. The updater does not request administrator privileges. It uses the
published Windows release channel; the macOS beta channel is unchanged.

## Local rehearsal

A local test fixture can simulate the next release without publishing it. This
requires a test-only launcher, kept outside the shipped application, that points
its release checker at a local ZIP. It exercises the real verification, installer,
restart and browser flow. It is not evidence that old published Windows versions
already contain an updater.
