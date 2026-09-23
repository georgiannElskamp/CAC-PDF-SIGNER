#!/bin/bash
set -euo pipefail
export XDG_DATA_HOME="$HOME/.local/share" XDG_CONFIG_HOME="$HOME/.config" XDG_CACHE_HOME="$HOME/.cache"
export QT_QPA_PLATFORM=xcb GDK_BACKEND=x11
unset CAC_PKCS11_MODULE
printf 'directories.tokendir = /test/tokens\nobjectstore.backend = file\nslots.removable = true\nlog.level = ERROR\n' > "$SOFTHSM2_CONF"
provider=/usr/lib/softhsm/libsofthsm2.so
[[ -f "$provider" ]] || provider=/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so
softhsm2-util --init-token --free --label 'SC test' --so-pin 77777777 --pin 12345678
for id in 01 02 03; do
    case "$id" in
      01) label=RSA_id; usage=digitalSignature;;
      02) label=RSA_sign; usage=digitalSignature,nonRepudiation;;
      03) label=RSA_encryption; usage=keyEncipherment;;
    esac
    openssl req -x509 -newkey rsa:2048 -nodes -days 2 \
        -subj '/C=US/O=DisposablePluginTest/OU=DoD/CN=EXAMPLE.TEST.0000000000/title=TEST ONLY' \
        -addext "keyUsage=critical,$usage" -addext 'basicConstraints=critical,CA:FALSE' \
        -keyout /test/state/key.pem -out /test/state/cert.pem 2>/dev/null
    softhsm2-util --import /test/state/key.pem --token 'SC test' --id "$id" --label "$label" --pin 12345678
    openssl x509 -in /test/state/cert.pem -outform DER -out /test/state/cert.der
    pkcs11-tool --module "$provider" --login --pin 12345678 --token-label 'SC test' \
        --write-object /test/state/cert.der --type cert --id "$id" --label "$label"
done
rm /test/state/key.pem /test/state/cert.pem /test/state/cert.der
mkdir /test/state/db
modutil -create -dbdir sql:/test/state/db -force
modutil -add 'SoftHSM PKCS11' -dbdir sql:/test/state/db -libfile "$provider" -force
cd /test/state
virt_cacard > virtual-card.txt 2>&1 &
card_pid=$!
trap 'kill "$card_pid" 2>/dev/null || true' EXIT
export PROBE_CARD_PID="$card_pid"
sleep 2
pkcs11-tool --list-objects --type cert > control.txt
cd /repo
python3 -B tests/feasibility/virtual_probe.py
