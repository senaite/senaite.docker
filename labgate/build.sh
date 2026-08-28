#!/usr/bin/env bash
# 构建 labgate 各平台二进制。
#
# 本机装了 Go 就直接用 Go；没装则通过 Docker 构建（无需安装 Go）。
#
#   ./build.sh                 # 默认三平台，版本号 dev
#   VERSION=1.0.0 ./build.sh   # 指定版本号
#   PLATFORMS="linux/amd64" ./build.sh
set -euo pipefail

cd "$(dirname "$0")"

VERSION="${VERSION:-dev}"
PLATFORMS="${PLATFORMS:-windows/amd64 linux/amd64 linux/arm64}"
GO_IMAGE="${GO_IMAGE:-golang:alpine}"

mkdir -p dist

# run_go <shell 脚本>：本机有 go 就本地跑，否则丢进容器跑
if command -v go >/dev/null 2>&1; then
  run_go() { sh -c "$1"; }
else
  echo "本机未安装 Go，改用 Docker 镜像 ${GO_IMAGE} 构建"
  command -v docker >/dev/null 2>&1 || {
    echo "既没有 Go 也没有 Docker，无法构建" >&2
    exit 1
  }
  docker volume create labgate-gomod >/dev/null
  docker volume create labgate-gobuild >/dev/null
  run_go() {
    docker run --rm \
      -v "$(pwd):/src" \
      -v labgate-gomod:/go/pkg/mod \
      -v labgate-gobuild:/root/.cache/go-build \
      -w /src \
      -e CGO_ENABLED=0 \
      -e GOFLAGS=-buildvcs=false \
      ${GOPROXY:+-e GOPROXY="$GOPROXY"} \
      "$GO_IMAGE" sh -c "$1"
  }
fi

if [ "${RUN_TESTS:-0}" = "1" ]; then
  echo "==> 运行测试"
  run_go "go test ./... -timeout 300s"
fi

echo "==> 检查编译"
run_go "go vet ./..."

for platform in $PLATFORMS; do
  os="${platform%%/*}"
  arch="${platform##*/}"
  ext=""
  [ "$os" = "windows" ] && ext=".exe"
  echo "==> 构建 $platform"
  run_go "
    set -e
    GOOS=$os GOARCH=$arch go build -trimpath \
      -ldflags '-s -w -X main.version=$VERSION' \
      -o dist/labgate-$os-$arch$ext ./cmd/labgate
    GOOS=$os GOARCH=$arch go build -trimpath \
      -ldflags '-s -w -X main.version=$VERSION' \
      -o dist/labbridge-$os-$arch$ext ./cmd/labbridge
    GOOS=$os GOARCH=$arch go build -trimpath -ldflags '-s -w' \
      -o dist/fakebalance-$os-$arch$ext ./cmd/fakebalance
    GOOS=$os GOARCH=$arch go build -trimpath -ldflags '-s -w' \
      -o dist/fakelims-$os-$arch$ext ./cmd/fakelims
  "
done

echo
echo "构建完成："
ls -lh dist/
