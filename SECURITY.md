# Security

Windows and the card provider handle PIN entry and private-key operations. The plugin receives the resulting signature through the Windows CNG bridge or CryptoAPI for legacy CSP keys.

Linux uses OpenSC through PKCS#11. A native masked dialog collects the PIN when the reader does not provide a protected PIN entry path. The PIN is passed to the token session and is not written to settings, logs or recovery records. A rejected PIN is not retried automatically. The card performs the private-key operation.

The background and native frames validate message sources and origins. The native host launches a fixed bundled executable and exchanges document data over standard input/output. The signer handles one operation and exits; it does not expose a network listener. A Linux reader subprocess, when needed, uses a private local socket and exits with the operation.

Signed documents contain the signing certificate and visible identity details. Recovery PDFs and records are stored under `%LOCALAPPDATA%\ONLYOFFICE-CAC-Signature\Signed` and survive uninstallation. Treat these files as confidential documents.

For an ONLYOFFICE form, the first click creates an unsigned review PDF and a hash-bound handoff record under `Prepared` in the same application-data directory. They may contain confidential document content and the original file path. The worker removes entries older than 30 days during a later form preparation; uninstalling does not remove them. The card is accessed only after the review PDF's signature field is clicked.

Linux recovery files use the user's XDG data directory with private file permissions. Signing requires reader permissions granted by the operating system; the plugin does not elevate privileges.

Signature verification checks integrity, not certificate trust or revocation. Signing time comes from the local clock. The plugin assumes the local account and editor installation are trusted.

## Reporting issues

Use a sample PDF and redact paths and identity details from error reports. Report vulnerabilities through GitHub private security reporting when available, or ask a maintainer for a private channel.

Supported platforms and outstanding hardware checks are recorded in [TESTING.md](docs/TESTING.md). Other ONLYOFFICE versions and sandboxed installations are not assumed compatible.

## Release checks

Run `python -B tools/audit_public.py` before publishing. It checks source files and, when present, the release checksum, native manifests and packaged source. Git history and compiled archives require separate inspection. The release workflow also executes both bundled workers and tests installation in disposable editors.
