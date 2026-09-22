# Related signing projects

Reviewed on 2026-09-22 from project documentation and licenses. These projects have not been tested locally with a CAC.

| Project | Similar capabilities | Setup and differences | Project license |
| --- | --- | --- | --- |
| [LibreSign EuroOffice/ONLYOFFICE plugin](https://github.com/LibreSign/eurooffice-plugin) | Sends documents for signature and tracks signing from the editor sidebar. | Requires a Nextcloud/LibreSign environment. Its documented workflow is a signing request/approval process, not local Windows CAC signing by clicking a PDF field. | AGPL-3.0 |
| [JSignPdf](https://github.com/intoolswetrust/jsignpdf) | Visible PDF signatures, smart cards through PKCS#11, timestamping, revocation information and command-line/batch operation. | A separate Java desktop application. Configure the card's PKCS#11 provider; CAC compatibility depends on that provider. It does not supply an ONLYOFFICE plugin. | MPL-2.0 / LGPL-2.1 dual license |
| [192d-Wing/pdf-sign](https://github.com/192d-Wing/pdf-sign) | Explicit PIV/CAC support through Windows CNG, native PIN prompting and PDF signing workflows. | The complete project includes server, desktop and browser components. This plugin already uses its native bridge, but supplies its own PDF-field integration and appearance through pyHanko. | Apache-2.0 |
| [pyHanko](https://github.com/MatthiasValvekens/pyHanko) | PDF signature fields, visible signatures, PKCS#11, timestamping, incremental signatures and validation. | A Python library and CLI. It already supplies this plugin's PDF-signing engine; the editor integration and Windows CNG bridge are additional code. | MIT |
| [PDF QES Signer](https://github.com/pitboc/pdf-qes-signer) | A GUI with signature-field placement/selection, PKCS#11 smart cards, appearance settings and optional timestamping. | Requires Python dependencies and the card's PKCS#11 library. Its documented hardware testing targets Telesec TCOS cards, not DoD CACs. GitHub is a read-only mirror of the Codeberg project. | GPL-3.0-or-later |
| [Stirling PDF](https://github.com/Stirling-Tools/Stirling-PDF) | Desktop certificate signing through the Windows certificate store and PKCS#11. | A separate PDF application. Device-local signing and visible placement have documented limitations; verify the particular release and connection mode. It is not an ONLYOFFICE extension. | MIT core, with separately restricted desktop and other directories |
| [SignBridge](https://github.com/ASE-Bucure-ti/SignBridge) | Browser-to-native PKCS#11 signing with visible/invisible PDF signatures. | Requires a browser extension, native host and integrating web application/backend. Useful for web portals; not a single-file ONLYOFFICE plugin. | MIT at repository root; dependencies retain their licenses |

Stirling PDF's [root license](https://github.com/Stirling-Tools/Stirling-PDF/blob/main/LICENSE) lists exceptions; its [desktop license](https://github.com/Stirling-Tools/Stirling-PDF/blob/main/frontend/editor/src/desktop/LICENSE) restricts production use and redistribution. See its [hardware-token implementation](https://github.com/Stirling-Tools/Stirling-PDF/pull/6765), [remote-server certificate issue](https://github.com/Stirling-Tools/Stirling-PDF/issues/7316), and [visible-placement issue](https://github.com/Stirling-Tools/Stirling-PDF/issues/7261).

## Earlier browser options

[TrueWrit](https://chromewebstore.google.com/detail/truewrit/gelihaceiiafapjajnaafdpjlbjkhnod) advertises CAC/PIV PDF signing for government portals. A matching public source repository and a complete open-source license for its native components were not verified in this review.

[Signer.Digital](https://web.signer.digital/ForDevelopers) provides browser integration and developer libraries. Its extension licensing does not by itself establish the licensing of the complete native/server stack. Neither browser product is a drop-in ONLYOFFICE background plugin.
