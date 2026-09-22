# Architecture and builds

The `.plugin` archive contains the background JavaScript, a Windows signing executable, source and license notices. The executable includes Python and its dependencies.

## Signing flow

1. The background script attaches to PDF signature-field clicks.
2. A hidden `onlyoffice:` frame launches `native/cac-signer.exe` through ONLYOFFICE's `ExternalProcess` API.
3. The frames validate message origins. The worker receives the PDF and field name over standard input and returns JSON events over standard output.
4. The Windows CNG bridge requests a signature from the card. A Windows mutex serializes signing and Save As across editor tabs.
5. The worker verifies the signed PDF, writes a recovery copy, and opens the Windows Save As dialog.
6. After saving, the background script opens the result through `_openExternalReference`. The worker exits.

Cancelling Save As preserves the signed recovery copy. A subsequent click on the same field retries saving those bytes.

## Compatibility

Tested with Windows x64 and ONLYOFFICE Desktop Editors 9.4.0.129. The signature-field adapter and native-process interface depend on editor internals.

This editor version splits native executable paths at the first space, including quoted paths. The plugin installation path must therefore have no spaces. PDF filenames and save locations are unaffected.

The signing executable is unsigned. Managed devices may require administrator approval to run it.

## Build

Use Windows x64 and Python 3.11. Create a virtual environment outside the checkout and obtain `pdfsign-bridge.exe` from the [v0.1.0 release](https://github.com/192d-Wing/pdf-sign/releases/tag/v0.1.0).

```powershell
python -m pip install -r requirements-build.txt
python -B build_standalone.py --output ..\standalone-build --bridge ..\pdfsign-bridge.exe
```

The builder checks the bridge checksum, packages the runtime with PyInstaller, runs a dependency check, and writes:

- `CAC-PDF-Signer.plugin`
- `SHA256SUMS.txt`

Build output must be outside the checkout. `--reuse-executable` repackages assets during development; rebuild the executable after changes to Python source or dependencies.

## Legacy tools

`setup_windows.py`, `build_plugin.py`, `helper.py`, and `plugin/background.js` implement the 0.4.x helper-based edition. They are retained for regression tests. Current releases use `build_standalone.py`, `standalone.html`, and `standalone-background.js`.
