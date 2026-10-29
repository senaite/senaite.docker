# SENAITE Docker

[SENAITE](https://www.senaite.com) is a free and open source LIMS built on top of
[Plone](https://plone.org) and the [Zope application server](https://www.zope.org).

This repository is based on [plone.docker](https://github.com/plone/plone.docker) –
thanks to the great work of http://github.com/avoinea and the other contributors.


## Usage

Choose either single SENAITE instance or ZEO cluster.

**It is inadvisable to use following configurations for production.**


### Standalone SENAITE Instance

Standalone instances are best suited for testing SENAITE and development.

Pull and start the latest SENAITE container, based on [Debian](https://www.debian.org/).

The `2.x` tag follows the 2.x branch of senaite.core. For a fixed release,
use a version tag such as `v2.6.0-docker2` instead. All tags are listed on
[Docker Hub](https://hub.docker.com/r/senaite/senaite/tags).

```console
docker run --rm --name senaite -p 8080:8080 senaite/senaite:2.x
```

The `-p 8080:8080` parameter maps port `8080` of the container to the host.

Now you can add a SENAITE Site at http://localhost:8080 - default user and
password are `admin/admin`.


### ZEO Cluster

ZEO cluster are best suited for production setups, you will need a load balancer.

Create a shared network and start the ZEO server:

```console
docker network create senaite
docker run -d --name=zeo --network=senaite senaite/senaite:2.x zeo
```

Start 2 SENAITE clients:

```console
docker run -d --name=instance1 --network=senaite \
    -e ZEO_ADDRESS=zeo:8080 -p 8081:8080 senaite/senaite:2.x
docker run -d --name=instance2 --network=senaite \
    -e ZEO_ADDRESS=zeo:8080 -p 8082:8080 senaite/senaite:2.x
```

### Start SENAITE In Debug Mode

```console
docker run -p 8080:8080 senaite/senaite:2.x fg
```

Debug mode may also be used with ZEO:

```console
docker run --network=senaite -e ZEO_ADDRESS=zeo:8080 -p 8080:8080 senaite/senaite:2.x fg
```


## Supported Environment Variables

The SENAITE image uses several environment variables that allow to specify a
more specific setup.

### For Basic Usage

* `ADDONS` - Customize SENAITE via Plone add-ons using this environment variable
* `ZEO_ADDRESS` - This environment variable allows you to run Plone image as a ZEO client.

Run SENAITE with ZEO and install the addon [senaite.storage](https://github.com/senaite/senaite.storage):

```console
docker run --name=instance1 --network=senaite \
    -e ZEO_ADDRESS=zeo:8080 -p 8080:8080 \
    -e ADDONS="senaite.storage" senaite/senaite:2.x
```

To use a specific add-on version:

```console
-e ADDONS="senaite.storage==1.0.0"
```

### For Advanced Usage

* `PLONE_SITE`, `SITE` - Relative URL of the SENAITE site. Setting this will trigger installation.
* `PLONE_ZCML`, `ZCML` - Include custom Plone add-ons ZCML files (former `BUILDOUT_ZCML`)
* `PLONE_DEVELOP`, `DEVELOP` - Develop new or existing Plone add-ons (former `BUILDOUT_DEVELOP`)
* `ZEO_READ_ONLY` - Run Plone as a read-only ZEO client. Defaults to `off`.
* `ZEO_CLIENT_READ_ONLY_FALLBACK` - A flag indicating whether a read-only remote storage
  should be acceptable as a fallback when no writable storages are available. Defaults to `false`.
* `ZEO_SHARED_BLOB_DIR` - Set this to on if the ZEO server and the instance have access to
  the same directory. Defaults to `off`.
* `ZEO_STORAGE` - Set the storage number of the ZEO storage. Defaults to `1`.
* `ZEO_CLIENT_CACHE_SIZE` - Set the size of the ZEO client cache. Defaults to `128MB`.
* `ZEO_PACK_KEEP_OLD` - Can be set to false to disable the creation of *.fs.old files
  before the pack is run. Defaults to true.
* `PASSWORD` - Set the password of the ZOPE admin user


## Development

The following sections describe how to create and publish a new senaite docker
image on docker hub.

### Create a new version of a docker image

Copy an existing version structure and update `buildout.cfg` and
`requirements.txt` as needed:

```console
cp -r 2.6.0 2.7.0
cd 2.7.0
```

Build the image locally for testing (single platform):

```console
docker build --tag=senaite:v2.7.0 .
```

To test a multi-platform build locally without pushing:

```console
docker buildx create --use --name multibuilder --driver docker-container
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag senaite/senaite:v2.7.0 \
    --output type=oci,dest=senaite-v2.7.0.tar \
    .
```

### Run the container

Start a container based on your new image:

```console
docker container run --publish 9999:8080 --detach --name senaite senaite:v2.7.0
```

Go to http://localhost:9999 to install senaite.

Stop the container with `docker container stop senaite`.


### Publish the container on Docker Hub

Images are published automatically via the GitHub Actions workflow in
`senaite/senaite.core` when pushing to the `2.x` branch. The workflow builds
multi-platform images (`linux/amd64`, `linux/arm64`) and pushes them to Docker
Hub with the `edge` and branch name tags.

To publish a release image manually:

```console
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag senaite/senaite:v2.7.0 \
    --push \
    .
```

### Further information

Please refer to this documentation for further information:

https://docs.docker.com/get-started
