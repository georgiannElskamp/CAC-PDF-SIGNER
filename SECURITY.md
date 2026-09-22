# Security

Windows and the card provider handle PIN entry and private-key operations. The plugin receives the resulting signature through the Windows CNG bridge.

The background and native frames validate message sources and origins. The native host launches a fixed bundled executable and exchanges document data over standard input/output. The signer handles one operation and exits; it does not expose a network listener.

Signed documents contain the signing certificate and visible identity details. Recovery PDFs and records are stored under `%LOCALAPPDATA%\ONLYOFFICE-CAC-Signature\Signed` and survive uninstallation. Treat these files as confidential documents.

Signature verification checks integrity, not certificate trust or revocation. Signing time comes from the local clock. The plugin assumes the local Windows account and editor installation are trusted.

## Reporting issues

Use a sample PDF and redact paths and identity details from error reports. Report vulnerabilities through GitHub private security reporting when available, or ask a maintainer for a private channel.

## Release checks

Run `python -B audit_public.py` before publishing. It checks source files and, when present, the release checksum and packaged source. Git history and compiled archives require separate inspection.
