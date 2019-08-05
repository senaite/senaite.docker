#!/usr/local/bin/python

import re
import os
import warnings
warnings.simplefilter('always', DeprecationWarning)


class Environment(object):
    """ Configure container via environment variables
    """
    def __init__(
            self,
            env=os.environ,
            zope_conf="/home/senaite/senaitelims/parts/instance/etc/zope.conf",
            custom_conf="/home/senaite/senaitelims/custom.cfg",
            zeopack_conf="/home/senaite/senaitelims/bin/zeopack",
            zeoserver_conf="/home/senaite/senaitelims/parts/zeoserver/etc/zeo.conf"):
        self.env = env
        self.zope_conf = zope_conf
        self.custom_conf = custom_conf
        self.zeopack_conf = zeopack_conf
        self.zeoserver_conf = zeoserver_conf

    def zeoclient(self):
        """ ZEO Client
        """
        server = self.env.get("ZEO_ADDRESS", None)
        if not server:
            return

        config = ""
        with open(self.zope_conf, "r") as cfile:
            config = cfile.read()

        # Already initialized
        if "<blobstorage>" not in config:
            return

        read_only = self.env.get("ZEO_READ_ONLY", "false")
        zeo_ro_fallback = self.env.get("ZEO_CLIENT_READ_ONLY_FALLBACK", "false")
        shared_blob_dir = self.env.get("ZEO_SHARED_BLOB_DIR", "off")
        zeo_storage = self.env.get("ZEO_STORAGE", "1")
        zeo_client_cache_size = self.env.get("ZEO_CLIENT_CACHE_SIZE", "128MB")
        zeo_conf = ZEO_TEMPLATE.format(
            zeo_address=server,
            read_only=read_only,
            zeo_client_read_only_fallback=zeo_ro_fallback,
            shared_blob_dir=shared_blob_dir,
            zeo_storage=zeo_storage,
            zeo_client_cache_size=zeo_client_cache_size
        )

        pattern = re.compile(r"<blobstorage>.+</blobstorage>", re.DOTALL)
        config = re.sub(pattern, zeo_conf, config)

        with open(self.zope_conf, "w") as cfile:
            cfile.write(config)

    def zeopack(self):
        """ ZEO Pack
        """
        server = self.env.get("ZEO_ADDRESS", None)
        if not server:
            return

        if ":" in server:
            host, port = server.split(":")
        else:
            host, port = (server, "8100")

        with open(self.zeopack_conf, 'r') as cfile:
            text = cfile.read()
            text = text.replace('address = "8100"', 'address = "%s"' % server)
            text = text.replace('host = "127.0.0.1"', 'host = "%s"' % host)
            text = text.replace('port = "8100"', 'port = "%s"' % port)

        with open(self.zeopack_conf, 'w') as cfile:
            cfile.write(text)

    def zeoserver(self):
        """ ZEO Server
        """
        pack_keep_old = self.env.get("ZEO_PACK_KEEP_OLD", '')
        if pack_keep_old.lower() in ("false", "no", "0", "n", "f"):
            with open(self.zeoserver_conf, 'r') as cfile:
                text = cfile.read()
                if 'pack-keep-old' not in text:
                    text = text.replace(
                        '</filestorage>',
                        '  pack-keep-old false\n</filestorage>'
                    )

            with open(self.zeoserver_conf, 'w') as cfile:
                cfile.write(text)

    def buildout(self):
        """ Buildout from environment variables
        """
        # Already configured
        if os.path.exists(self.custom_conf):
            return

        eggs = self.env.get("PLONE_ADDONS",
                            self.env.get("ADDONS", "")).strip().split()
        if not eggs:
            eggs = self.env.get("BUILDOUT_EGGS", "").strip().split()
            if eggs:
                warnings.warn(
                    "BUILDOUT_EGGS is deprecated. Please use "
                    "PLONE_ADDONS instead !!!", DeprecationWarning)

        zcml = self.env.get("PLONE_ZCML",
                            self.env.get("ZCML", "")).strip().split()
        if not zcml:
            zcml = self.env.get("BUILDOUT_ZCML", "").strip().split()
            if zcml:
                warnings.warn(
                    "BUILDOUT_ZCML is deprecated. Please use "
                    "PLONE_ZCML instead !!!", DeprecationWarning)

        develop = self.env.get("PLONE_DEVELOP",
                               self.env.get("DEVELOP", "")).strip().split()
        if not develop:
            develop = self.env.get("BUILDOUT_DEVELOP", "").strip().split()
            if develop:
                warnings.warn(
                    "BUILDOUT_DEVELOP is deprecated. Please use "
                    "PLONE_DEVELOP instead !!!", DeprecationWarning)

        if not (eggs or zcml or develop):
            return

        buildout = BUILDOUT_TEMPLATE.format(
            eggs="\n\t".join(eggs),
            zcml="\n\t".join(zcml),
            develop="\n\t".join(develop)
        )

        with open(self.custom_conf, 'w') as cfile:
            cfile.write(buildout)

    def setup(self, **kwargs):
        self.buildout()
        self.zeoclient()
        self.zeopack()
        self.zeoserver()

    __call__ = setup


ZEO_TEMPLATE = """
    <zeoclient>
      read-only {read_only}
      read-only-fallback {zeo_client_read_only_fallback}
      blob-dir /data/blobstorage
      shared-blob-dir {shared_blob_dir}
      server {zeo_address}
      storage {zeo_storage}
      name zeostorage
      var /home/senaite/senaitelims/parts/instance/var
      cache-size {zeo_client_cache_size}
    </zeoclient>
""".strip()


BUILDOUT_TEMPLATE = """
[buildout]
extends = develop.cfg
develop += {develop}
eggs += {eggs}
zcml += {zcml}
"""


def initialize():
    """ Configure Plone instance as ZEO Client
    """
    environment = Environment()
    environment.setup()


if __name__ == "__main__":
    initialize()
