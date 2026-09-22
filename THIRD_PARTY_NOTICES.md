# Third-party components

## ONLYOFFICE plugin SDK

`plugin/plugins.js` is the upstream ONLYOFFICE plugin bootstrap SDK from Ascensio System SIA. Its copyright header, AGPLv3 additional terms, trademark notices and GUI asset notices are retained. The AGPLv3 license is in `LICENSE`.

- Distribution: https://onlyoffice.github.io/sdkjs-plugins/v1/plugins.js
- Source: https://github.com/ONLYOFFICE/sdkjs/tree/master/common/plugins
- SHA-256: `8b3cff57a562b56610116252f021042410b568cbfdfabb22c3abb35c38c78cdf`

The CAC icons are project assets. The project name indicates ONLYOFFICE compatibility and does not imply endorsement.

## Windows signing bridge

The standalone package includes the Windows CNG executable from `192d-Wing/pdf-sign`, version `v0.1.0`, under Apache-2.0. The license is in `licenses/pdf-sign-APACHE-2.0.txt`.

- Source: https://github.com/192d-Wing/pdf-sign/tree/v0.1.0
- Release: https://github.com/192d-Wing/pdf-sign/releases/tag/v0.1.0
- Archive: `pdfsign-bridge_0.1.0_windows_amd64.zip`
- Archive SHA-256: `c65fde8bed039378f13ef663781bee2498e4418cb2361a4e94759e39ef5b4910`
- Executable SHA-256: `0c641a9a326498e90d9d5f887bfe694d389b8e7ee74857b551c240382431b067`

The builder verifies the executable checksum before packaging.

The bridge contains the Go 1.26.4 runtime and `golang.org/x/sys` v0.46.0, copyright The Go Authors, under BSD-3-Clause. Their notices are in `licenses/go-BSD-3-Clause.txt` and `licenses/go-x-sys-BSD-3-Clause.txt`.

- Go source: https://github.com/golang/go/tree/go1.26.4
- x/sys source: https://github.com/golang/sys/tree/v0.46.0

## Helvetica metrics

`helvetica_metrics.py` derives its Helvetica WinAnsi character advances from ReportLab 5.0.1, under BSD-3-Clause. The copyright and license are in `licenses/reportlab-BSD-3-Clause.txt`.

- Source: https://hg.reportlab.com/hg-public/reportlab/ (`reportlab/pdfbase`)

## Python dependencies and runtime

`requirements-lock.txt` pins the production dependencies, including pyHanko, cryptography, asn1crypto, pyhanko-certvalidator and Pillow. ReportLab is used for tests. Dependency licenses are included in release archives under `licenses/dependencies`.

PyInstaller 6.19.0 packages CPython 3.11.9 and the dependencies. The archive includes PyInstaller's GPL license and bootloader exception, the CPython license, and setuptools notices. Integration source is included under `source/`.

- PyInstaller source: https://github.com/pyinstaller/pyinstaller/tree/v6.19.0
- CPython source: https://github.com/python/cpython/tree/v3.11.9
- Python packages: https://pypi.org/

## OpenSSL

The CPython runtime includes OpenSSL 3.0.13 in `libcrypto-3.dll` and `libssl-3.dll`. The cryptography 50.0.1 Windows wheel includes OpenSSL 4.0.2. OpenSSL is developed by the OpenSSL Project and distributed under Apache-2.0; the license copies are in `licenses/openssl-3.0.13-APACHE-2.0.txt` and `licenses/openssl-4.0.2-APACHE-2.0.txt`.

- OpenSSL 3.0.13 source: https://github.com/openssl/openssl/tree/openssl-3.0.13
- OpenSSL 4.0.2 source: https://github.com/openssl/openssl/tree/openssl-4.0.2

## Microsoft runtime

The standalone executable includes `VCRUNTIME140.dll` supplied with the CPython 3.11.9 Windows distribution. Microsoft runtime code is proprietary and is not licensed under this project's AGPL license. The CPython Windows redistribution conditions are reproduced in `licenses/microsoft-runtime-CPython.txt` and in the packaged Python license.

Windows supplies the Universal CRT and API-set libraries; copies of `ucrtbase.dll` and `api-ms-win-*.dll` are not bundled. Windows 10 or later is required. Windows and separately installed card middleware retain their respective licenses.

- CPython redistribution conditions: https://github.com/python/cpython/blob/v3.11.9/PC/crtlicense.txt
- Microsoft redistribution terms: https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files

`licenses/manifest.json` records the upstream URLs and checksums for the additional license files. The builder verifies these files, runtime versions, and the native DLL inventory before packaging.

## Linux runtime

The Linux worker uses CPython 3.11.9 from python-build-standalone's 20240726 release, including OpenSSL 3.0.14 and the runtime's built-in libraries. `native_linux/runtime.json` identifies the distribution and checksums. `licenses/linux-python-sources.json` provides source locations, versions and checksums for its bundled components, including Berkeley DB under the Sleepycat license. Their complete upstream notices are retained as `licenses/linux-python-LICENSE.*`. Project integration source accompanies the plugin; Python package source releases are available from PyPI at the pinned versions in `requirements-lock.txt` and `requirements-linux.txt`.

The worker includes python-pkcs11 0.10.0 and its license under `licenses/linux/dependencies`. GCC 8.3 runtime libraries are covered by the GPL with the GCC Runtime Library Exception; their Debian copyright and license information is in `licenses/linux-gcc-runtime-COPYRIGHT.txt`.

The native card stack includes OpenSC 0.27.1 (LGPL-2.1-or-later), libusb 1.0.30 (LGPL-2.1-or-later), pcsc-lite 2.5.2 and CCID 1.8.4 (their BSD-style terms), OpenSSL 3.5.8 (Apache-2.0), and zlib 1.3.2 (zlib license). License texts are in `licenses/linux-*-LICENSE.txt`. Exact source URLs and checksums are in `native_linux/sources.json`; OpenSC, libusb, pcsc-lite and CCID source archives accompany the plugin under `native-sources/linux/`. The pcsc-lite changes for private IPC paths are supplied in `source/native_linux/private_pcsc.py`.

The operating system supplies glibc and GTK 3. The Linux worker contains no Windows executable or Microsoft runtime dependency. The combined plugin also contains a separate Windows worker, subject to the Windows notices above.
