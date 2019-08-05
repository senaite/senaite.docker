# Use an official Python runtime as a parent image
FROM python:2.7-stretch

# Set one or more individual labels
LABEL maintainer="Ramon Bartl"
LABEL email="rb@ridingbytes.com"
LABEL senaite.core.version="1.3.1"

# Set environment variables
ENV PLONE_MAJOR=4.3 \
    PLONE_VERSION=4.3.18 \
    PLONE_MD5=c9932e919254a2799b0e340b2ecbda9b \
    SENAITE_HOME=/home/senaite \
    SENAITE_USER=senaite \
    SENAITE_INSTANCE_HOME=/home/senaite/senaitelims \
    SENAITE_DATA=/data \
    SENAITE_FILESTORAGE=/data/filestorage \
    SENAITE_BLOBSTORAGE=/data/blobstorage

# Create the senaite user
RUN useradd --system -m -d $SENAITE_HOME -U -u 500 $SENAITE_USER

# Create direcotries
RUN mkdir -p $SENAITE_INSTANCE_HOME $SENAITE_FILESTORAGE $SENAITE_BLOBSTORAGE

# Copy the package config
COPY packages.txt /

# Install package dependencies
RUN apt-get update && apt-get install -y --no-install-recommends $(grep -vE "^\s*#" /packages.txt  | tr "\n" " ")

# Fetch unified installer
RUN wget -O Plone.tgz https://launchpad.net/plone/$PLONE_MAJOR/$PLONE_VERSION/+download/Plone-$PLONE_VERSION-UnifiedInstaller.tgz \
    && echo "$PLONE_MD5 Plone.tgz" | md5sum -c - \
    && tar -xzf Plone.tgz \
    && cp -rv /Plone-$PLONE_VERSION-UnifiedInstaller/base_skeleton/* $SENAITE_INSTANCE_HOME \
    && cp -v /Plone-$PLONE_VERSION-UnifiedInstaller/buildout_templates/buildout.cfg $SENAITE_INSTANCE_HOME/buildout-base.cfg \
    && cd $SENAITE_INSTANCE_HOME \
    && tar -xjf /Plone-$PLONE_VERSION-UnifiedInstaller/packages/buildout-cache.tar.bz2

# Change working directory
WORKDIR $SENAITE_INSTANCE_HOME

# Copy Buildout
COPY bootstrap.py buildout.cfg ./

# Bootstrap and buildout
RUN python bootstrap.py \
    && bin/buildout \
    && ln -s $SENAITE_FILESTORAGE/ var/filestorage \
    && ln -s $SENAITE_BLOBSTORAGE/ var/blobstorage \
    && chown -R senaite:senaite $SENAITE_HOME $SENAITE_DATA

# Mount external volume
VOLUME /data

# Copy startup scripts
COPY docker-initialize.py docker-entrypoint.sh /

# Expose instance port
EXPOSE 8080

# Add instance healthcheck
HEALTHCHECK --interval=1m --timeout=5s --start-period=1m \
  CMD nc -z -w5 127.0.0.1 8080 || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["start"]
