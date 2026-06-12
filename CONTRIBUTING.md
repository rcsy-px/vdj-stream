# Contributing

Contributions and focused bug reports are welcome.

## Development setup

1. Run `START.bat` once to prepare the local environment.
2. Run `.venv\Scripts\python -m pytest -q` before submitting changes.
3. Keep the backend bound to `127.0.0.1`.
4. Do not commit runtime data, logs, downloaded tools, credentials, or cookies.

## Native plugin changes

The plugin requires Visual Studio with the C++ workload. Build it with:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\online-source\build-and-install.ps1
```

That script refreshes the distributable prebuilt DLL. Include the updated
`plugin\online-source\prebuilt\x64\VdjCompanionSource.dll` with plugin changes.

## Pull requests

Keep changes scoped, explain user-visible behavior, and include relevant tests.
By contributing, you agree that your contribution is licensed under the MIT
License.
