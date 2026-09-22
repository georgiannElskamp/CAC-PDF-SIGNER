FROM debian:12@sha256:704583dbf243593da87cf949fc0543ffeca24a28d36c2760dc9545410cb8ed02
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl xz-utils python3 python3-pil build-essential libssl-dev patch \
    libtool automake autoconf pkg-config gnutls-bin openssl xvfb xauth \
    xdotool poppler-utils libgbm1 dbus-x11 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/test-build
RUN curl -fsSLo node.tar.xz https://nodejs.org/dist/v22.23.2/node-v22.23.2-linux-x64.tar.xz \
    && echo 'd60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307  node.tar.xz' | sha256sum -c - \
    && tar -xJf node.tar.xz --strip-components=1 -C /usr/local && rm node.tar.xz
RUN curl -fsSLo source.tar.gz https://deb.debian.org/debian/pool/main/s/softhsm2/softhsm2_2.6.1.orig.tar.gz \
    && echo 'ac9ac1e3f4402f88bf3e626a18f070f8031c031947ed469c6e17482495ec72b6  source.tar.gz' | sha256sum -c - \
    && curl -fsSLo patches.tar.xz https://deb.debian.org/debian/pool/main/s/softhsm2/softhsm2_2.6.1-2.1.debian.tar.xz \
    && echo '221de2ddd2c36c00f589baf2a0901da522f209598caf6ebf0f415012519299da  patches.tar.xz' | sha256sum -c - \
    && tar -xf source.tar.gz && tar -xf patches.tar.xz -C softhsm2-2.6.1
WORKDIR /opt/test-build/softhsm2-2.6.1
RUN while read -r name; do case "$name" in ''|'#'*) continue;; esac; patch -p1 < "debian/patches/$name"; done < debian/patches/series \
    && autoreconf -fi && ./configure --disable-gost --prefix=/opt/softhsm \
    && make -j2 && make install
WORKDIR /opt/test-build/softhsm2-2.6.1/src/lib
# Avoid requiring Debian 12's C++ runtime inside the older bundled worker.
RUN g++ -shared -fPIC -static-libstdc++ -static-libgcc -Wl,--exclude-libs,ALL -Wl,-soname,libsofthsm2.so \
    .libs/access.o .libs/main.o .libs/P11Attributes.o .libs/P11Objects.o .libs/SoftHSM.o \
    -Wl,--whole-archive common/.libs/libsofthsm_common.a crypto/.libs/libsofthsm_crypto.a \
    data_mgr/.libs/libsofthsm_datamgr.a handle_mgr/.libs/libsofthsm_handlemgr.a \
    object_store/.libs/libsofthsm_objectstore.a session_mgr/.libs/libsofthsm_sessionmgr.a \
    slot_mgr/.libs/libsofthsm_slotmgr.a -Wl,--no-whole-archive -lcrypto \
    -o /opt/softhsm/lib/libsofthsm2-test.so
RUN useradd --uid 1000 --home-dir /test/profile --create-home tester && mkdir /evidence && chown tester /evidence
WORKDIR /repo
CMD ["bash", "tests/linux/container-test.sh"]
