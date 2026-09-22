# ONLYOFFICE CAC Signature Plugin

Sign PDF signature fields with a Common Access Card in ONLYOFFICE Desktop Editors. The plugin runs in the background and includes its own signing runtime.

Version 0.6.0-dev adds native Linux support. The maintainer has validated it on one Windows desktop; second-desktop validation is pending. Linux signing has been tested with a software token, not a hardware CAC.

## Requirements

- ONLYOFFICE Desktop Editors 9.4.0.129.
- Windows 10 or later, x64; or desktop Linux x86_64 with glibc 2.28 or later and GTK 3.
- A connected CAC reader and one eligible document-signing certificate. Windows uses its card middleware. Linux includes OpenSC, PC/SC and a USB CCID driver.
- On Linux, permission to access the USB reader, or access to an existing system PC/SC reader service. Sandboxed editor packages may restrict native process or USB access.
- On Windows, a plugin installation path without spaces. This editor build cannot launch the bundled worker from a profile path containing spaces; PDF and save filenames may contain spaces.

Linux was tested under Ubuntu 26.04/WSL, with runtime checks on Debian 10/glibc 2.28. ARM64, musl and Flatpak/Snap installations are unverified. WSL needs the USB reader attached to Linux.

## Install

Use `CAC-PDF-Signer.plugin` from a GitHub Release or the local `release/` folder. It includes both workers; no separate Python installation or signing service is required. Release 0.5.3 supports Windows only.

1. Open **Plugins > Plugin Manager > Available plugins > Install plugin manually**.
2. Select **CAC-PDF-Signer.plugin**.
3. Enable **CAC PDF Signer** under **Plugins > Background plugins**.

After an update, reopen the PDF or toggle the background plugin off and on.

## Sign a PDF

Save and reopen the PDF, then click an empty signature field. Enter your PIN when prompted. Choose a location in **Save signed PDF as**; the signed copy opens in ONLYOFFICE.

The signature displays your certificate name, signing time, and rank and DoD ID when available. Text wraps and scales to the field dimensions. Tall fields place the name above the signing details.

If you cancel Save As, click the same field again to save the completed signature. Recovery copies are stored in `%LOCALAPPDATA%\ONLYOFFICE-CAC-Signature\Signed` and remain after uninstalling the plugin.

On Linux, recovery files use `$XDG_DATA_HOME/ONLYOFFICE-CAC-Signature/Signed`, defaulting to `~/.local/share/ONLYOFFICE-CAC-Signature/Signed`. The plugin reuses an available PC/SC service; otherwise it starts its bundled reader process for the signing operation and stops it afterward. It installs no system service and does not change USB permissions.

## Limitations

- Requires an existing PDF signature field; drawn rectangles and typed signature lines are unsupported.
- Save and reopen edited PDFs before signing. The editor can retain an earlier version of the document in memory.
- Encrypted PDFs, files over 40 MB, hidden or ambiguous fields, and multiple eligible signing certificates are unsupported.
- Signature text uses Helvetica's Western character set.
- Verification checks signature integrity. Certificate trust, revocation and trusted timestamping are outside its scope; signing time uses the local clock.
- The plugin depends on ONLYOFFICE internals. Other editor versions may need an adapter update.

## Build and test

See [architecture and build instructions](docs/STANDALONE_ARCHITECTURE.md). Build with `build_standalone.py`; publish with `publish_release.py` after validation. The `release/` directory is excluded from Git.

For development, install `requirements-dev.txt` in a virtual environment outside the checkout, then run:

```powershell
python -B run_tests.py
node tests/test_background.js
node tests/test_native.js
python -B audit_public.py
```

See [related signing projects](docs/ALTERNATIVES.md) for alternatives and differences in deployment.

## License

The project code is AGPL-3.0-only. Bundled dependencies retain their own licenses, including the Microsoft runtime redistribution conditions. See [LICENSE](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md), [security](SECURITY.md), and [release checks](docs/RELEASE_CHECKS.md).
