# SENAITE Docker

[SENAITE](https://www.senaite.com) is a free and open source LIMS built on top of
[Plone](https://plone.org) and the [Zope application server](https://www.zope.org).

This repository is based [plone.docker](https://github.com/plone/plone.docker) –
Thanks to the great work of http://github.com/avoinea and the other contributors.

### Try SENAITE

Click the _Try in PWD_ button below to get 4 hours to try SENAITE LIMS:

NOTE: A [DockerHub](https://hub.docker.com/) account is needed.

A sandbox environment will be created after the "Start" button was pressed.
This will take about 2-3 Minutes and the final screen will display a button
with the port number `8080` displayed on it. This will open the SENAITE site
in the webbrower.

NOTE: If the link to port `8080` is not displayed on the site, you have to click
      the **OPEN PORT** button and enter `8080` in there.

It might be that this site will not load immediately, because the server is
still in startup process. Please wait and reload until the SENAITE site appears.

**Authentication: `admin:admin`**

[![Try in PWD](https://cdn.rawgit.com/play-with-docker/stacks/cff22438/assets/images/button.png)](http://play-with-docker.com?stack=https://raw.githubusercontent.com/senaite/senaite.docker/master/stack.yml)


## Usage

Choose either single SENAITE instance or ZEO cluster.

**It is inadvisable to use following configurations for production.**


### Standalone SENAITE Instance

Standalone instances are best suited for testing SENAITE and development.

Build and start the latest SENAITE container, based on [Debian](https://www.debian.org/).

```bash
$ git clone https://github.com/senaite/senaite.docker
$ cd senaite.docker/2.4.0
$ docker build -t senaite .
$ docker run --rm --name senaite -p 8080:8080 senaite
```

The `-p 8080:8080` parameter will link port `8080` to the internal container
port where SENAITE is listening.

Now you can add a SENAITE Site at http://localhost:8080 - default user and
password are **`admin/admin`**.


### ZEO Cluster

ZEO cluster are best suited for production setups, you will **need** a loadbalancer.

Start ZEO server in the background

```bash
$ docker run -d --name=zeo senaite zeo
```

Start 2 SENAITE clients (also in the background)

```bash
$ docker run -d --name=instance1 --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8081:8080 senaite
$ docker run -d --name=instance2 --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8082:8080 senaite
```

### Start SENAITE In Debug Mode

You can also start SENAITE in debug mode (`fg`) by running

```bash
$ docker run -p 8080:8080 senaite fg
```

Debug mode may also be used with ZEO

```bash
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

```bash
$ docker run --name=instance1 --link=zeo -e ZEO_ADDRESS=zeo:8080 -p 8080:8080 \
-e ADDONS="senaite.storage" senaite
```

To use specific add-ons versions:

```bash
 -e ADDONS="senaite.storage==1.0.0"
```

### For Advanced Usage

* `PLONE_SITE`, `SITE` - Relative URL of the SENAITE site. Setting this will trigger installation.
* `PLONE_ZCML`, `ZCML` - Include custom Plone add-ons ZCML files (former `BUILDOUT_ZCML`)
* `PLONE_DEVELOP`, `DEVELOP` - Develop new or existing Plone add-ons (former `BUILDOUT_DEVELOP`)
* `ZEO_READ_ONLY` - Run Plone as a read-only ZEO client. Defaults to `off`.
* `ZEO_CLIENT_READ_ONLY_FALLBACK` - A flag indicating whether a read-only remote storage should be acceptable as a fallback when no writable storages are available. Defaults to `false`.
* `ZEO_SHARED_BLOB_DIR` - Set this to on if the ZEO server and the instance have access to the same directory. Defaults to `off`.
* `ZEO_STORAGE` - Set the storage number of the ZEO storage. Defaults to `1`.
* `ZEO_CLIENT_CACHE_SIZE` - Set the size of the ZEO client cache. Defaults to `128MB`.
* `ZEO_PACK_KEEP_OLD` - Can be set to false to disable the creation of *.fs.old files before the pack is run. Defaults to true.
* `PASSWORD` - Set the password of the ZOPE admin user


## Development

The following sections describe how to create and publish a new senaite docker
image on docker hub.

### Create a new version of a docker image

Copy an existing version structure:

```console
$ cp -r 2.3.0 2.4.0
$ cd 2.4.0
$ docker build --tag=senaite:v2.4.0 .

[...]
Successfully built 7af3395db8f6
Successfully tagged senaite:v2.4.0
```

Note that the the image will automatically tagged as `v2.4.0`.

             
### Run the container

Start a container based on your new image:

```
docker container run --publish 9999:8080 --detach --name senaite senaite:v2.4.0
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
ecf514d717ba        senaite:v2.4.0      "/docker-entrypoint.…"   26 seconds ago      Up 24 seconds (health: starting)   0.0.0.0:9999->8080/tcp   senaite
```

Go to http://localhost:9999 to install senaite.

Stop the container with `docker container stop senaite`.


### Publish the container on Docker Hub

Images must be namespaced correctly to share on Docker Hub. Specifically, images
must be named like `<Docker Hub ID>/<Repository Name>:<tag>.` We can relabel our
`senaite:2.4.0` image like this:

```console
$ docker image tag senaite:v2.4.0 senaite/senaite:v2.4.0
```

Finally, push the image to Docker Hub:

```console
docker image push senaite/senaite:v2.4.0
```

### Update the PWD stack

After each new release, the PWD configuration needs to be adapted to the latest version.
Open `stack.yml` and update the image versions to the new released version.

### Further information

Please refer to this documentation for further information:

https://docs.docker.com/get-started
