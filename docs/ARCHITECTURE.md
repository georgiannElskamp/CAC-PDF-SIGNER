# Architecture

The `.plugin` archive contains the background JavaScript, Windows and Linux workers, project source and dependency notices. Each worker includes Python and its dependencies in the installation directory. Native libraries are not extracted into temporary storage at launch.

## Signing flow

1. The background script checks the editor adapter and runs desktop and recovery-storage preflight before attaching to PDF signature fields.
2. A hidden `onlyoffice:` frame launches the worker through ONLYOFFICE's `ExternalProcess` API. Windows uses `native/cac-signer.exe`; Linux uses `launch-linux.sh` and `native/linux-x86_64/cac-signer`.
3. The frames validate message origins. Standard PDF signature fields send PDF bytes and the field name to the worker. A saved ONLYOFFICE form sends its local path and form key. At startup, the worker hashes that file; before accessing the card, it rejects a changed hash. The worker returns JSON events over standard output.
4. Windows signs through the CNG bridge or CryptoAPI for legacy CSP keys. Linux uses python-pkcs11 and OpenSC. A Windows mutex or Linux file lock serializes signing and Save As across editor tabs.
5. The worker verifies the signed PDF, writes a recovery copy and opens a native Save As dialog. Cancelling preserves the completed signature for a later save attempt.
6. The plugin acknowledges the result before the worker exits, avoiding the editor's process-output shutdown race. The acknowledgment wait is limited to ten seconds. After saving, the plugin opens the result through the editor's native file opener.

ONLYOFFICE PDF form signature boxes export as image buttons rather than PDF `/Sig` fields. In Preview mode, the adapter recognizes the selected form control and intercepts its image-signature dialog. The worker copies the standard PDF objects, converts that button into a `/Sig` field at the same rectangle, and signs the resulting PDF. This removes the embedded editable form package from the signed copy. Existing signed forms are rejected because copying them would invalidate their signatures.

Desktop Editors 9.4 does not provide a working plugin API for exporting the currently displayed form PDF. The startup hash detects later disk changes, but cannot exclude a change between the editor's file load and the hash capture. Form support remains a research feature until that boundary can be verified.

## Platform integration

The PDF-field adapter and process interface depend on ONLYOFFICE internals and are validated against Desktop Editors 9.4.0.129. An incompatible adapter fails before signing. PDF documents can report `editorType: word` with `editorSubType: pdf`; the manifest and startup guard account for both.

This editor version splits Windows executable paths at the first space. The launcher uses the built-in `cmd.exe` with tab-separated arguments, quoted paths, and disabled AutoRun and delayed expansion. Existing short-name aliases reduce executable and temporary paths when available. The editor's own loader still limits long plugin paths.

Linux launches `/bin/sh` with a path argument parsed by the editor, without evaluating that path as shell code. The launcher adds execute permission only when needed. A bundled PC/SC process uses a short private socket path when no system service is available, and stops after the operation. Reader access remains subject to OS permissions.

The installation filesystem must permit execution; temporary storage need not. The Windows worker is unsigned. The OS supplies Windows system libraries or Linux glibc and GTK 3.

## Source layout

| Location | Contents |
| --- | --- |
| Root Python modules | Signing, certificate selection, appearance, dialogs and recovery |
| `plugin/` | ONLYOFFICE background integration and native transport |
| `native_linux/` | Pinned middleware sources, build script and private PC/SC adaptation |
| `fonts/` | Signature fonts, checksums and upstream font licenses |
| `tools/` | Build, audit, test and release commands |
| `tests/` | Regression suites and disposable-editor installation checks |
| `docs/` | Installation, builds, validation and release notes |
| `licenses/` | Unmodified dependency notices and provenance |
| `release/` | Local generated assets; excluded from Git and bundled source |

See [build instructions](BUILDING.md), [security](../SECURITY.md) and [third-party notices](../THIRD_PARTY_NOTICES.md).
