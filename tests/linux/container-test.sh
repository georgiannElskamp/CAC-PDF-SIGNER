#!/bin/bash
set -euo pipefail
python3 -B - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, '/repo/tools')
from automation import download, validate_manifest
manifest = validate_manifest(json.loads(Path('/input/editor.json').read_text()))
pin = manifest['linux']
download(f"https://github.com/ONLYOFFICE/DesktopEditors/releases/download/v{manifest['version']}/{pin['file']}",
         Path('/tmp/editor.deb'), pin['sha256'])
PY
apt-get update
apt-get install -y --no-install-recommends /tmp/editor.deb
rm /tmp/editor.deb
if command -v pcscd || command -v opensc-tool; then
    echo 'Unexpected system smart-card middleware'
    exit 1
fi
install -d -m 0700 -o tester /test/state /test/tokens
install -d -o tester '/test/profile/Example User é'
runuser -u tester -- env HOME='/test/profile/Example User é' \
    XDG_RUNTIME_DIR=/test/state CAC_PKCS11_MODULE=/opt/softhsm/lib/libsofthsm2-test.so \
    SOFTHSM2_CONF=/test/state/softhsm.conf \
    dbus-run-session -- xvfb-run -a -s '-screen 0 1280x1024x24' bash tests/linux/signing-session.sh
