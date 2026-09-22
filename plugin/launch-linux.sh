#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
case "$(uname -m)" in
    x86_64) architecture=linux-x86_64 ;;
    aarch64|arm64) architecture=linux-aarch64 ;;
    *) printf '%s\n' '{"event":"result","ok":false,"error":"This Linux CPU architecture is not supported by the package."}'; exit 1 ;;
esac
worker="$root/native/$architecture/cac-signer"
if [ ! -f "$worker" ]; then
    printf '%s\n' '{"event":"result","ok":false,"error":"This package does not include a signing runtime for this Linux CPU architecture."}'
    exit 1
fi
# Plugin extraction does not preserve Unix executable permissions in every editor build.
if [ ! -x "$worker" ] && ! chmod u+x -- "$worker"; then
    printf '%s\n' '{"event":"result","ok":false,"error":"The Linux signing runtime is not executable. Check plugin ownership and filesystem execution permissions."}'
    exit 1
fi
reader="$root/native/$architecture/_internal/pcscd"
if [ -f "$reader" ] && [ ! -x "$reader" ] && ! chmod u+x -- "$reader"; then
    printf '%s\n' '{"event":"result","ok":false,"error":"The bundled reader is not executable. Check plugin ownership and filesystem execution permissions."}'
    exit 1
fi
exec "$worker"
