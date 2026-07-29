# SENAITE Docker Local Run Guide

## 1. Enter the build directory

```powershell
cd d:\AWork\senaite.docker\latest
```

## 2. Build the image

Use the normal build command:

```powershell
docker build -t maitux-lims:latest .
```

Before building, if you add or remove any addon under `d:\AWork\senaite.docker\latest\addons\common`, remember to manually update:

```text
d:\AWork\senaite.docker\latest\common-addons.cfg
```

Current common addon config example:

```ini
[buildout]
develop +=
    /opt/addons/common/maitux.footercleanup_0.1.0
eggs +=
    maitux.footercleanup

[plonesite]
profiles =
    senaite.lims:default
    maitux.footercleanup:default
```

If you want detailed build logs:

```powershell
$env:DOCKER_BUILDKIT="1"
docker build --progress=plain -t maitux-lims:latest .
```

If you need to build through a local proxy:

```powershell
$env:DOCKER_BUILDKIT="1"
$env:HTTP_PROXY="http://host.docker.internal:7897"
$env:HTTPS_PROXY="http://host.docker.internal:7897"
$env:NO_PROXY="127.0.0.1,localhost,postgres,maitux-lims,maitux-lims-postgres"

docker build --progress=plain `
  --build-arg HTTP_PROXY=$env:HTTP_PROXY `
  --build-arg HTTPS_PROXY=$env:HTTPS_PROXY `
  --build-arg NO_PROXY=$env:NO_PROXY `
  -t maitux-lims:latest .
```

If you need to force a full rebuild without cache:

```powershell
docker build --no-cache --progress=plain -t maitux-lims:latest .
```

## 3. Start the container

```powershell
docker compose -f docker-compose.yml up -d --build
```

## 4. Check container status

```powershell
docker compose -f docker-compose.yml ps
```

## 5. View startup logs

```powershell
docker compose -f docker-compose.yml logs -f instance
```

## 6. Open the site

After the container starts successfully, open:

```text
http://localhost:8083/MaiLIMS
```

## 7. Verify Chinese locale files in the container

Enter the container:

```powershell
docker exec -it maitux-lims bash
```

Check the locale directory:

```bash
ls /home/senaite/senaitelims/src/senaite.impress/src/senaite/impress/locales/zh_CN/LC_MESSAGES
```

You should see these two files:

```text
senaite.impress.mo
senaite.impress.po
```

Optionally inspect the PO file content:

```bash
head -n 20 /home/senaite/senaitelims/src/senaite.impress/src/senaite/impress/locales/zh_CN/LC_MESSAGES/senaite.impress.po
```

## 8. Stop the container

```powershell
docker compose -f docker-compose.yml down
```

