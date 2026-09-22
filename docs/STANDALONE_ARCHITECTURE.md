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

Requires Windows 10 or later, x64; tested with ONLYOFFICE Desktop Editors 9.4.0.129. The signature-field adapter and native-process interface depend on editor internals.

This editor version splits native executable paths at the first space, including quoted paths. The plugin installation path must therefore have no spaces. PDF filenames and save locations are unaffected.

The signing executable is unsigned. Managed devices may require administrator approval to run it.

## Build

Use Windows x64 and the official CPython 3.11.9 distribution. Create a virtual environment outside the checkout and obtain `pdfsign-bridge.exe` from the [v0.1.0 release](https://github.com/192d-Wing/pdf-sign/releases/tag/v0.1.0).

```powershell
python -m pip install -r requirements-build.txt
python -B build_standalone.py --output ..\standalone-build --bridge ..\pdfsign-bridge.exe
```

The builder verifies the bridge and license checksums, packages the runtime with PyInstaller, checks the DLL inventory and dependency imports, and writes:

- `CAC-PDF-Signer.plugin`
- `SHA256SUMS.txt`

Build output must be outside the checkout. `--reuse-executable` repackages assets during development; rebuild the executable after changes to Python source or dependencies.

The build uses only Python and Windows directories for native-library lookup. Windows supplies the Universal CRT and API-set libraries. Changing Python, either OpenSSL version, or the native DLL inventory requires reviewing and updating the accompanying notices.

## Distribution

Keep the current plugin, `SHA256SUMS.txt`, and `INSTALL.txt` in `release/`. That directory is excluded from source packaging and Git. Attach the plugin and checksum to a GitHub Release when publishing. The plugin contains the corresponding project source and dependency licenses.
