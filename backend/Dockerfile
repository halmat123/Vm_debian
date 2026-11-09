FROM debian:13-slim AS qemu-builder

ARG QEMU_VERSION=11.0.5
ARG QEMU_SIGNING_KEY=CEACC9E15534EBABB82D3FA03353C9CEF108B584

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bison \
        bzip2 \
        build-essential \
        ca-certificates \
        curl \
        flex \
        gnupg \
        libfdt-dev \
        libglib2.0-dev \
        libpixman-1-dev \
        libslirp-dev \
        libzstd-dev \
        ninja-build \
        pkg-config \
        python3 \
        python3-venv \
        xz-utils \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN curl -fL --retry 3 \
        "https://download.qemu.org/qemu-${QEMU_VERSION}.tar.xz" \
        -o qemu.tar.xz \
    && curl -fL --retry 3 \
        "https://download.qemu.org/qemu-${QEMU_VERSION}.tar.xz.sig" \
        -o qemu.tar.xz.sig \
    && gpg --batch --keyserver hkps://keys.openpgp.org \
        --recv-keys "${QEMU_SIGNING_KEY}" \
    && test "$(gpg --batch --with-colons --fingerprint "${QEMU_SIGNING_KEY}" \
        | awk -F: '$1 == "fpr" { print $10; exit }')" = "${QEMU_SIGNING_KEY}" \
    && gpg --batch --verify qemu.tar.xz.sig qemu.tar.xz \
    && tar -xJf qemu.tar.xz \
    && mkdir qemu-build \
    && cd qemu-build \
    && "../qemu-${QEMU_VERSION}/configure" \
        --prefix=/opt/qemu \
        --target-list=aarch64-softmmu \
        --enable-fdt \
        --enable-slirp \
        --disable-kvm \
        --disable-debug-info \
        --disable-curses \
        --disable-docs \
        --disable-gtk \
        --disable-opengl \
        --disable-sdl \
        --disable-virglrenderer \
        --disable-vnc \
        --disable-werror \
    && make -j"$(nproc)" qemu-system-aarch64 qemu-img \
    && install -Dm0755 qemu-system-aarch64 \
        /opt/qemu/bin/qemu-system-aarch64 \
    && install -Dm0755 qemu-img \
        /opt/qemu/bin/qemu-img \
    && install -d -m0755 /opt/qemu/share/qemu \
    && bzip2 -dc "../qemu-${QEMU_VERSION}/pc-bios/edk2-aarch64-code.fd.bz2" \
        > /opt/qemu/share/qemu/edk2-aarch64-code.fd \
    && bzip2 -dc "../qemu-${QEMU_VERSION}/pc-bios/edk2-arm-vars.fd.bz2" \
        > /opt/qemu/share/qemu/edk2-arm-vars.fd \
    && chmod 0644 /opt/qemu/share/qemu/*.fd

FROM debian:13-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        genisoimage \
        libfdt1 \
        libglib2.0-0t64 \
        libpixman-1-0 \
        libslirp0 \
        libzstd1 \
        openssh-client \
        python3 \
        python3-pip \
        python3-venv \
        zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin vm

COPY --from=qemu-builder /opt/qemu /opt/qemu

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt

RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

COPY backend/ /app/

RUN chmod 0755 /app/entrypoint.sh \
    && mkdir -p /var/lib/yadro-vm /run/yadro-vm \
    && chown -R vm:vm /app /var/lib/yadro-vm /run/yadro-vm

ENV PATH="/opt/venv/bin:/opt/qemu/bin:${PATH}" \
    PYTHONUNBUFFERED=1

USER vm

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
