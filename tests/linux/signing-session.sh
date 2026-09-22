#!/bin/bash
set -euo pipefail
export XDG_DATA_HOME="$HOME/.local/share" XDG_CONFIG_HOME="$HOME/.config" XDG_CACHE_HOME="$HOME/.cache"
export QT_QPA_PLATFORM=xcb GDK_BACKEND=x11
mkdir -p "$HOME/Documents"
cleanup() {
    [[ -z ${editor_pid:-} ]] || kill "$editor_pid" 2>/dev/null || true
    rm -rf /test/tokens /test/state/*
}
trap cleanup EXIT
printf 'directories.tokendir = /test/tokens\nobjectstore.backend = file\nlog.level = ERROR\n' > "$SOFTHSM2_CONF"
/opt/softhsm/bin/softhsm2-util --init-token --free --label CAC-Test --so-pin 87654321 --pin 123456
openssl req -x509 -newkey rsa:2048 -nodes -days 2 \
    -subj '/C=US/O=DisposablePluginTest/OU=DoD/CN=EXAMPLE.TEST.0000000000/title=TEST ONLY' \
    -addext 'keyUsage=critical,digitalSignature,nonRepudiation' -addext 'basicConstraints=critical,CA:FALSE' \
    -keyout /test/state/key.pem -out /test/state/cert.pem 2>/dev/null
/opt/softhsm/bin/softhsm2-util --import /test/state/key.pem --token CAC-Test --id 01 --label CAC-Test --pin 123456
p11tool --provider="$CAC_PKCS11_MODULE" --login --set-pin=123456 --write --load-certificate=/test/state/cert.pem \
    --id=01 --label=CAC-Test 'pkcs11:token=CAC-Test'
rm /test/state/key.pem /test/state/cert.pem
node tests/editor_smoke.js --fixture "$HOME/Documents/installation-test.pdf"
launcher=$(command -v onlyoffice-desktopeditors || command -v desktopeditors)
"$launcher" --remote-debugging-port=9251 "$HOME/Documents/installation-test.pdf" > /test/state/editor.log 2>&1 &
editor_pid=$!
node tests/linux/signing.js
