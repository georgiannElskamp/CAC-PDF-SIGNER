# CAC PDF Signer 0.6.0-dev

- Added a bundled native Linux worker with OpenSC, PC/SC and USB CCID support.
- Fixed Background plugin discovery when the PDF editor identifies itself as a document editor.
- Reduced repeated signature-field lookups in the background adapter.
- Added checked release publishing and Windows/Linux CI.

Install `CAC-PDF-Signer.plugin` through Plugin Manager, then enable **CAC PDF Signer** under **Background plugins**. No separate Python installation or signing service is required.

Requires ONLYOFFICE Desktop Editors 9.4.0.129. Windows requires x64 and a plugin installation path without spaces. Linux requires x86_64, glibc 2.28+, GTK 3 and reader access.

The maintainer validated the preceding build on one Windows desktop. Second-desktop validation and Linux hardware-CAC testing remain pending. Linux signing was tested with a software token. ARM64, musl and Flatpak/Snap are unverified.
