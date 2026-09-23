# CAC PDF Signer for ONLYOFFICE

Sign existing PDF signature fields with a Common Access Card in ONLYOFFICE Desktop Editors. The background plugin fills the signature block with certificate details, scales the text to fit, and opens Save As.

**[Download the approved release](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/releases/latest)** · [Installation](docs/INSTALLATION.md) · [Validation status](docs/TESTING.md)

The physical-card validation baseline is `0.7.0-rc.6`, tested on two additional Windows installations. Fresh Debian 12 validation used a simulated card. Subsequent releases link their automated evidence and require maintainer approval. Physical CAC signing on Linux remains unverified.

## Compatibility

| Platform | Requirements |
| --- | --- |
| Editor | ONLYOFFICE Desktop Editors 9.4.0.129 |
| Windows | Windows 10 or later, x64, working CNG or legacy CSP smart-card provider |
| Linux | x86_64, glibc 2.28+, GTK 3, desktop display and permission to access the reader |

ARM64, musl-based Linux, macOS, the web editor, Flatpak and Snap are outside the supported package. Other editor versions require adapter validation. See [installation requirements](docs/INSTALLATION.md#requirements) for details.

## Install and use

1. Download **CAC-PDF-Signer.plugin** from the release assets. The source ZIP is not an installable plugin.
2. In ONLYOFFICE, open **Plugins > Plugin Manager > Install plugin manually** and select the file.
3. Enable **CAC PDF Signer** under **Plugins > Background plugins**.
4. Save and reopen the PDF, click an empty signature field, enter the CAC PIN and save the signed copy.

One `.plugin` file contains both signing runtimes. No separate Python installation or persistent signing service is required. Startup checks desktop availability and recovery storage before enabling signature clicks.

Turn the background plugin off before updating or removing it; reopen the PDF after updating. If Save As is cancelled, clicking the same field retries saving the completed signature. See [installation and troubleshooting](docs/INSTALLATION.md).

## Scope

- Uses existing PDF signature fields; drawn rectangles and typed signature lines are unsupported.
- Displays the certificate name, signing time, and rank and DoD ID when available. Text wraps and scales to the field.
- Rejects encrypted PDFs, files over 40 MB, ambiguous fields and multiple eligible signing certificates.
- Checks signature integrity. Certificate trust, revocation and trusted timestamping are outside its scope.
- Leaves recovery copies in the user's application-data directory after uninstalling. Treat them as confidential documents.

## Development

Changes flow through `research`, a frozen `release-verification` candidate, and maintainer-approved `main`. Only main publishes a GitHub release. See the [maintenance guide](docs/AUTOMATION.md).

The signing modules stay at the root; editor integration is in `plugin/`, build and release commands in `tools/`, and checks in `tests/`. Generated release assets are excluded from Git. The package includes the corresponding source and dependency notices.

- [Architecture and repository layout](docs/ARCHITECTURE.md)
- [Build and release instructions](docs/BUILDING.md)
- [Tests and compatibility matrix](docs/TESTING.md)
- [GitHub maintenance and hosted builds](docs/AUTOMATION.md)
- [Release notes](docs/RELEASE_NOTES.md)
- [Security](SECURITY.md)

## License

Project code is [AGPL-3.0-only](LICENSE). Dependencies retain their own terms, including the Microsoft runtime redistribution conditions. [Third-party notices](THIRD_PARTY_NOTICES.md) identify their sources and licenses. Required notices in `licenses/` and `fonts/` are part of the distribution.
