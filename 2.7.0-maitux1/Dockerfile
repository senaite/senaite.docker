# Use an official Python runtime as a parent image
FROM python:2.7-slim-buster

ARG HTTP_PROXY=http://host.docker.internal:7897
ARG HTTPS_PROXY=http://host.docker.internal:7897
ARG NO_PROXY=127.0.0.1,localhost,::1,host.docker.internal

# Set one or more individual labels
LABEL maintainer="Ramon Bartl"
LABEL email="rb@ridingbytes.com"
LABEL senaite.core.version="latest"

# Set environment variables
ENV PLONE_MAJOR=5.2 \
    PLONE_VERSION=5.2.15 \
    PLONE_MD5=714be71e21098ab148df8681196e78ce \
    PLONE_UNIFIED_INSTALLER=Plone-5.2.15-UnifiedInstaller-1.0 \
    PLONE_UNIFIED_INSTALLER_COMMIT=1f925681de91391ab4197871f78adbdd01c3b194 \
    SENAITE_HOME=/home/senaite \
    SENAITE_USER=senaite \
    SENAITE_INSTANCE_HOME=/home/senaite/senaitelims \
    SENAITE_DATA=/data \
    SENAITE_FILESTORAGE=/data/filestorage \
    SENAITE_BLOBSTORAGE=/data/blobstorage \
    WHEELHOUSE=/home/senaite/wheelhouse \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
    PIP_FIND_LINKS=/home/senaite/wheelhouse \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8 \
    PYTHONIOENCODING=utf-8 \
    DEBIAN_FRONTEND=noninteractive \
    HTTP_PROXY=$HTTP_PROXY \
    HTTPS_PROXY=$HTTPS_PROXY \
    NO_PROXY=$NO_PROXY \
    http_proxy=$HTTP_PROXY \
    https_proxy=$HTTPS_PROXY \
    no_proxy=$NO_PROXY

# Create the senaite user
RUN useradd --system -m -d $SENAITE_HOME -U -u 500 $SENAITE_USER

# Create directories
RUN mkdir -p $SENAITE_INSTANCE_HOME $SENAITE_FILESTORAGE $SENAITE_BLOBSTORAGE

# Copy Buildout
COPY requirements.txt buildout.cfg common-addons.cfg versions.cfg zope-versions.cfg zope-versions-prod.cfg $SENAITE_INSTANCE_HOME/
RUN touch $SENAITE_INSTANCE_HOME/custom-addon.cfg

# Copy the build dependencies and startup scripts
COPY build_deps.txt run_deps.txt docker-initialize.py docker-entrypoint.sh /

# Copy the local translation overrides from the build context
COPY senaite.impress.po senaite.impress.mo /tmp/install-lc-messages/

# Copy local common addons from the build context
COPY addons/common /opt/addons/common
RUN mkdir -p /opt/addons/customers

RUN set -eux; \
    sed -i 's/\r$//' /docker-entrypoint.sh /docker-initialize.py /build_deps.txt /run_deps.txt; \
    chmod +x /docker-entrypoint.sh

RUN set -eux; \
    echo "Acquire::Check-Valid-Until \"false\";" > /etc/apt/apt.conf.d/99no-check-valid-until; \
    echo "Acquire::Retries \"5\";" > /etc/apt/apt.conf.d/80retries; \
    printf '%s\n' \
      'deb http://snapshot.debian.org/archive/debian/20240311T000000Z/ buster main contrib non-free' \
      'deb http://snapshot.debian.org/archive/debian-security/20240311T000000Z/ buster/updates main contrib non-free' \
      > /etc/apt/sources.list; \
    retry_update() { \
      for attempt in 1 2 3 4 5; do \
        apt-get update && return 0; \
        sleep 5; \
      done; \
      return 1; \
    }; \
    retry_update; \
    retry_install() { \
      for attempt in 1 2 3 4 5; do \
        apt-get install -y --fix-missing --no-install-recommends "$@" && return 0; \
        sleep 5; \
      done; \
      return 1; \
    }; \
    build_deps="$(sed 's/\r$//' /build_deps.txt | grep -vE '^[[:space:]]*($|#)' | xargs)"; \
    run_deps="$(sed 's/\r$//' /run_deps.txt | grep -vE '^[[:space:]]*($|#)' | xargs)"; \
    set -- $build_deps; \
    retry_install "$@"; \
    set -- $run_deps; \
    retry_install "$@"; \
    echo 'zh_CN.UTF-8 UTF-8' > /etc/locale.gen; \
    locale-gen zh_CN.UTF-8; \
    update-locale LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8

RUN set -eux; \
    installer_url="https://github.com/plone/Installers-UnifiedInstaller/archive/$PLONE_UNIFIED_INSTALLER_COMMIT.tar.gz"; \
    mkdir -p /tmp/plone-installer; \
    wget -O /Plone.tgz --tries=5 --timeout=120 "$installer_url"; \
    tar -xzf /Plone.tgz -C /tmp/plone-installer --strip-components=1; \
    cp -rv /tmp/plone-installer/base_skeleton/* $SENAITE_INSTANCE_HOME; \
    cp -v /tmp/plone-installer/buildout_templates/buildout.cfg $SENAITE_INSTANCE_HOME/buildout-base.cfg; \
    sed -i 's|https://dist.plone.org/release/5.2.15/versions.cfg|versions.cfg|g' $SENAITE_INSTANCE_HOME/buildout-base.cfg; \
    rm -rf /tmp/plone-installer /Plone.tgz

ARG CACHEBUST=1
ARG UPDATED_PACKAGES=
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/cache/buildout-downloads \
    --mount=type=cache,target=/cache/eggs \
    --mount=type=cache,target=/cache/wheelhouse \
    set -eux; \
    cd $SENAITE_INSTANCE_HOME; \
    git --version; \
    git config --global http.version HTTP/1.1; \
    git config --global http.proxy "$HTTP_PROXY"; \
    git config --global https.proxy "$HTTPS_PROXY"; \
    git config --global http.https://github.com.proxy ""; \
    git config --global --list || true; \
    env | sort | grep '^GIT_' || true; \
    env | sort | grep -Ei '^(HTTP|HTTPS|NO)_PROXY=|^(http|https|no)_proxy=' || true; \
    pip --version; \
    python -c "import setuptools; print(setuptools.__version__)"; \
    mkdir -p /cache/buildout-downloads /cache/eggs /cache/wheelhouse; \
    mkdir -p $SENAITE_HOME/buildout-cache/downloads; \
    mkdir -p $SENAITE_INSTANCE_HOME/eggs; \
    mkdir -p $WHEELHOUSE; \
    cp -a /cache/buildout-downloads/. $SENAITE_HOME/buildout-cache/downloads/ || true; \
    cp -a /cache/eggs/. $SENAITE_INSTANCE_HOME/eggs/ || true; \
    cp -a /cache/wheelhouse/. $WHEELHOUSE/ || true; \
    retry_cmd() { for attempt in 1 2 3; do "$@" && return 0; sleep 5; done; return 1; }; \
    fallback_pip_index=https://pypi.org/simple; \
    pip_download_with_fallback() { \
      if ! retry_cmd pip download --dest "$WHEELHOUSE" --index-url "$PIP_INDEX_URL" "$@"; then \
        retry_cmd pip download --dest "$WHEELHOUSE" --index-url "$fallback_pip_index" "$@"; \
      fi; \
    }; \
    pip_install_with_fallback() { \
      if ! retry_cmd pip install --find-links "$WHEELHOUSE" --index-url "$PIP_INDEX_URL" "$@"; then \
        retry_cmd pip install --find-links "$WHEELHOUSE" --index-url "$fallback_pip_index" "$@"; \
      fi; \
    }; \
    pip_download_with_fallback -r requirements.txt argparse==1.4.0 zope.component==4.6.2 collective.recipe.plonesite Plone==$PLONE_VERSION; \
    pip_install_with_fallback -r requirements.txt argparse==1.4.0 zope.component==4.6.2 collective.recipe.plonesite; \
    if [ -n "$UPDATED_PACKAGES" ]; then for pkg in $UPDATED_PACKAGES; do bin/develop up $pkg 2>/dev/null || true; done; fi; \
    GIT_TRACE=1 GIT_CURL_VERBOSE=1 buildout -N; \
    cp -a $SENAITE_HOME/buildout-cache/downloads/. /cache/buildout-downloads/ || true; \
    cp -a $SENAITE_INSTANCE_HOME/eggs/. /cache/eggs/ || true; \
    cp -a $WHEELHOUSE/. /cache/wheelhouse/ || true

RUN set -eux; \
    locale_dir="$SENAITE_INSTANCE_HOME/src/senaite.impress/src/senaite/impress/locales/zh_CN/LC_MESSAGES"; \
    mkdir -p "$locale_dir"; \
    install -m 0644 /tmp/install-lc-messages/senaite.impress.po "$locale_dir/senaite.impress.po"; \
    install -m 0644 /tmp/install-lc-messages/senaite.impress.mo "$locale_dir/senaite.impress.mo"

RUN set -eux; \
    mkdir -p $SENAITE_HOME/buildout-cache/downloads; \
    mkdir -p $SENAITE_INSTANCE_HOME/eggs; \
    mkdir -p $WHEELHOUSE; \
    ln -s $SENAITE_FILESTORAGE/ $SENAITE_INSTANCE_HOME/var/filestorage; \
    ln -s $SENAITE_BLOBSTORAGE/ $SENAITE_INSTANCE_HOME/var/blobstorage; \
    chown -R senaite:senaite $SENAITE_HOME $SENAITE_DATA

RUN set -eux; \
    rm -rf /tmp/install-lc-messages; \
    rm -rf /var/lib/apt/lists/*

# Change working directory
WORKDIR $SENAITE_INSTANCE_HOME

# Mount external volume
VOLUME /data

# Expose instance port
EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["start"]
