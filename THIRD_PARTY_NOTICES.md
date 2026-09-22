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

The builders verify these checksums before packaging.

## Helvetica metrics

`helvetica_metrics.py` derives its Helvetica WinAnsi character advances from ReportLab 5.0.1, under BSD-3-Clause. The copyright and license are in `licenses/reportlab-BSD-3-Clause.txt`.

- Source: https://hg.reportlab.com/hg-public/reportlab/ (`reportlab/pdfbase`)

## Python dependencies and runtime

`requirements-lock.txt` pins the production dependencies, including pyHanko, cryptography, asn1crypto, pyhanko-certvalidator and Pillow. ReportLab is used for tests. Dependency licenses are included in release archives under `licenses/dependencies`.

PyInstaller 6.19.0 packages CPython 3.11.9 and the dependencies. The archive includes PyInstaller's GPL license and bootloader exception, the CPython license, and setuptools notices. Integration source is included under `source/`.

- PyInstaller source: https://github.com/pyinstaller/pyinstaller/tree/v6.19.0
- CPython source: https://github.com/python/cpython/tree/v3.11.9
- Python packages: https://pypi.org/
