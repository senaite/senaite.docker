# 仪器采集中转站 Docker 镜像
#
# 构建（在 src/maitux.instrument_acquisition 目录下执行）：
#   docker build -f deploy/Dockerfile -t instrument-relay .
#
# 运行（--restart unless-stopped：Docker 开机自启容器、异常退出自动拉起）：
#   docker run -d --name instrument-relay \
#       --restart unless-stopped \
#       -p 9000:9000 \
#       instrument-relay
#
# 若容器访问不到局域网里的 W610（透传仪器），Linux 下可改用宿主机网络：
#   docker run -d --name instrument-relay --restart unless-stopped \
#       --network host instrument-relay

FROM python:3.11-slim

WORKDIR /app
COPY relay_station.py .

EXPOSE 9000

# LIMS 地址与 Token 按实际环境改；或运行时不传 CMD，用 docker run 参数覆盖
CMD ["python", "relay_station.py", \
     "--listen-host", "0.0.0.0", \
     "--listen-port", "9000", \
     "--lims-url", "http://192.168.1.18:8080", \
     "--token", "maitux-phase1-instrument-acquisition-token"]
