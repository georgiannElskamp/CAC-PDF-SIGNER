# CAC PDF Signer 0.7.0-rc.6

Current approved release as of 2026-09-22. The tested plugin, checksum and version tag are unchanged.

The maintainer verified the published plugin with a physical CAC on two additional Windows installations. A fresh Debian 12 x86_64 installation also passed simulated-card signing, visible signature rendering, native PIN and Save As dialogs, cancellation/recovery and independent PDF signature verification. Physical CAC signing on Linux remains unverified; this limitation is accepted for the current release.

- Fixed Windows startup with spaces, Unicode and percent signs in profile paths. Existing short-name aliases also support long runtime paths.
- Fixed valid extended Windows Save As paths and protected the source PDF against path aliases.
- Check recovery storage before requesting a card operation.
- Removed runtime extraction into temporary storage. Linux temporary directories can be mounted without execution permission.
- Fixed administrator-owned Linux installations and long private reader socket paths.
- Added legacy Windows CSP signing and embedded fonts for additional Latin, Greek, Cyrillic and CJK certificate names.
- Acknowledge worker results before shutdown to prevent intermittent loss through ONLYOFFICE's process interface.
- Added specific startup errors, runtime/source manifests and checks of both shipped workers before GitHub publication.
- Check desktop libraries, display access and recovery storage when the background plugin starts, before attaching signature handlers.
- Reject Linux builds containing binaries for the wrong CPU or requiring glibc newer than the declared baseline.
- Add fresh-editor installation, background startup, disable, uninstall and reinstall checks as Windows/Linux publication requirements. The Linux sequence also passes locally.
- Organize build and release commands under `tools/`, separate installation and developer documentation, and remove the earlier alternatives comparison.
- Allow release checks to fetch draft assets, with download credentials excluded from the worker and editor test steps.

Install the single `CAC-PDF-Signer.plugin` through Plugin Manager, then enable **CAC PDF Signer** under **Background plugins**. Disable it before updating or removing it, and reopen the PDF after updating. No separate Python installation or persistent signing service is required.

Requires ONLYOFFICE Desktop Editors 9.4.0.129, Windows x64 or Linux x86_64 with glibc 2.28+, GTK 3 and reader access. ARM64 and musl builds are not included. Sandboxed installations and network-hosted plugins remain unverified.

Automated source, packaged-runtime and fresh-editor installation checks pass. The minimal Debian editor installation required `libgbm1`. The software-token test required a compatible provider build because the stock provider needed a newer C++ runtime than the plugin bundles; no plugin files changed. Physical legacy CSP middleware, Linux hardware CACs and arbitrary third-party providers remain unverified. See the [current validation matrix](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/blob/main/docs/TESTING.md).

The `0.7.0-rc.6` label is retained so downloads remain byte-for-byte identical to the validated build. Documentation embedded in the archive records its original candidate status; these release notes and the current repository documentation record the subsequent validation and acceptance.
