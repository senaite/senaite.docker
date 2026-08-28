#!/bin/bash
#
# 自动生成 buildout 的客户 add-on 配置 custom-addon.cfg。
#
# 每次容器启动（docker-entrypoint.sh）先删掉旧文件，再按 /opt/addons/customers
# 里"实际存在"的 add-on 重新写一份，所以：
#
#   1. 部署人员不用手写这个文件（写错/漏项是最常见的部署事故）
#   2. 物理删掉某个 add-on 目录不再需要同步改 cfg —— 遍历不到就不会写进去，
#      不会再出现 buildout 报错 → 容器无限重启
#
# 生成的文件是一个"叶子"配置：由 buildout.cfg 的 extends 引入，本身不 extends
# 任何东西。这一点刻意和历史上手工维护的版本保持一致 —— extends 的层级决定了
# += 的合并结果，换位置会静默改变有效配置。也因此：即使没有任何客户 add-on，
# 也必须生成一个空壳文件，否则 buildout.cfg 的 extends 找不到文件会直接失败。
#
# 生成规则（依据 addons/customers/SENAITE-Addon开发规则.md）：
#
#   - 只有"带 setup.py 的一级子目录"才算 add-on。空壳目录、xlsx、md 一律跳过。
#   - egg 名一律从 setup.py 的 name= 读，不用目录名：两者可以不一致
#     （目录 maitux.oauth2.0 的 egg 名是 maitux.oauth2）。
#
#   - [instance] zcml 为【每个有 configure.zcml 的包】都写一条。这一条是保守选择：
#     它精确复现了 2026-08 之前长期跑通的那份手工配置，而不是去猜哪些可以省。
#
#     加载时机（parts/instance/etc/site.zcml 的顺序）：
#         <include files="package-includes/*-configure.zcml" />   <- 显式 slug 在这里
#         <five:loadProducts />                                   <- CMFPlone 在这里，
#                                                                    autoinclude 也在这里
#     显式 slug 走前面那个独立阶段，顺序确定，不受 autoinclude 内部排序影响。
#
#     注意：两种方式都【不保证】排在 senaite.core 之后。2026-08-28 实测，无论只留
#     必要条目还是写全 20 条，maitux.audittrail 都会
#         ComponentLookupError: (IPermission, 'senaite.core.permissions.ViewLogTab')
#     真正的修法在 addon 自己：ZCML 里引用了 senaite.core 权限的包，必须在自己的
#     configure.zcml 里 <include package="senaite.core.permissions" />（R1 的另一种
#     写法，maitux.esignature / maitux.instrument_acquisition 一直就是这么写的）。
#     所以这里写全，只是为了和历史配置一致，不要指望它能兜住权限顺序问题。

#   - 带 overrides.zcml 的包额外补一条 <egg>-overrides slug（R2 / R5b）。
#
#   - 不写 [plonesite] profiles：buildout.cfg 里 profiles 是普通赋值
#     （profiles = senaite.lims:default），extends 链上层优先级最高，在这里
#     追加会被整个丢掉（实测 buildout annotate 确认：加与不加，有效值都只有
#     senaite.lims:default）。客户 add-on 的 profile 一律在站点后台手工安装。
#
#   - [instance] initialization = import pkg_resources 照写一份，缺了它
#     collective.recipe.plonesite 用 `bin/instance run` 建站的子进程看不到
#     eggs 里的 zope.* 命名空间包，建站静默失败、站点 404（见 buildout.cfg 注释）。
#
set -euo pipefail

# 排序结果必须稳定
export LC_ALL=C

ADDONS_DIR=${ADDONS_DIR:-/opt/addons/customers}
CFG=${CFG:-/home/senaite/senaitelims/custom-addon.cfg}

log() { echo "[gen-custom-addon] $*"; }

# 需求：每次先删除，再自动创建
rm -f "$CFG"

# 只有一个 [buildout] 空段的空壳配置：没有客户 add-on 时用它占位，
# 让 buildout.cfg 的 extends 有文件可读。
write_stub() {
    {
        echo "# 本文件由 /gen-custom-addon.sh 在容器启动时自动生成，请勿手工修改。"
        echo "# 当前 ${ADDONS_DIR} 下没有任何可用的 add-on（没有带 setup.py 的一级子目录），"
        echo "# 所以这里是空的。放一个 add-on 目录进去并重启容器即可自动生效。"
        echo ""
        echo "[buildout]"
    } > "$CFG"
    chown senaite:senaite "$CFG" 2>/dev/null || true
}

if [ ! -d "$ADDONS_DIR" ]; then
    log "$ADDONS_DIR 不存在，写入空壳 $(basename "$CFG")"
    write_stub
    exit 0
fi

# 从 setup.py 里取 egg 分发名（name=）
egg_name() {
    local setup_py=$1 name
    # 常见写法：缩进一层的 name="xxx", / name='xxx',
    name=$(sed -n "s/^[[:space:]]*name[[:space:]]*=[[:space:]]*[\"']\([^\"']*\)[\"'].*/\1/p" \
           "$setup_py" | head -n 1)
    if [ -z "$name" ]; then
        # 兜底：setup(name="xxx", ...) 写在同一行
        name=$(grep -oE "name[[:space:]]*=[[:space:]]*[\"'][^\"']+[\"']" "$setup_py" \
               | head -n 1 | sed "s/.*[\"']\([^\"']*\)[\"']/\1/")
    fi
    printf '%s' "$name"
}

# 按【分发名】拼出代码目录，再看某个 zcml 在不在。
# 必须按分发名拼、不能用 find：slug 生成的是 <include package="<分发名>" />，
# 能不能 import 到取决于分发名与真实目录大小写是否一致（R5c）。
# 逐级用 ls 做精确（区分大小写）匹配。不能直接 [ -f ]：宿主是 Windows 时
# 绑定挂载的文件系统大小写不敏感，INNOCARE/Reportdesign 会假装存在，
# R5c 那个大小写陷阱就查不出来了。
exact_path() {
    local root=$1 cur=$1 rest=$2 part
    while [ -n "$rest" ]; do
        part=${rest%%/*}
        case "$rest" in
            */*) rest=${rest#*/} ;;
            *)   rest="" ;;
        esac
        [ -n "$part" ] || continue
        ls -1a "$cur" 2>/dev/null | grep -qxF -- "$part" || return 1
        cur="$cur/$part"
    done
    [ -e "$cur" ]
}


has_zcml() {
    local dir=$1 egg=$2 fname=$3 rel base
    rel=$(printf '%s' "$egg" | tr '.' '/')
    for base in "src/$rel" "$rel"; do
        if exact_path "$dir" "$base/$fname"; then
            return 0
        fi
    done
    return 1
}

# 兜底探测：包里到底有没有这个 zcml（不管大小写对不对）
any_zcml() {
    local dir=$1 fname=$2
    find "$dir" -maxdepth 5 -name "$fname" \
        -not -path "*egg-info*" -not -path "*/tests/*" -print -quit 2>/dev/null
}

develop_lines=""
eggs_lines=""
zcml_lines=""
count=0

shopt -s nullglob
for path in "$ADDONS_DIR"/*/; do
    path=${path%/}
    dir=$(basename "$path")

    if [ ! -f "$path/setup.py" ]; then
        log "跳过 $dir：没有 setup.py（不是一个可用的 add-on）"
        continue
    fi

    egg=$(egg_name "$path/setup.py")
    if [ -z "$egg" ]; then
        log "跳过 $dir：setup.py 里读不到 name=，无法确定 egg 名"
        continue
    fi

    develop_lines="${develop_lines}    ${ADDONS_DIR}/${dir}"$'\n'
    eggs_lines="${eggs_lines}    ${egg}"$'\n'

    note=""
    if has_zcml "$path" "$egg" configure.zcml; then
        zcml_lines="${zcml_lines}    ${egg}"$'\n'
        note="zcml"
    elif [ -n "$(any_zcml "$path" configure.zcml)" ]; then
        note="仅 autoinclude！分发名 $egg 与代码目录大小写不一致，显式 include 会重复注册（R5c）"
    else
        note="无 configure.zcml"
    fi

    if has_zcml "$path" "$egg" overrides.zcml; then
        zcml_lines="${zcml_lines}    ${egg}-overrides"$'\n'
        note="${note} + overrides"
    fi

    count=$((count + 1))
    log "收录 $dir -> $egg ($note)"
done
shopt -u nullglob

if [ "$count" -eq 0 ]; then
    log "$ADDONS_DIR 下没有任何 add-on，写入空壳 $(basename "$CFG")"
    write_stub
    exit 0
fi

{
    echo "# 本文件由 /gen-custom-addon.sh 在容器启动时自动生成，请勿手工修改："
    echo "# 每次启动都会先删除再重新生成，改动会丢失。"
    echo "# 要增删客户 add-on，直接增删 ${ADDONS_DIR} 下的目录即可。"
    echo ""
    echo "[buildout]"
    echo "develop +="
    printf '%s' "$develop_lines"
    echo ""
    echo "eggs +="
    printf '%s' "$eggs_lines"
    echo ""
    echo "[instance]"
    echo "# 修复建站失败：pip 装进 site-packages 的 zope.* 带的 *-nspkg.pth 会在"
    echo "# 解释器启动时往 sys.modules 塞一个只含 site-packages 路径的假 zope 模块，"
    echo "# eggs 里的 zope.processlifetime 因此不可见。buildout 自动建站走的"
    echo "# \`bin/instance run\` 子进程不 import pkg_resources，于是静默失败："
    echo "# buildout 不报错、实例照常启动，但站点没建出来，/<站点id> 返回 404。"
    echo "initialization ="
    echo "    import pkg_resources"
    if [ -n "$zcml_lines" ]; then
        echo "# 每个有 configure.zcml 的包都必须显式 include：只靠 autoinclude 会和"
        echo "# senaite.core 挤在同一批加载，引用 senaite.core 权限的注册会"
        echo "# ComponentLookupError 让整站起不来（详见 /gen-custom-addon.sh 顶部注释）。"
        echo "zcml +="
        printf '%s' "$zcml_lines"
    fi
} > "$CFG"

chown senaite:senaite "$CFG" 2>/dev/null || true

log "已生成 $CFG（$count 个 add-on）："
sed 's/^/    | /' "$CFG"
