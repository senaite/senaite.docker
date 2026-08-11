# maitux.branding 安装说明

## 包简介

**MAITUX BRANDING** (`maitux.branding 0.1.0`)

- 移除 SENAITE 底部栏的版权文字、外部链接和图标组
- 浏览器标签标题自动显示为 **MaiTux LIMS**（覆盖 `plone.htmlhead.title` viewlet，每次请求生效）

通过 `FooterViewlet` / `ColophonViewlet` 重写实现 footer 清理，通过 `TitleViewlet` 覆盖实现标题替换。

依赖：
- `senaite.core`
- `senaite.lims`
- `zope.interface`

---

## 当前 Docker 项目中的安装方式（推荐）

本仓库使用手工维护的 `common-addons.cfg` 管理通用 addon，并在 Docker 构建时一并复制到镜像中。

当前目录建议保持如下结构：

```text
latest/
  addons/
    common/
      maitux.branding/
```

### 1. 将 addon 放到 `addons/common/`

本包当前路径如下：

```text
d:\AWork\senaite.docker\latest\addons\common\maitux.branding
```

镜像构建时会复制 `addons/common/` 到容器内 `/opt/addons/common`。

然后需要在 `latest/common-addons.cfg` 中手工加入本 addon，配置如下：

```ini
[buildout]
develop +=
    /opt/addons/common/maitux.branding
eggs +=
    maitux.branding

[plonesite]
profiles =
    senaite.lims:default
    maitux.branding:default
```

### 2. 重新构建镜像

在 `d:\AWork\senaite.docker\latest` 目录执行：

```bash
docker compose build app
```

### 3. 启动或重建容器

```bash
docker compose up -d
```

### 4. 生效说明

- 如果是新建站点，addon 会随站点初始化一起安装
- 如果是已经存在的站点，代码会进入实例，但通常仍需到 `Site Setup -> Add-ons` 中激活一次

激活成功后，SENAITE 底部栏的版权文字、外部链接和图标组将被移除，浏览器标题将显示为 **MaiTux LIMS**

---

## 非 Docker 场景（仅参考）

如果不是使用当前仓库的 Docker 方案，也可以按常规 Python / buildout 方式手工安装，但这不是本仓库的推荐路径。

---

## 卸载

1. `Site Setup` -> `Add-ons` -> 取消勾选 **MAITUX BRANDING** -> `Deactivate`
2. 如需完全移除，从 `buildout.cfg` 中移除对应 egg 和 develop 配置后重新运行 `bin/buildout`

---

## 文件清单

```
maitux.branding/
├── setup.py
├── README.rst
├── INSTALL.md              ← 本文件
└── src/
    └── maitux/
        ├── __init__.py
        └── branding/
            ├── __init__.py
            ├── configure.zcml
            ├── interfaces.py
            ├── browser/
            │   ├── __init__.py
            │   ├── configure.zcml
            │   ├── viewlets.py
            │   └── templates/
            │       ├── colophon.pt
            │       ├── footer.pt
            │       └── title.pt
            ├── profiles/
                ├── default/
                │   ├── browserlayer.xml
                │   ├── metadata.xml
                │   ├── maitux.branding.txt
                │   └── setuphandlers.py
                └── uninstall/
                    ├── browserlayer.xml
                    ├── metadata.xml
                    └── maitux.branding_uninstall.txt
```

