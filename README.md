# SENAITE Docker

[SENAITE](https://www.senaite.com) is a free and open source LIMS built on top of
[Plone](https://plone.org) and the [Zope application server](https://www.zope.org).

This repository is based [plone.docker](https://github.com/plone/plone.docker) –
Thanks to the great work of http://github.com/avoinea and the other contributors.

### Try SENAITE

Click the _Try in PWD_ button below to get 4 hours to try SENAITE LIMS:

NOTE: A [DockerHub](https://hub.docker.com/) account is needed.

**Authentication: `admin:admin`**

[![Try in PWD](https://cdn.rawgit.com/play-with-docker/stacks/cff22438/assets/images/button.png)](http://play-with-docker.com?stack=https://raw.githubusercontent.com/senaite/senaite.docker/master/stack.yml)


## Usage

Choose either single SENAITE instance or ZEO cluster.

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
$ docker run -d --name=zeo senaite zeo
```

Start 2 SENAITE clients (also in the background)

```console
$ docker run -d --name=instance1 --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8081:8080 senaite
$ docker run -d --name=instance2 --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8082:8080 senaite
```

### Start SENAITE In Debug Mode

You can also start SENAITE in debug mode (`fg`) by running

```console
$ docker run -p 8080:8080 senaite fg
```

Debug mode may also be used with ZEO

```console
$ docker run --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8080:8080 senaite fg
```

For more information on how to extend this image with your own custom settings,
adding more add-ons, building it or mounting volumes, please refer to the
[plone.docker documentation](https://docs.plone.org/manage/docker/docs/index.html).


## Supported Environment Variables

The SENAITE image uses several environment variable that allow to specify a more specific setup.

### For Basic Usage

* `ADDONS` - Customize SENAITE via Plone add-ons using this environment variable
* `ZEO_ADDRESS` - This environment variable allows you to run Plone image as a ZEO client.

Run SENAITE with ZEO and install the addon [senaite.storage](https://github.com/senaite/senaite.storage)

```console
$ docker run --name=instance1 --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8080:8080 \
-e ADDONS="senaite.storage" senaite
```

To use specific add-ons versions:

```console
 -e ADDONS="senaite.storage==1.0.0"
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


## Development

The following sections describe how to create and publish a new senaite docker
image on docker hub.

### Create a new version of a docker image

Copy an existing version structure:

```console
$ cp -r 1.3.1 1.3.2
$ cd 1.3.2
$ docker build --tag=senaite:v1.3.2 .

[...]
Successfully built 7af3395db8f6
Successfully tagged senaite:v1.3.2
```

Note that the the image will automatically tagged as `v1.3.2`.

             
### Run the container

Start a container based on your new image:

```
docker container run --publish 9999:8080 --detach --name senaite senaite:v1.3.2
```

We used a couple of common flags here:

  - `--publish` asks Docker to forward traffic incoming on the host’s port
                9999, to the container’s port 8080 (containers have their own
                private set of ports, so if we want to reach one from the
                network, we have to forward traffic to it in this way;
                otherwise, firewall rules will prevent all network traffic from
                reaching your container, as a default security posture).

  - `--detach` asks Docker to run this container in the background.

  - `--name` lets us specify a name with which we can refer to our container in
             subset
```

$ docker container ls
CONTAINER ID        IMAGE               COMMAND                  CREATED             STATUS                             PORTS                    NAMES
ecf514d717ba        senaite:v1.3.2      "/docker-entrypoint.…"   26 seconds ago      Up 24 seconds (health: starting)   0.0.0.0:9999->8080/tcp   s132
```

Go to http://localhost:9999 to install senaite.

Stop the container with `docker container stop s132`.


### Publish the container on Docker Hub

Images must be namespaced correctly to share on Docker Hub. Specifically, images
must be named like `<Docker Hub ID>/<Repository Name>:<tag>.` We can relabel our
`senaite:1.3.2` image like this:

```console
$ docker image tag senaite:v1.3.2 ramonski/senaite:v1.3.2
$ docker image tag senaite:v1.3.2 ramonski/senaite:latest
```

Finally, push the image to Docker Hub:

```console
docker image push ramonski/senaite:v1.3.2
docker image push ramonski/senaite:latest
```

### Further information

Please refer to this documentation for further information:

https://docs.docker.com/get-started
