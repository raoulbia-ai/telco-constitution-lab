# Track 1 NETCONF surface — sysrepo + Netopeer2, built from source at pinned,
# mutually-compatible release tags. Isolation: the entire NETCONF stack, its
# build deps, and the sysrepo datastore live inside this image — the host OS
# stays pristine (see HANDOVER decision: Docker for OS isolation).
#
# Pinned compatible set (verified against each project's *_DEP_(SO)VERSION):
#   libyang     v5.8.6   (SOVERSION 5.5.5)
#   libnetconf2 v4.4.10  (needs libyang >= 5.3.4)  -> OK
#   sysrepo     v5.1.0   (needs libyang >= 5.4.0)  -> OK
#   netopeer2   v2.8.7   (needs libyang >=5.1.3, libnetconf2 >=5.4.3, sysrepo >=8.5.1) -> OK
#
# Native aarch64 build (DGX Spark / GB10). No arch emulation.

FROM ubuntu:24.04

ARG LIBYANG_TAG=v5.8.6
ARG LIBNETCONF2_TAG=v4.4.10
ARG SYSREPO_TAG=v5.1.0
ARG NETOPEER2_TAG=v2.8.7

ENV DEBIAN_FRONTEND=noninteractive

# Build + runtime dependencies. libssh/libssl for libnetconf2 transport;
# libpcre2 for libyang; libpam/libcurl pulled by libnetconf2 optional features;
# openssh-client provides ssh-keygen used by netopeer2's host-key setup script.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        pkg-config \
        libpcre2-dev \
        libssl-dev \
        libssh-dev \
        libpam0g-dev \
        libcurl4-openssl-dev \
        zlib1g-dev \
        openssh-client \
        ca-certificates \
        bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# 1) libyang
RUN git clone --depth 1 -b ${LIBYANG_TAG} https://github.com/CESNET/libyang.git libyang \
    && cmake -S libyang -B libyang/build \
        -DCMAKE_BUILD_TYPE=Release -DENABLE_TESTS=OFF \
    && cmake --build libyang/build -j"$(nproc)" \
    && cmake --install libyang/build \
    && ldconfig

# 2) libnetconf2
RUN git clone --depth 1 -b ${LIBNETCONF2_TAG} https://github.com/CESNET/libnetconf2.git libnetconf2 \
    && cmake -S libnetconf2 -B libnetconf2/build \
        -DCMAKE_BUILD_TYPE=Release -DENABLE_TESTS=OFF \
    && cmake --build libnetconf2/build -j"$(nproc)" \
    && cmake --install libnetconf2/build \
    && ldconfig

# 3) sysrepo (creates /etc/sysrepo datastore; installs internal YANG modules)
RUN git clone --depth 1 -b ${SYSREPO_TAG} https://github.com/sysrepo/sysrepo.git sysrepo \
    && cmake -S sysrepo -B sysrepo/build \
        -DCMAKE_BUILD_TYPE=Release -DENABLE_TESTS=OFF \
    && cmake --build sysrepo/build -j"$(nproc)" \
    && cmake --install sysrepo/build \
    && ldconfig

# Bake the NETCONF client's public key into root's authorized_keys BEFORE the
# netopeer2 install runs. netopeer2's merge_config.sh configures the server to
# authenticate the installing user (root) via that user's authorized_keys, so
# this gives us deterministic public-key auth with NO PAM dependency.
COPY secrets/netconf_key.pub /root/.ssh/authorized_keys
RUN chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys

# 4) netopeer2 — make install also: installs ietf-netconf* modules, generates
#    the SSH host key, and merges the default listen config (0.0.0.0:830).
RUN git clone --depth 1 -b ${NETOPEER2_TAG} https://github.com/CESNET/netopeer2.git netopeer2 \
    && cmake -S netopeer2 -B netopeer2/build \
        -DCMAKE_BUILD_TYPE=Release \
    && cmake --build netopeer2/build -j"$(nproc)" \
    && cmake --install netopeer2/build \
    && ldconfig

# Install the illustrative Track 1 hardening-knobs YANG model into sysrepo.
COPY yang/telco-hardening.yang /opt/yang/telco-hardening.yang
RUN sysrepoctl -i /opt/yang/telco-hardening.yang -v2

COPY docker/netconf/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 830

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
