FROM debian:12@sha256:704583dbf243593da87cf949fc0543ffeca24a28d36c2760dc9545410cb8ed02
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git gcc make autoconf automake libtool pkg-config libcacard-dev \
    libpcsclite-dev libglib2.0-dev softhsm2 opensc pcscd vsmartcard-vpcd libnss3-tools \
    openssl python3 python3-pil xvfb xauth xdotool poppler-utils libgtk-3-0 dbus-x11 \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/Jakuje/virt_cacard.git /opt/virt-source \
    && cd /opt/virt-source && git checkout bbb49bc1ae17f5fd6328f0bd1ad196a12fde841c \
    && ./autogen.sh && ./configure && make -j2 && make install
RUN useradd --uid 1000 --home-dir /test/profile --create-home tester
WORKDIR /repo
CMD ["bash","tests/feasibility/virtual_start.sh"]
