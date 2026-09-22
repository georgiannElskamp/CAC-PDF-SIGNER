# CAC PDF Signer 0.7.0-rc.4

Portability release candidate; hardware validation remains in progress.

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

Automated signing, runtime and editor-transport checks pass. Signing on the second Windows desktop, physical legacy CSP middleware and a Linux hardware CAC still need validation. See the [validation matrix](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/blob/v0.7.0-rc.4/docs/TESTING.md).
