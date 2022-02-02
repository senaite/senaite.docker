# Use an official Python runtime as a parent image
FROM python:2.7-slim-buster

# Set one or more individual labels
LABEL maintainer="Ramon Bartl"
LABEL email="rb@ridingbytes.com"
LABEL senaite.core.version="latest"

# Set environment variables
ENV PLONE_MAJOR=5.2 \
    PLONE_VERSION=5.2.7 \
    PLONE_MD5=c180d7ce3170b1871a7e8d53938096b1 \
    PLONE_UNIFIED_INSTALLER=Plone-5.2.7-UnifiedInstaller-1.0 \
    SENAITE_HOME=/home/senaite \
    SENAITE_USER=senaite \
    SENAITE_INSTANCE_HOME=/home/senaite/senaitelims \
    SENAITE_DATA=/data \
    SENAITE_FILESTORAGE=/data/filestorage \
    SENAITE_BLOBSTORAGE=/data/blobstorage

# Create the senaite user
RUN useradd --system -m -d $SENAITE_HOME -U -u 500 $SENAITE_USER

# Create directories
RUN mkdir -p $SENAITE_INSTANCE_HOME $SENAITE_FILESTORAGE $SENAITE_BLOBSTORAGE

# Copy the build dependencies
COPY build_deps.txt /

# Copy the runtime dependencies
COPY run_deps.txt /

# Install package dependencies
RUN apt-get update
RUN apt-get install -y --no-install-recommends $(grep -vE "^\s*#" /build_deps.txt  | tr "\n" " ")
RUN apt-get install -y --no-install-recommends $(grep -vE "^\s*#" /run_deps.txt  | tr "\n" " ")

# Fetch unified installer
RUN wget -O Plone.tgz https://launchpad.net/plone/$PLONE_MAJOR/$PLONE_VERSION/+download/$PLONE_UNIFIED_INSTALLER.tgz \
    && echo "$PLONE_MD5 Plone.tgz" | md5sum -c - \
    && tar -xzf Plone.tgz \
    && cp -rv /$PLONE_UNIFIED_INSTALLER/base_skeleton/* $SENAITE_INSTANCE_HOME \
    && cp -v /$PLONE_UNIFIED_INSTALLER/buildout_templates/buildout.cfg $SENAITE_INSTANCE_HOME/buildout-base.cfg \
    && cd $SENAITE_HOME \
    && rm -rf /$PLONE_UNIFIED_INSTALLER /Plone.tgz

# Change working directory
WORKDIR $SENAITE_INSTANCE_HOME

# Copy Buildout
COPY requirements.txt buildout.cfg ./

# Buildout
RUN pip install -r requirements.txt \
    && buildout \
    && ln -s $SENAITE_FILESTORAGE/ var/filestorage \
    && ln -s $SENAITE_BLOBSTORAGE/ var/blobstorage \
    && chown -R senaite:senaite $SENAITE_HOME $SENAITE_DATA

# Cleanup
RUN apt-get purge -y --auto-remove $(grep -vE "^\s*#" /build_deps.txt  | tr "\n" " ")
RUN rm -rf /$SENAITE_HOME/buildout-cache
RUN rm -rf /var/lib/apt/lists/*

# Mount external volume
# VOLUME /data

# Copy startup scripts
COPY docker-initialize.py docker-entrypoint.sh /

# Expose instance port
EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["start"]
