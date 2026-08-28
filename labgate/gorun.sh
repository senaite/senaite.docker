#!/usr/bin/env bash
# 在 Docker 里执行任意 go 命令，本机不用装 Go。
#
#   ./gorun.sh go test ./...
#   ./gorun.sh go vet ./...
#   ./gorun.sh sh -c 'GOOS=windows go build ./...'
#
# 模块缓存与编译缓存放在命名卷里，第二次执行会快很多。
set -e
cd "$(dirname "$0")"
docker volume create labgate-gomod >/dev/null
docker volume create labgate-gobuild >/dev/null
MSYS_NO_PATHCONV=1 exec docker run --rm \
  -v "$(pwd -W 2>/dev/null || pwd):/src" \
  -v labgate-gomod:/go/pkg/mod \
  -v labgate-gobuild:/root/.cache/go-build \
  -w /src \
  -e CGO_ENABLED=0 \
  -e GOFLAGS=-buildvcs=false \
  "${GO_IMAGE:-golang:alpine}" "$@"
