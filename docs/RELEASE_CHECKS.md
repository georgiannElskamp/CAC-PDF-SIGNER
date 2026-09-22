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

## Version 0.5.2

The 26 Python tests and both JavaScript suites pass. The standalone package passes dependency, license-checksum and DLL-inventory checks. Missing or altered native dependency notices stop the build. Windows system runtime DLLs are excluded; the Python-supplied Visual C++ runtime is retained with its redistribution conditions.

Installation, native launch/exit, Save As and reopening were tested on ONLYOFFICE 9.4.0.129 with the 0.5.0 package. Version 0.5.1 added signature-layout tests and rendered samples. Hardware-CAC and editor acceptance testing remain outstanding for 0.5.2.
