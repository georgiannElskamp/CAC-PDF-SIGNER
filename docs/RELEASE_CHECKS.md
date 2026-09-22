# Release checks

## Automated

```powershell
python -B run_tests.py
node tests/test_background.js
node tests/test_native.js
python -B audit_public.py
```

The tests cover signature integrity, field selection, text sizing and page rotation, bridge framing, message origins, process cleanup, and Save As recovery. Python tests use temporary software signing credentials.

## Manual

- Install the package through Plugin Manager and enable it under Background plugins.
- Sign an empty field with a connected CAC and save the result.
- Confirm that the saved PDF opens and its signature validates.
- Check wide, narrow, shallow and rotated fields for clipping.
- Cancel Save As, then retry and confirm that another card signature is not requested.

## Version 0.5.3

The 19 Python tests and both JavaScript suites pass. The obsolete service implementation and its tests have been removed. Standalone recovery, PDF signing, field selection, text layout and native messaging remain covered. Release checks verify notices, checksums, manifest versions and matching packaged source; the builder checks the native DLL inventory.

Installation, native launch/exit, Save As and reopening were tested on ONLYOFFICE 9.4.0.129 with the 0.5.0 package. Version 0.5.1 added signature-layout tests and rendered samples. A clean second-computer test and fresh hardware-CAC/editor acceptance testing remain outstanding for 0.5.3.
