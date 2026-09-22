FROM debian:10@sha256:2a0c1b9175adf759420fe0fbd7f5b449038319171eb76554bb76cbe172b62b42
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1
RUN printf 'deb http://archive.debian.org/debian buster main\ndeb http://archive.debian.org/debian-security buster/updates main\n' > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/* \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends ca-certificates curl jq xz-utils \
       build-essential flex autoconf automake libtool pkg-config perl binutils patchelf \
    && rm -rf /var/lib/apt/lists/*
COPY native_linux/runtime.json native_linux/sources.json /opt/pins/
RUN curl -fL --retry 2 "$(jq -r .python.url /opt/pins/runtime.json)" -o /opt/python.tar.gz \
    && printf '%s  /opt/python.tar.gz\n' "$(jq -r .python.sha256 /opt/pins/runtime.json)" | sha256sum -c - \
    && tar -xf /opt/python.tar.gz -C /opt && rm /opt/python.tar.gz \
    && /opt/python/bin/python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:/opt/python/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
COPY requirements-lock.txt requirements-linux.txt requirements-build.txt /opt/requirements/
RUN python -m pip install -r /opt/requirements/requirements-build.txt -r /opt/requirements/requirements-linux.txt \
    meson==1.9.2 ninja==1.13.0 setuptools==80.9.0
RUN mkdir /opt/src && jq -r '.[] | [.url,.file,.sha256] | @tsv' /opt/pins/sources.json | \
    while read -r url name digest; do \
      curl -fL --retry 2 "$url" -o "/opt/src/$name"; \
      printf '%s  %s\n' "$digest" "/opt/src/$name" | sha256sum -c - || exit 1; \
    done
COPY . /repo
WORKDIR /repo
RUN sh native_linux/build_middleware.sh
RUN python -B tools/build_linux.py --output /opt/linux-bundle --prefix /opt/native --sources /opt/src --work /opt/freeze-work
CMD ["tar", "-cf", "/output/linux-bundle.tar", "-C", "/opt/linux-bundle", "."]
