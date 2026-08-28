# labgate —— 实验室仪器采集网关（边缘节点）
#
# 多阶段构建，产物是静态链接的单二进制，运行镜像不含编译工具链。
# 国内环境可用 --build-arg 换镜像源与 Go 代理：
#   docker build \
#     --build-arg GO_IMAGE=docker.m.daocloud.io/library/golang:alpine \
#     --build-arg GOPROXY=https://goproxy.cn,direct .

ARG GO_IMAGE=golang:alpine
ARG RUNTIME_IMAGE=alpine:3.22

# ---------------------------------------------------------------- 构建阶段
FROM ${GO_IMAGE} AS builder

ARG GOPROXY
ENV GOPROXY=${GOPROXY:-https://proxy.golang.org,direct}
ENV CGO_ENABLED=0

WORKDIR /src

# 先只拷依赖清单，依赖不变时这一层可复用缓存
COPY go.mod go.sum ./
RUN go mod download

COPY . .

ARG VERSION=dev
# TARGETOS/TARGETARCH 由 buildx 注入；单平台构建时为空，走本机架构
ARG TARGETOS
ARG TARGETARCH
RUN GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH} \
    go build -trimpath -ldflags "-s -w -X main.version=${VERSION}" \
      -o /out/labgate ./cmd/labgate && \
    GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH} \
    go build -trimpath -ldflags "-s -w -X main.version=${VERSION}" \
      -o /out/labbridge ./cmd/labbridge && \
    GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH} \
    go build -trimpath -ldflags "-s -w" \
      -o /out/fakebalance ./cmd/fakebalance && \
    GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH} \
    go build -trimpath -ldflags "-s -w" \
      -o /out/fakelims ./cmd/fakelims

# ---------------------------------------------------------------- 运行阶段
FROM ${RUNTIME_IMAGE}

# ca-certificates：连 HTTPS 的云 LIMS 用；tzdata：日志时间戳按本地时区
RUN apk add --no-cache ca-certificates tzdata && \
    adduser -D -u 10001 -h /home/labgate labgate
ENV TZ=Asia/Shanghai

COPY --from=builder /out/labgate /usr/local/bin/labgate
COPY --from=builder /out/labbridge /usr/local/bin/labbridge
COPY --from=builder /out/fakebalance /usr/local/bin/fakebalance
COPY --from=builder /out/fakelims /usr/local/bin/fakelims

# 配置与 JetStream 数据都放在 /data，挂一个卷即可持久化。
# 空的命名卷会继承这里的属主，非 root 也能写。
RUN mkdir -p /data && chown -R labgate:labgate /data
VOLUME ["/data"]

USER labgate
WORKDIR /data
# 配置与 JetStream 数据都落在 /data；不设这个值时相对路径会变成 /data/data
ENV LABGATE_DATA_DIR=/data
EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8090/healthz >/dev/null 2>&1 || exit 1

ENTRYPOINT ["labgate"]
CMD ["--config", "/data/config.json"]
