# Testing and compatibility

Each research PR and release candidate runs the same source, package and hosted-editor checks. The release PR links the exact tested artifact and reports. See [GitHub maintenance](AUTOMATION.md) for the approval and publication process.

## Run source tests

Use Python 3.11 and Node 22. Install `requirements-dev.txt` in an environment outside the checkout, then run:

```sh
python -B tools/run_tests.py
node tests/test_background.js
node tests/test_native.js
python -B tools/audit_public.py
```

The Python suite checks PDF conversion, signature integrity, handoff records, Save As protection, recovery, platform boundaries and controller decisions. The JavaScript suites check adapter and native-host behavior. The publication audit permits only a hash-pinned, synthetic ONLYOFFICE form PDF under `tests/fixtures/`; it rejects other PDFs and generated files from source.

For a built package, run `python -B tools/verify_package.py <path-to-CAC-PDF-Signer.plugin>`. Add `--preflight` to check the packaged worker's desktop dependencies and recovery storage. Neither option accesses a card. Node is needed by this test on Windows, but not by end users.

## Hosted qualification

`tests/editor_ci.py` installs the pinned official ONLYOFFICE Desktop Editors 9.4.0.129 on disposable Windows and Ubuntu GitHub runners. It checks the packaged plugin's Background plugins listing, native preflight, disable, uninstall and reinstall. Candidate builds require a second editor session that opens the synthetic PDF form in Preview mode, clicks its signature box, and produces an unsigned review PDF with a visible standard signature field. A PDF parser compares the review copy's page content and field rectangle to the editor-loaded snapshot. The test uses paths with spaces and an accented character. Where the open source file can be replaced, the check also verifies that the handoff uses the loaded snapshot rather than the changed disk file. Compatibility runs require this form check for releases 0.9.0 and later; earlier releases are checked against their supported standard-PDF workflow.

Other required jobs exercise Linux GUI signing with a software token, native PIN entry, Save As cancellation/recovery, a fresh editor restart and independent PDF verification. Windows CNG qualification uses a disposable software certificate and the bundled bridge. Neither simulation proves physical CAC, reader, driver or provider compatibility. Windows standard-user profile initialization remains a diagnostic limit outside the required matrix.

## Local validation of the form handoff

On 2026-09-23, a disposable ONLYOFFICE 9.4.0.129 Windows profile loaded the synthetic form and the new adapter read its recovery PDF. A real pointer click on the box reached the background plugin without opening the image-signature dialog. A temporary Windows-only package then passed the full card-free first stage: plugin installation, background startup, review-copy creation and opening, and visible standard `/Sig` field. The review copy retained the editor-loaded page content. The source file was locked while open on this Windows installation, so changing it after load was not locally tested. The same packaged plugin also passed two ordinary PDF install/uninstall cycles. The temporary editor was stopped and the plugin uninstalled after the tests.

The source tests passed on Windows: 94 tests, with five Linux-only skips; both JavaScript suites passed. The full combined Windows/Linux candidate and Linux form-editor lane must pass GitHub qualification before this change can reach a release. The maintainer previously reported physical CAC signing of an earlier form-support candidate on Windows; that does not validate this new two-stage handoff.

## Compatibility limits

| Component | Covered scope |
| --- | --- |
| ONLYOFFICE | Desktop Editors 9.4.0.129 internals; other versions require adapter validation |
| Windows | Windows 10 or later, x64, CNG or legacy CSP card provider; unsigned worker may be blocked by application policy |
| Linux | x86_64, glibc 2.28+, GTK 3, desktop display and reader access |
| Form source | Saved and reopened PDF form, one unambiguous empty signature box, Preview mode, no existing PDF signature |
| PDF | Unencrypted, at most 40 MB; integrity checked after signing |

ARM64, musl-based Linux, macOS, browser editing, Flatpak, Snap, network installations and every PDF layout are outside the validated package. RPM and AppImage installation remain untested. The Linux software-token test does not cover physical card readers. A working editor does not establish permission to execute the worker or access a reader.

For a physical-card release check, install the candidate through Plugin Manager, sign a standard PDF field and an ONLYOFFICE form review copy, save and reopen each PDF, inspect the visible text and validate the signature in an independent PDF verifier. Retry Save As after cancellation and repeat on another Windows profile with spaces when possible. Keep test documents, certificate details and PINs out of issues and artifacts.
