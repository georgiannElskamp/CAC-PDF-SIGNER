# Release checks

## Automated

```sh
python -B run_tests.py
node tests/test_background.js
node tests/test_native.js
python -B audit_public.py
```

Tests cover field selection, signature integrity, text sizing, page rotation, native messaging and Save As recovery. Signing tests use temporary software credentials.

## Desktop validation

- Install through Plugin Manager and enable **Background plugins > CAC PDF Signer**.
- Sign an empty field with a connected CAC, save and reopen the PDF.
- Verify the signature and inspect wide, narrow, shallow and rotated fields.
- Cancel Save As, then retry without signing again.

## 0.6.0-dev status

| Platform | Result |
| --- | --- |
| Windows desktop | Validated by the maintainer on 2026-09-22. |
| Second Windows desktop | Pending. |
| Ubuntu 26.04 / WSL | Field click, PIN, signing, Save As and reopening passed with a software token. Signature integrity and original PDF bytes verified. |
| Debian 10 / glibc 2.28 | Frozen runtime dependency check passed. |
| Linux hardware CAC | Pending; no USB reader was attached to WSL. |
| ARM64, musl, Flatpak/Snap | Unverified. |

All 27 Python tests pass on Linux; Windows passes 23 and skips four Linux-only tests. Both JavaScript suites pass. Reader-process startup, socket permissions and cleanup were checked separately.

The adapter polling change has automated coverage; the native workers are unchanged from the desktop-validated build. Repeat desktop validation with the packaged update before publishing.

## Publish

Run `python -B publish_release.py` to check the local package. Publishing requires Git, an authenticated GitHub CLI with repository/workflow access, and completed desktop validation. Commit the source, then run `python -B publish_release.py --publish`.

Publishing pushes the commit to `main`, pushes the version tag, uploads the checked package as a draft release, and dispatches the release workflow. GitHub runs Windows and Linux tests, checks the package against the tagged source, then publishes the release. Versions containing a hyphen are prereleases. A failed workflow leaves the release in draft.

To retry an uploaded draft after a workflow failure, run **Actions > Publish release > Run workflow** with the same tag. Rebuild and use a new version if the source or package changes.
