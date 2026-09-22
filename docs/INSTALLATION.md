# Install and sign

Download **CAC-PDF-Signer.plugin** from the [0.7.0-rc.6 release](https://github.com/georgiannElskamp/CAC-PDF-SIGNER/releases/tag/v0.7.0-rc.6). GitHub's source ZIP is for development and cannot be installed as a plugin. The `.plugin` file contains both signing runtimes; it needs no separate Python installation or persistent signing service.

## Requirements

| Component | Requirement |
| --- | --- |
| Editor | ONLYOFFICE Desktop Editors 9.4.0.129 |
| Windows | Windows 10 or later, x64; a working CNG or legacy CSP smart-card provider |
| Linux | x86_64, glibc 2.28 or later, GTK 3, a desktop display, and reader access |
| Card | Connected CAC with one eligible RSA document-signing certificate |
| Installation | Permission to run executables from the plugin directory and write recovery files |

The Linux plugin includes OpenSC, PC/SC and a USB CCID driver. It reuses an available system PC/SC service, or starts its own reader process for the signing operation. It does not install a service, elevate privileges or change USB permissions. WSL requires the reader to be attached to Linux.

ARM64, musl-based Linux, macOS, the web editor, Flatpak and Snap are outside this package's supported scope. RPM and AppImage installation are untested. Windows application-control policies may block the unsigned worker. See the [validation matrix](TESTING.md) for tested configurations and outstanding hardware checks.

## Install or update

1. If an older version is running, turn it off under **Plugins > Background plugins**.
2. Open **Plugins > Plugin Manager > Install plugin manually**. Depending on the editor, this appears under **My plugins** or **Available plugins**.
3. Select **CAC-PDF-Signer.plugin**.
4. Reopen the PDF and enable **CAC PDF Signer** under **Background plugins**.

Startup checks desktop availability and recovery storage without accessing the card. Successful startup opens no plugin window.

Keep Windows plugin installation paths below 260 characters. Spaces, Unicode and literal percent signs are supported; network-hosted installations remain untested.

## Sign

Save and reopen the PDF, then click an empty signature field. Enter the CAC PIN when prompted and choose a location in **Save signed PDF as**. The signed copy opens in ONLYOFFICE.

The visible signature displays the certificate name, signing time, and rank and DoD ID when available. Text wraps and scales to the field dimensions. The card performs the private-key operation.

If Save As is cancelled, click the same field again to save the completed signature without signing again. Recovery copies remain in:

- Windows: `%LOCALAPPDATA%\ONLYOFFICE-CAC-Signature\Signed`
- Linux: `$XDG_DATA_HOME/ONLYOFFICE-CAC-Signature/Signed`, or `~/.local/share/ONLYOFFICE-CAC-Signature/Signed`

These files contain signed documents and identity details. Uninstalling the plugin does not remove them.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Plugin is missing from Background plugins | Confirm the editor version, install the `.plugin` file rather than the source ZIP, then reopen the PDF. |
| Editor adapter update required | The installed editor differs from the tested PDF interface. Signing stops until an adapter is available. |
| Worker is blocked or not executable | Check application-control rules, plugin ownership and filesystem execution permissions. |
| Linux desktop unavailable | GTK 3 and a usable display must be accessible to the editor and its child processes. |
| Reader or certificate unavailable | Confirm the reader is connected and accessible to this OS account. Windows needs its card provider; Linux needs USB or system PC/SC access. |
| Recovery folder cannot be written | Check permissions and free space before retrying. |
| PDF must be reopened | Save changes and close/reopen the PDF so the editor loads the saved bytes. |

The plugin requires an existing PDF signature field. It rejects encrypted PDFs, files over 40 MB, hidden or ambiguous fields, multiple eligible certificates and unsupported certificate-name characters. Bundled fonts cover additional Latin, Greek, Cyrillic and CJK text; other scripts and right-to-left layout are unvalidated.

Verification checks signature integrity. Certificate trust, revocation and trusted timestamping are outside its scope; signing time uses the local clock.

## Uninstall

Disable **CAC PDF Signer** under **Background plugins**, then remove it in Plugin Manager and close the PDF. Removing plugin files alone can leave a running instance active until the document closes.
