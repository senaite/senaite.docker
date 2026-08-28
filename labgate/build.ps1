<#
.SYNOPSIS
    构建 labgate 的各平台二进制（通过 Docker，本机无需安装 Go）。

.DESCRIPTION
    产物输出到 dist\：
        labgate-windows-amd64.exe / fakebalance-windows-amd64.exe
        labgate-linux-amd64       / fakebalance-linux-amd64
        labgate-linux-arm64       / fakebalance-linux-arm64

.PARAMETER Version
    写入二进制的版本号（labgate --version 可见），默认 dev。

.PARAMETER Platforms
    要构建的平台，默认三个都建。

.PARAMETER Test
    构建前先跑一遍测试。

.EXAMPLE
    .\build.ps1
.EXAMPLE
    .\build.ps1 -Version 1.0.0 -Test
.EXAMPLE
    .\build.ps1 -Platforms windows/amd64

.NOTES
    本文件必须保存为「带 BOM 的 UTF-8」。Windows PowerShell 5.1 会把没有 BOM
    的脚本按系统 ANSI 代码页解析，中文会变成乱码并导致语法错误。
#>
[CmdletBinding()]
param(
    [string]$Version = "dev",
    [string[]]$Platforms = @("windows/amd64", "linux/amd64", "linux/arm64"),
    [switch]$Test,
    [string]$GoImage = "golang:alpine",
    [string]$GoProxy = ""
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "找不到 docker。请先启动 Docker Desktop，或在装有 Go 的机器上直接用 go build。"
}

# 复用命名卷缓存模块与编译结果，第二次构建会快很多
foreach ($v in @("labgate-gomod", "labgate-gobuild")) {
    docker volume create $v | Out-Null
}

$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $dist | Out-Null

function Invoke-Go([string]$Script) {
    $dockerArgs = @(
        "run", "--rm",
        "-v", "${root}:/src",
        "-v", "labgate-gomod:/go/pkg/mod",
        "-v", "labgate-gobuild:/root/.cache/go-build",
        "-w", "/src",
        "-e", "CGO_ENABLED=0",
        "-e", "GOFLAGS=-buildvcs=false"
    )
    if ($GoProxy) { $dockerArgs += @("-e", "GOPROXY=$GoProxy") }
    $dockerArgs += @($GoImage, "sh", "-c", $Script)

    & docker @dockerArgs
    if ($LASTEXITCODE -ne 0) { throw "构建步骤失败（退出码 $LASTEXITCODE）" }
}

if ($Test) {
    Write-Host "==> 运行测试" -ForegroundColor Cyan
    Invoke-Go "go test ./... -timeout 300s"
}

Write-Host "==> 检查编译" -ForegroundColor Cyan
Invoke-Go "go vet ./..."

foreach ($platform in $Platforms) {
    $parts = $platform.Split("/")
    $os = $parts[0]
    $arch = $parts[1]
    $ext = if ($os -eq "windows") { ".exe" } else { "" }

    Write-Host "==> 构建 $platform" -ForegroundColor Cyan
    $ldflags = "-s -w -X main.version=$Version"
    $script = @"
set -e
GOOS=$os GOARCH=$arch go build -trimpath -ldflags '$ldflags' \
  -o dist/labgate-$os-$arch$ext ./cmd/labgate
GOOS=$os GOARCH=$arch go build -trimpath -ldflags '$ldflags' \
  -o dist/labbridge-$os-$arch$ext ./cmd/labbridge
GOOS=$os GOARCH=$arch go build -trimpath -ldflags '-s -w' \
  -o dist/fakebalance-$os-$arch$ext ./cmd/fakebalance
GOOS=$os GOARCH=$arch go build -trimpath -ldflags '-s -w' \
  -o dist/fakelims-$os-$arch$ext ./cmd/fakelims
"@
    Invoke-Go $script
}

Write-Host ""
Write-Host "构建完成，产物在 $dist" -ForegroundColor Green
Get-ChildItem $dist | Sort-Object Name | ForEach-Object {
    "{0,-40} {1,10:N1} MB" -f $_.Name, ($_.Length / 1MB)
}
Write-Host ""
Write-Host "Windows 上直接运行：" -ForegroundColor Yellow
Write-Host "  .\dist\labgate-windows-amd64.exe --config config.json"
