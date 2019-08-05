# SENAITE Docker

[SENAITE](https://www.senaite.com) is a free and open source LIMS built on top of
[Plone](https://plone.org) and the [Zope application server](https://www.zope.org).

This repository is based [plone.docker](https://github.com/plone/plone.docker) –
Thanks to the great work of @avoinea and the other contributors.

### Try SENAITE

Click the _Try in PWD_ button below to get 4 hours to try SENAITE LIMS:

NOTE: A [DockerHub](https://hub.docker.com/) account is needed.

**Authentication: `admin:admin`**

[![Try in PWD](https://cdn.rawgit.com/play-with-docker/stacks/cff22438/assets/images/button.png)](http://play-with-docker.com?stack=https://raw.githubusercontent.com/senaite/senaite.docker/master/stack.yml)


## Usage

Choose either single Plone instance or ZEO cluster.

**It is inadvisable to use following configurations for production.**


### Standalone SENAITE Instance

Standalone instances are best suited for testing SENAITE and development.

Download and start the latest SENAITE container, based on [Debian](https://www.debian.org/).

```console
$ docker run -p 8080:8080 senaite
```

This image exposes the TCP Port `8080` via `EXPOSE 8080`, so standard container
linking will make it automatically available to the linked containers.

Now you can add a SENAITE Site at http://localhost:8080 - default user and
password are **`admin/admin`**.


### ZEO Cluster

ZEO cluster are best suited for production setups, you will **need** a loadbalancer.

Start ZEO server in the background

```console
$ docker run -d --name=zeo senait zeo
```

Start 2 SENAITE clients (also in the background)

```console
$ docker run -d --name=instance1 --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8081:8080 senaite
$ docker run -d --name=instance2 --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8082:8080 senaite
```

### Start SENAITE In Debug Mode

You can also start Plone in debug mode (`fg`) by running

```console
$ docker run -p 8080:8080 senaite fg
```

Debug mode may also be used with ZEO

```console
$ docker run --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8080:8080 senaite fg
```

For more information on how to extend this image with your own custom settings, adding more add-ons, building it or mounting volumes, please refer to our [documentation](https://docs.plone.org/manage/docker/docs/index.html).


## Supported Environment Variables

The Plone image uses several environment variable that allow to specify a more specific setup.

### For Basic Usage

* `ADDONS` - Customize SENAITE via Plone add-ons using this environment variable
* `ZEO_ADDRESS` - This environment variable allows you to run Plone image as a ZEO client.

Run Plone with ZEO and install two addons (PloneFormGen and collective.roster)

```console
$ docker run --name=instance1 --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8080:8080 \
-e ADDONS="Products.PloneFormGen collective.roster" plone
```

To use specific add-ons versions:

```console
 -e ADDONS="Products.PloneFormGen==1.8.5 collective.roster==2.3.1"
```

### For Advanced Usage

* `PLONE_ZCML`, `ZCML` - Include custom Plone add-ons ZCML files (former `BUILDOUT_ZCML`)
* `PLONE_DEVELOP`, `DEVELOP` - Develop new or existing Plone add-ons (former `BUILDOUT_DEVELOP`)
* `ZEO_READ_ONLY` - Run Plone as a read-only ZEO client. Defaults to `off`.
* `ZEO_CLIENT_READ_ONLY_FALLBACK` - A flag indicating whether a read-only remote storage should be acceptable as a fallback when no writable storages are available. Defaults to `false`.
* `ZEO_SHARED_BLOB_DIR` - Set this to on if the ZEO server and the instance have access to the same directory. Defaults to `off`.
* `ZEO_STORAGE` - Set the storage number of the ZEO storage. Defaults to `1`.
* `ZEO_CLIENT_CACHE_SIZE` - Set the size of the ZEO client cache. Defaults to `128MB`.
* `ZEO_PACK_KEEP_OLD` - Can be set to false to disable the creation of *.fs.old files before the pack is run. Defaults to true.
