# labgate 构建入口。
# 本机没装 Go 时用 make docker-build / ./build.sh，它们会走 Docker。

VERSION  ?= dev
# 阿里云个人版镜像仓库（推送前先 docker login $(REGISTRY)）
REGISTRY ?= crpi-z99l88o2fu3lae8l.cn-hangzhou.personal.cr.aliyuncs.com/maitux
IMAGE    ?= $(REGISTRY)/labgate
LDFLAGS := -s -w -X main.version=$(VERSION)
GO      ?= go

.PHONY: help
help: ## 显示可用目标
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## 编译当前平台的二进制到 dist/
	$(GO) build -trimpath -ldflags "$(LDFLAGS)" -o dist/labgate ./cmd/labgate
	$(GO) build -trimpath -ldflags "$(LDFLAGS)" -o dist/labbridge ./cmd/labbridge
	$(GO) build -trimpath -ldflags "-s -w" -o dist/fakebalance ./cmd/fakebalance
	$(GO) build -trimpath -ldflags "-s -w" -o dist/fakelims ./cmd/fakelims

.PHONY: test
test: ## 跑全部测试
	$(GO) test ./... -timeout 300s

.PHONY: race
race: ## 带竞态检测跑测试
	$(GO) test ./... -race -timeout 600s

.PHONY: vet
vet: ## 静态检查
	$(GO) vet ./...

.PHONY: fmt
fmt: ## 格式化
	gofmt -w .

.PHONY: cross
cross: ## 交叉编译三平台（需要本机有 Go）
	VERSION=$(VERSION) ./build.sh

.PHONY: docker-build
docker-build: ## 构建 Docker 镜像
	docker build --build-arg VERSION=$(VERSION) -t $(IMAGE):$(VERSION) .

.PHONY: docker-push
docker-push: ## 推送镜像到阿里云仓库（需先 docker login）
	docker push $(IMAGE):$(VERSION)

.PHONY: up
up: ## 起本机演示栈（模拟天平 + 网关 + 云端 NATS）
	docker compose up -d --build

.PHONY: down
down: ## 停演示栈
	docker compose down

.PHONY: logs
logs: ## 看网关日志
	docker compose logs -f labgate

.PHONY: clean
clean: ## 清理产物
	rm -rf dist data
