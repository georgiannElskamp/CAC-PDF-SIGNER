# Testing and compatibility

## Automated

Run from the repository root after installing `requirements-dev.txt` in an environment outside the checkout. Python 3.11 and Node 22 are used by CI. Linux card-runtime tests also need `requirements-linux.txt`.

```sh
python -B tools/run_tests.py
node tests/test_background.js
node tests/test_native.js
python -B tools/audit_public.py
python -B tools/verify_package.py release/CAC-PDF-Signer.plugin
```

`verify_package.py` needs Node on Windows test machines; end users do not. It extracts and checks the shipped worker under a spaced Unicode path. Add `--preflight` to check desktop libraries, Linux display access and writable recovery storage. Neither operation accesses a card or verifies hardware signing.

`tests/editor_ci.py` installs the pinned official editor on disposable GitHub-hosted runners. `tests/editor_smoke.js` exercises the editor's native installer and plugin controller, checks its Background plugins list and native preflight, then disables, removes and reinstalls the plugin. It does not enter a PIN or sign a document. These jobs are publication requirements; results are recorded in [GitHub Actions](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/actions/workflows/release.yml).

To run the editor smoke test elsewhere, use a disposable OS account or Linux XDG profile. Generate its only PDF with `node tests/editor_smoke.js --fixture <pdf-path>`, open it in ONLYOFFICE with `--remote-debugging-port=9251`, then run `node tests/editor_smoke.js --disposable-profile 9251 <absolute-plugin-path> <version>`. The tool refuses an existing CAC installation and other PDF fields. Close the test editor afterward; remote debugging should not be enabled during normal signing.

## 0.7.0-rc.2 validation

| Check | Result |
| --- | --- |
| Python regression suite | 40 tests: Windows passes 35 and skips five Linux tests; Linux passes 38 and skips two Windows tests. |
| JavaScript suites | Pass on Windows and Linux. |
| Packaged rc.2 workers | Windows and Linux preflight passes under spaced Unicode installation paths. Linux runs as UID 65534. |
| Fresh Linux ONLYOFFICE 9.4.0 installation | Official DEB extracted into an isolated Ubuntu/WSL desktop, unprivileged profile with spaces: install, Background plugins listing, startup, preflight, disable, uninstall and reinstall pass. |
| Linux desktop failure | Packaged worker rejects an unavailable display before accessing a card. Missing GTK is covered by a regression test. |
| Linux build compatibility | All 66 ELF files pass architecture and glibc 2.28 checks; regression tests reject incompatible binaries. |
| Fresh Windows editor installation with rc.2 | Required by the release workflow; consult its GitHub Actions result. Physical CAC validation on the second desktop remains pending. |

The following portability checks passed with the local rc.1 candidate. Their covered code is retained, but the complete matrix has not been repeated for rc.2.

| Check | Result |
| --- | --- |
| Windows native-process interface in ONLYOFFICE 9.4.0.129 | Packaged worker returns its result under seven synthetic profile paths, including spaces, punctuation, percent signs, accented and Chinese characters. |
| Windows extended destination and source aliases | Save and overwrite-protection tests pass. |
| Windows long paths | Worker startup passes using short-name aliases. A full plugin nested roughly 390 characters deep fails to load through ONLYOFFICE. Keep plugin installations below 260 characters. |
| Complete Windows native plugin transport | Five consecutive dependency checks pass from a spaced Unicode installation containing a literal percent expression. |
| Legacy Windows CSP | An ephemeral software-provider key signs and verifies successfully. Physical legacy middleware is untested. |
| Ubuntu 26.04 / WSL | Native runtime passes as UID 65534 with capabilities removed, with a root-owned installation and GNU chmod. |
| Linux temporary storage | Runtime passes with an isolated noexec mount; private reader socket connects despite long temporary-directory settings. |
| Debian 10 / glibc 2.28 | Native dependency check passes in a clean root filesystem. All 66 inspected ELF files require at most glibc 2.28. |
| Certificate text | Latin, Greek, Cyrillic and CJK sample signatures pass integrity checks and rendered visual inspection. |
| Recovery storage | An unavailable recovery directory is rejected before card access. Storage can still fail after the preflight check. |

An earlier published build was validated on one Windows desktop and installed on a second. Earlier Linux signing used a software token. These results do not establish hardware compatibility across different readers and card middleware.

## Desktop validation before a stable release

- Install through Plugin Manager and enable **Background plugins > CAC PDF Signer**.
- Sign an empty field with a connected CAC, save and reopen the PDF.
- Verify the signature and inspect wide, narrow, shallow and rotated fields.
- Cancel Save As, then retry without signing again.
- Repeat under a profile containing spaces on the second Windows desktop.
- Repeat on a normal, non-root Linux desktop with a physical CAC and reader.

Other ONLYOFFICE builds need adapter validation. ARM64 and musl builds are not supplied. Flatpak/Snap, RPM/AppImage installation, network installations, provider-specific PIN behavior and managed execution policies remain outside the validated matrix. A working ONLYOFFICE installation does not by itself establish permission to execute a plugin worker or access a USB reader.

## Publish

Run `python -B tools/publish_release.py` to check the local package. Publish a stable release only after the desktop checks above; incomplete hardware validation must remain explicit in prerelease notes. See [build and release instructions](BUILDING.md).

Publishing pushes the commit and version tag, uploads a draft release and dispatches the release workflow. GitHub runs Windows/Linux source tests, executes both uploaded native workers, tests installation in fresh editors and checks the package against the tagged source before publication. Versions containing a hyphen are prereleases. A failed workflow leaves the release in draft.

To retry an uploaded draft after a workflow failure, run **Actions > Publish release > Run workflow** with the same tag. Rebuild and use a new version if the source or package changes.
