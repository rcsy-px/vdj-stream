# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Report it
privately through GitHub's security advisory feature for this repository.

Include a clear reproduction, affected version, and potential impact. Avoid
including credentials, cookies, personal data, or private media URLs.

## Security model

VDJ Companion binds only to `127.0.0.1` and is not intended to be exposed to a
local network or the public internet. It stores runtime logs and caches only
inside its local project directory and does not include telemetry.
