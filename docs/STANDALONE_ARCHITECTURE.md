# Architecture and builds

The `.plugin` archive contains the background JavaScript, Windows and Linux signing workers, source and license notices. Each worker includes Python and its dependencies.

## Signing flow

1. The background script attaches to PDF signature-field clicks.
2. A hidden `onlyoffice:` frame launches the bundled worker through ONLYOFFICE's `ExternalProcess` API. Windows uses `native/cac-signer.exe`; Linux uses a bundled shell launcher and `native/linux-x86_64/cac-signer`.
3. The frames validate message origins. The worker receives the PDF and field name over standard input and returns JSON events over standard output.
4. Windows uses the CNG bridge. Linux uses python-pkcs11 and OpenSC. A Windows mutex or Linux file lock serializes signing and Save As across editor tabs.
5. The worker verifies the signed PDF, writes a recovery copy, and opens a native Save As dialog. Linux reuses the GTK 3 library required by the desktop editor.
6. After saving, the background script opens the result through `_openExternalReference`. The worker exits.

Cancelling Save As preserves the signed recovery copy. A subsequent click on the same field retries saving those bytes.

## Compatibility

Requires ONLYOFFICE Desktop Editors 9.4.0.129 on Windows x64 or Linux x86_64 with glibc 2.28 or later. The signature-field adapter and native-process interface depend on editor internals. The PDF editor can report `editorType: word` and `editorSubType: pdf`; the manifest and startup guard account for that.

This editor version splits Windows executable paths at the first space. A Windows plugin installation path without spaces is required; the plugin reports this limitation before requesting a PIN. Linux launches `/bin/sh` with an argument parsed by the editor, without evaluating the plugin path as shell code.

Linux needs access to a supported reader. A bundled, patched PC/SC process uses a private socket when no system PC/SC service is available, and terminates after the operation. It does not request root access, install a daemon, or change device permissions. The kernel, libc, desktop libraries and USB access policy remain operating-system requirements. ARM64 and musl builds are not supplied.

The signing executable is unsigned. Managed devices may require administrator approval to run it.

## Build

Use Windows x64 and the official CPython 3.11.9 distribution. Create a virtual environment outside the checkout and obtain `pdfsign-bridge.exe` from the [v0.1.0 release](https://github.com/192d-Wing/pdf-sign/releases/tag/v0.1.0).

```powershell
python -m pip install -r requirements-build.txt
python -B build_standalone.py --output ..\standalone-build --bridge ..\pdfsign-bridge.exe --linux-bundle ..\linux-bundle
```

The builder verifies the bridge and license checksums, packages the runtime with PyInstaller, checks the DLL inventory and dependency imports, and writes:

- `CAC-PDF-Signer.plugin`
- `SHA256SUMS.txt`

Build output must be outside the checkout. `--reuse-executable` repackages assets during development; rebuild the executable after changes to Python source or dependencies.

The build uses only Python and Windows directories for native-library lookup. Windows supplies the Universal CRT and API-set libraries. Changing Python, either OpenSSL version, or the native DLL inventory requires reviewing and updating the accompanying notices.

### Linux worker

Build in an isolated x86_64 Linux environment with glibc 2.28 and GCC 8.3 or a compatible compiler. `native_linux/runtime.json` pins the Python distribution. Install `requirements-linux.txt`, PyInstaller 6.19.0, Meson and Ninja in its virtual environment. Build tools also include make, pkg-config, flex, autoconf, automake, libtool and Perl. These tools are not needed by end users.

Download and verify the sources in `native_linux/sources.json` into `/opt/src`. Run `sh native_linux/build_middleware.sh` to build into `/opt/native`; the script verifies every source archive before extraction. Its `CAC_NATIVE_PREFIX`, `CAC_NATIVE_SOURCES` and `CAC_NATIVE_WORK` variables can select other absolute locations. Use a fresh build directory.

```sh
python -B build_linux.py --output /opt/linux-bundle --prefix /opt/native --sources /opt/src --work /opt/freeze-work
```

Copy the resulting `linux-bundle` directory to the Windows build machine and pass it to `build_standalone.py`. The final package contains both workers. OpenSC, libusb, PC/SC and CCID source archives accompany the native runtime; the PC/SC adaptation is in `native_linux/private_pcsc.py`.

## Distribution

Keep `CAC-PDF-Signer.plugin`, `SHA256SUMS.txt`, and `INSTALL.txt` in `release/`. The plugin includes project source and dependency licenses; the release directory is excluded from Git and source packaging.

`publish_release.py` checks the local package. With `--publish`, it pushes the committed source and version tag, uploads a draft release, and starts `.github/workflows/release.yml`. The workflow verifies the uploaded assets and runs tests on Windows and Linux before publishing. See [release checks](RELEASE_CHECKS.md).
