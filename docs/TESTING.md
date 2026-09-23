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

### Hosted signing regression

The unchanged approved plugin passed the [hosted compatibility matrix](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/actions/runs/35768964456) on 2026-09-22. Windows and Ubuntu installation checks passed. A disposable Debian 12 container also verified an actual pointer click, native PIN prompt, PKCS#11 signature, Save As cancellation and recovery without another PIN, a spaced Unicode save path, unchanged original bytes, independent Poppler verification and reopening the signed field. The bundled reader stack passed a separate no-card control without system smart-card middleware.

The rendered certificate text was inspected using synthetic identity `EXAMPLE.TEST.0000000000`. Generated keys and token files were confined to the disposable container and excluded from artifacts. The screenshot and structured report are retained for 14 days; the workflow result and compatibility issue retain the pass record. This adds repeatable software-token coverage, not physical Linux hardware validation. See [GitHub maintenance](AUTOMATION.md).

## Current release

Version 0.7.0-rc.6 was accepted for release on 2026-09-22. Its artifact and version label are unchanged from the tested candidate. It retains the rc.2 signing code and corrects draft-asset access, Linux editor launch and Windows test-process cleanup in the release workflow.

The `research` branch has unreleased ONLYOFFICE form-box support. A saved form made by ONLYOFFICE 9.4.0.129 was inspected without changing the original. The Preview-mode click adapter was exercised in a disposable editor profile. A copy of the form was signed with an in-memory synthetic certificate and reopened with the visible appearance in the same rectangle; pyHanko verified its cryptographic integrity. This does not establish physical CAC behavior, Linux editor behavior, or preservation of every kind of multi-field ONLYOFFICE form. A rebuilt Windows/Linux `.plugin` and hosted qualification are required before release.

| Check | Result |
| --- | --- |
| Release workflow | Windows/Linux source, packaged-worker and fresh-editor installation checks [passed](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/actions/runs/35749846160). |
| Physical CAC on Windows | The maintainer reports successful validation of the published plugin on two additional Windows installations. Reader and middleware details were not recorded. |
| Fresh Debian 12 x86_64 | Official ONLYOFFICE 9.4.0, ordinary user, profile and save paths containing spaces and an accented character: install, Background plugins listing, startup, disable, uninstall and reinstall pass. |
| Simulated card signing on Debian 12 | Native PIN prompt, existing signature field, certificate text, Save As, cancellation/recovery without another PIN, and reopening the saved PDF pass. Poppler independently verifies the signature; the original PDF remains unchanged. |
| Bundled Linux reader | Starts without system OpenSC or PC/SC packages and correctly reports no connected eligible card. Physical reader signing remains unverified. |

The Debian test used a separate disposable WSL installation, with Windows drive automount and Windows process interoperability disabled. The plugin used its bundled signing runtime; existing WSL distributions were not used. The temporary installation, software token and all its test files were removed afterward.

ONLYOFFICE required the Linux graphics package `libgbm1` before it could start. Debian's stock SoftHSM provider required a newer C++ runtime than the plugin bundles, so a compatible test provider was built with its C++ runtime statically linked. No plugin files were modified. These results do not establish compatibility with arbitrary PKCS#11 providers, physical Linux readers or every distribution. The maintainer accepted these Linux validation limits for this release.

Tested plugin SHA-256: `e0af01f17b70c30efe4790ef01aa51c7b9105ba1c3a00d2e5f98f0a876b8f3e7`.

The following tables record earlier checks; they are not additional tests of the final artifact.

### 0.7.0-rc.2 baseline

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

## Checks for future releases

- Install through Plugin Manager and enable **Background plugins > CAC PDF Signer**.
- Sign an empty field with a connected CAC, save and reopen the PDF.
- Verify the signature and inspect wide, narrow, shallow and rotated fields.
- Cancel Save As, then retry without signing again.
- Repeat under a profile containing spaces on another Windows desktop.
- Test a normal, non-root Linux desktop with a physical CAC and reader when available; record whether results use hardware or a simulated card.

Other ONLYOFFICE builds need adapter validation. ARM64 and musl builds are not supplied. Flatpak/Snap, RPM/AppImage installation, network installations, provider-specific PIN behavior and managed execution policies remain outside the validated matrix. A working ONLYOFFICE installation does not by itself establish permission to execute a plugin worker or access a USB reader.

## Publish

Run `python -B tools/publish_release.py` to check a newly prepared package. Record completed checks and untested configurations before publication. Hardware validation limits must remain explicit in release notes, including when the maintainer accepts them for release. See [build and release instructions](BUILDING.md).

Publishing pushes the commit and version tag, uploads a draft release and dispatches the release workflow. GitHub runs Windows/Linux source tests, executes both uploaded native workers, tests installation and simulated Linux signing, and checks the package against the tagged source before requesting maintainer approval. Versions containing a hyphen are initially published as prereleases. A failed workflow leaves the release in draft. A validated candidate can subsequently be promoted in GitHub without changing its tag or assets.

To retry an uploaded draft after a workflow failure, run **Actions > Publish release > Run workflow** with the same tag. Rebuild and use a new version if the source or package changes.

## Required candidate qualification

Research PRs and research/release-verification snapshots run the same full build and qualification matrix. Extended probes live in `tests/qualification`. Windows CNG uses a disposable software certificate; Linux virtual CAC tests use synthetic card data and the bundled OpenSC path. Neither proves physical-card compatibility. Windows standard-user profile initialization remains a recorded diagnostic limit outside the required matrix. The release PR links the exact candidate and its reports; publication promotes those bytes after maintainer approval. See [GitHub maintenance](AUTOMATION.md).
