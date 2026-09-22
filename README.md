# ONLYOFFICE CAC Signature Plugin

Sign PDF signature fields with a Common Access Card in ONLYOFFICE Desktop Editors. The plugin runs in the background and includes its own signing runtime.

## Requirements

- Windows 10 or later, x64, and ONLYOFFICE Desktop Editors 9.4.0.129.
- A CAC reader, Windows card middleware, and one eligible document-signing certificate on the connected card.
- A plugin installation path without spaces. PDF filenames and save locations may contain spaces.

## Install

1. Open **Plugins > Plugin Manager > Available plugins > Install plugin manually**.
2. Select **CAC-PDF-Signer.plugin**.
3. Enable **CAC PDF Signer** under **Plugins > Background plugins**.

After an update, reopen the PDF or toggle the background plugin off and on.

## Sign a PDF

Save and reopen the PDF, then click an empty signature field. Enter your PIN if Windows prompts for it. Choose a location in **Save signed PDF as**; the signed copy opens in ONLYOFFICE.

The signature displays your certificate name, signing time, and rank and DoD ID when available. Text wraps and scales to the field dimensions. Tall fields place the name above the signing details.

If you cancel Save As, click the same field again to save the completed signature. Recovery copies are stored in `%LOCALAPPDATA%\ONLYOFFICE-CAC-Signature\Signed` and remain after uninstalling the plugin.

## Limitations

- Requires an existing PDF signature field; drawn rectangles and typed signature lines are unsupported.
- Save and reopen edited PDFs before signing. The editor can retain an earlier version of the document in memory.
- Encrypted PDFs, files over 40 MB, hidden or ambiguous fields, and multiple eligible signing certificates are unsupported.
- Signature text uses Helvetica's Western character set.
- Verification checks signature integrity. Certificate trust, revocation and trusted timestamping are outside its scope; signing time uses the local clock.
- The plugin depends on ONLYOFFICE internals. Other editor versions may need an adapter update.

## Build and test

See [build instructions and architecture](docs/STANDALONE_ARCHITECTURE.md). Use `build_standalone.py` to create the installable `.plugin` file.

For development, install `requirements-dev.txt` in a virtual environment outside the checkout, then run:

```powershell
python -B run_tests.py
node tests/test_background.js
node tests/test_native.js
python -B audit_public.py
```

## License

The project code is AGPL-3.0-only. Bundled dependencies retain their own licenses, including the Microsoft runtime redistribution conditions. See [LICENSE](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md), [security](SECURITY.md), and [release checks](docs/RELEASE_CHECKS.md).
