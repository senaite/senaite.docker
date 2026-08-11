# Customer Addons

本目录用于存放“仅部分客户需要”的 SENAITE / Plone addon。

## 目录用途

- `addons/common/`
  - 存放所有客户通用的 addon
  - 这类 addon 通常建议直接进入镜像或统一纳入公共 buildout 配置

- `addons/customers/`
  - 存放客户专属 addon
  - 建议按客户分目录管理，避免不同客户的插件混在一起

推荐结构：

```text
addons/
  common/
    medai.footercleanup/
  customers/
    customer-a/
      customer.a.addon/
    customer-b/
      customer.b.addon/
```

## 推荐做法

优先推荐保存“解压后的源码目录”，不推荐长期只保存 zip 文件。

推荐原因：

- buildout / develop 更适合直接引用源码目录
- 便于版本管理、差异比较和排查问题
- 便于按客户做小范围修改
- 后续挂载到容器时更直接

zip 文件更适合：

- 临时交付
- 归档备份
- 第三方交付的原始安装包留档

如果必须保留 zip，建议同时保留解压后的目录，例如：

```text
addons/
  common/
    medai.footercleanup_0.1.0.zip
    medai.footercleanup/
```

## 客户插件放置建议

建议一个客户一个目录，例如：

```text
addons/customers/customer-a/customer.a.addon/
addons/customers/customer-b/customer.b.addon/
```

这样便于：

- 单独挂载客户插件
- 单独维护客户配置
- 后续使用 `docker-compose.customer-a.yml` 做覆盖

## 启用方式

仅把 addon 放到目录里还不够，还需要在 buildout 配置中声明：

- `develop +=`
- `eggs +=`
- `profiles +=`

通常配合客户自己的 `custom.cfg` 使用。

## 命名建议

- 目录名尽量使用 addon 的 Python package 名称
- 客户目录名使用稳定代号，例如 `customer-a`、`nb-hospital`、`demo-lab`
- 不建议直接把多个客户插件平铺在 `addons/customers/` 根目录下
