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

## Version 0.5.1

The 22 Python tests and both JavaScript suites pass. Rendered sample signatures cover wide, shallow, square, tall and long-name fields. The standalone package passes dependency, manifest and archive checks.

Installation, native launch/exit, Save As and reopening were tested on ONLYOFFICE 9.4.0.129 with the 0.5.0 package. Hardware-CAC acceptance testing remains outstanding for 0.5.1.
