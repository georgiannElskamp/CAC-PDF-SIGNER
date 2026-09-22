# Security

Windows and the card provider handle PIN entry and private-key operations. The plugin receives the resulting signature through the Windows CNG bridge.

Linux uses OpenSC through PKCS#11. A native masked dialog collects the PIN when the reader does not provide a protected PIN entry path. The PIN is passed to the token session and is not written to settings, logs or recovery records. A rejected PIN is not retried automatically. The card performs the private-key operation.

The background and native frames validate message sources and origins. The native host launches a fixed bundled executable and exchanges document data over standard input/output. The signer handles one operation and exits; it does not expose a network listener. A Linux reader subprocess, when needed, uses a private local socket and exits with the operation.

Signed documents contain the signing certificate and visible identity details. Recovery PDFs and records are stored under `%LOCALAPPDATA%\ONLYOFFICE-CAC-Signature\Signed` and survive uninstallation. Treat these files as confidential documents.

Linux recovery files use the user's XDG data directory with private file permissions. Signing requires reader permissions granted by the operating system; the plugin does not elevate privileges.

Signature verification checks integrity, not certificate trust or revocation. Signing time comes from the local clock. The plugin assumes the local account and editor installation are trusted.

## Reporting issues

Use a sample PDF and redact paths and identity details from error reports. Report vulnerabilities through GitHub private security reporting when available, or ask a maintainer for a private channel.

## Release checks

Run `python -B audit_public.py` before publishing. It checks source files and, when present, the release checksum and packaged source. Git history and compiled archives require separate inspection.
