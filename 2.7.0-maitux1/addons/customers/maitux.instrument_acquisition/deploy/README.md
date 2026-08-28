# 中转站部署与系统托管

中转站（`relay_station.py`）是纯标准库的 Python 脚本，Python 2.7 / 3.x 均可，
可部署在 Linux 虚拟机、Docker 容器或 Windows 机器上，并交给系统托管：
**开机自启、崩溃自动重启、无需手动启动**。

> 一个中转站实例管一台仪器（单仪器互斥）。LIMS 侧对应的配置：
> `services/phase1_targets.py` 的 `PHASE1_RELAY_STATION_URL` 指向中转站地址。

## 方式一：Linux 虚拟机（systemd 服务，推荐）

1. 上传 `relay_station.py` 到服务器目录，如 `/opt/instrument-relay/`
2. 把 `deploy/relay_station.service` 复制为
   `/etc/systemd/system/instrument-relay.service`，
   并按环境修改其中的路径 / `--lims-url` / `--listen-port` / token
3. 启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now instrument-relay   # enable = 开机自启
sudo systemctl status instrument-relay
journalctl -u instrument-relay -f              # 看日志
```

`Restart=always` 保证崩溃后 5 秒自动拉起；升级脚本后
`sudo systemctl restart instrument-relay` 即可。

## 方式二：Docker 容器（restart=unless-stopped）

在 `src/maitux.instrument_acquisition` 目录下：

```bash
# 用 docker compose（推荐）
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml logs -f

# 或直接 docker build / run
docker build -f deploy/Dockerfile -t instrument-relay .
docker run -d --name instrument-relay --restart unless-stopped -p 9000:9000 instrument-relay
```

`restart: unless-stopped`：Docker 服务开机自启后自动拉起容器，异常退出自动重启。

注意：默认 bridge 网络下容器访问局域网里的 W610 一般可通（出方向 NAT）；
不通时 Linux 下改用 `network_mode: host`（compose 文件里已留注释）。

## 方式三：Windows 本机（NSSM 注册为 Windows 服务）

1. 下载 [NSSM](https://nssm.cc/) 并解压，管理员命令行进入 nssm 目录
2. 注册服务（路径按实际改）：

```bat
nssm install InstrumentRelay "C:\Python27\python.exe" "E:\senaite\诺诚项目\senaite.core-2.x\src\maitux.instrument_acquisition\relay_station.py --listen-host 0.0.0.0 --listen-port 9000 --lims-url http://192.168.1.18:8080 --token maitux-phase1-instrument-acquisition-token"
nssm set InstrumentRelay AppDirectory "E:\senaite\诺诚项目\senaite.core-2.x\src\maitux.instrument_acquisition"
nssm set InstrumentRelay AppStdout "E:\logs\relay.log"
nssm set InstrumentRelay AppStderr "E:\logs\relay.log"
nssm set InstrumentRelay Start SERVICE_AUTO_START
nssm start InstrumentRelay
```

- `Start SERVICE_AUTO_START`：开机自动启动
- NSSM 检测到进程退出会自动重启（等效 Restart=always）
- 卸载：`nssm remove InstrumentRelay confirm`

> 备选（不想装 NSSM）：Windows「任务计划程序」新建"登录时/启动时"任务，
> 程序填 python.exe，参数填脚本路径，勾选"不管用户是否登录都要运行"。

## 部署后验证

```bash
curl http://<中转站IP>:9000/status
```

返回 JSON（含 `success: true`）即服务正常；再进 LIMS 采集页点「开始采集」
验证仪器连接。

## 升级流程

1. 替换服务器上的 `relay_station.py`
2. 重启服务：
   - systemd：`sudo systemctl restart instrument-relay`
   - Docker：`docker compose -f deploy/docker-compose.yml up -d --build`
   - NSSM：`nssm restart InstrumentRelay`
