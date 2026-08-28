#!/bin/bash
set -e

COMMANDS="adduser debug fg foreground help kill logreopen logtail reopen_transcript run show status stop wait"
START="console start restart"

# Fixing permissions for external /data volumes
mkdir -p /data/blobstorage /data/cache /data/filestorage /data/instance /data/log /data/zeoserver
mkdir -p /home/senaite/senaitelims/src

find /data  -not -user senaite -exec chown senaite:senaite {} \+
find /home/senaite -not -user senaite -exec chown senaite:senaite {} \+


# Initializing from environment variables
gosu senaite python /docker-initialize.py

if [ -n "$PASSWORD" ]; then
    echo "admin:$PASSWORD" > /home/senaite/senaitelims/parts/instance/inituser
    chown senaite:senaite /home/senaite/senaitelims/parts/instance/inituser
fi

function git_fixture {
  for d in `find /home/senaite/senaitelims/src -mindepth 1 -maxdepth 1 -type d`
  do
    if [ -d "$d/.git" ]; then
      git config --global --add safe.directory $d
      echo "git config --global --add safe.directory $d"
    fi
  done
}

# Fix mr.developer: fatal: detected dubious ownership in repository at ...
# https://github.com/actions/runner-images/issues/6775
# https://github.com/senaite/senaite.docker/issues/17
git_fixture

# ---------------------------------------------------------------------------
# 客户 add-on 的 buildout 配置（custom-addon.cfg）每次启动重新生成：
# 先删掉旧文件，再按 /opt/addons/customers 里实际存在的 add-on 重新写一份。
#
# 部署人员不用再手工维护它；物理删掉某个 add-on 目录也不会再出现
# 「cfg 里还留着 → buildout 失败 → 容器无限重启」。生成规则见脚本顶部注释。
# ---------------------------------------------------------------------------
if [ ! -f /gen-custom-addon.sh ]; then
  echo "ERROR: 缺少 /gen-custom-addon.sh，无法生成客户 add-on 配置" >&2
  echo "       检查 docker-compose.yml 里的挂载，或重建镜像" >&2
  exit 1
fi
# 该脚本可能是从 Windows 宿主挂载进来的 CRLF 文件，直接执行会 bad interpreter，
# 所以照 Dockerfile 的老办法先去掉 \r（宿主是只读挂载，写到 /tmp 再跑）
sed 's/\r$//' /gen-custom-addon.sh > /tmp/gen-custom-addon.sh
bash /tmp/gen-custom-addon.sh

if [ -e "custom.cfg" ]; then
  buildout -c custom.cfg -o -n
  find /data  -not -user senaite -exec chown senaite:senaite {} \+
  find /home/senaite -not -user senaite -exec chown senaite:senaite {} \+
  gosu senaite python /docker-initialize.py
fi

# ZEO Server
if [[ "$1" == "zeo"* ]]; then
  exec gosu senaite bin/$1 fg
fi

# Instance start
if [[ $START == *"$1"* ]]; then
  exec gosu senaite bin/instance console
fi

# Instance helpers
if [[ $COMMANDS == *"$1"* ]]; then
  exec gosu senaite bin/instance "$@"
fi

# Custom
exec "$@"
