#!/bin/sh
# Build in an isolated Linux environment with the oldest supported glibc.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
prefix=${CAC_NATIVE_PREFIX:-/opt/native}
sources=${CAC_NATIVE_SOURCES:-/opt/src}
work=${CAC_NATIVE_WORK:-/opt/middleware-build}
jobs=${CAC_BUILD_JOBS:-4}
export PATH="/opt/venv/bin:$PATH"
export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
export LD_LIBRARY_PATH="$prefix/lib"
export CFLAGS="-O2 -fPIC -ffile-prefix-map=$work=/build"
export CPPFLAGS="-I$prefix/include"
export LDFLAGS="-L$prefix/lib"
mkdir -p "$work" "$prefix"
python - "$script_dir/sources.json" "$sources" "$work" <<'PY'
import hashlib, json, pathlib, sys, tarfile
manifest, sources, work = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
for item in json.loads(manifest.read_text()):
    archive = sources / item['file']
    if hashlib.sha256(archive.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError('Source checksum mismatch: ' + item['file'])
    with tarfile.open(archive) as source:
        source.extractall(work, filter='data')
PY
cd "$work/libusb-1.0.30"
./configure --prefix="$prefix" --libdir="$prefix/lib" --disable-udev --disable-static
make -j "$jobs"
make install
cd "$work/zlib-1.3.2"
./configure --prefix="$prefix" --libdir="$prefix/lib"
make -j "$jobs"
make install
cd "$work/openssl-3.5.8"
[ ! -f Makefile ] || make clean
./Configure --prefix="$prefix" --libdir=lib shared no-tests no-asm
make -j "$jobs"
make install_sw
python "$script_dir/private_pcsc.py" "$work/pcsc-lite-2.5.2"
meson setup "$work/pcsc-build" "$work/pcsc-lite-2.5.2" --prefix="$prefix" --libdir=lib --buildtype=release -Dlibsystemd=false -Dlibudev=false -Dlibusb=true -Dpolkit=false -Dserial=false -Dusb=true -Dusbdropdir="$prefix/lib/pcsc/drivers"
meson compile -C "$work/pcsc-build" -j "$jobs"
meson install -C "$work/pcsc-build"
meson setup "$work/ccid-build" "$work/ccid-1.8.4" --prefix="$prefix" --libdir=lib --buildtype=release -Dudev-rules=false -Dserial=false -Denable-extras=false
meson compile -C "$work/ccid-build" -j "$jobs"
meson install -C "$work/ccid-build"
cd "$work/opensc-0.27.1"
./configure --prefix="$prefix" --libdir="$prefix/lib" --disable-static --disable-readline --disable-notify --disable-tests --disable-integration-tests --disable-doc --enable-openssl --enable-zlib --with-pcsc-provider=libpcsclite.so.1
make -j "$jobs"
make install
printf '%s\n' 'Linux smart-card components built.'
