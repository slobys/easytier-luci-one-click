#!/bin/sh
# EasyTier LuCI installer for OpenWrt / iStoreOS. POSIX sh / BusyBox ash.
set -eu
umask 077

SCRIPT_VERSION=1.0.0
REPO=EasyTier/luci-app-easytier
API=https://api.github.com/repos/$REPO
WEB=https://github.com/$REPO
ACTION=menu
CORE=easytier
TAG=latest
PROXY=${EASYTIER_DOWNLOAD_PROXY:-}
WORK=
LOCKED=0
RESTORE=0
BACKUP=
BOOT_STATE=none
PM=
ARCH=
LOCK=/tmp/et-luci-install.lock

say() { printf '%s\n' "$*"; }
warn() { printf '提示：%s\n' "$*" >&2; }
die() { printf '错误：%s\n' "$*" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }

usage() {
    cat <<'EOF'
EasyTier LuCI 一键安装 / 管理
  sh easytier.sh                     打开菜单
  sh easytier.sh --install           安装 / 升级 LuCI + 中文 + 核心
  sh easytier.sh --install --no-web  安装不含自建 Web 控制台的核心
  sh easytier.sh --luci-only         仅安装 LuCI 和中文包
  sh easytier.sh --check             查询匹配的正式 Release，不修改系统
  sh easytier.sh --status            查看安装及服务状态，不打印密钥
  sh easytier.sh --backup            备份配置到 /root/easytier-backups
  sh easytier.sh --uninstall         备份后卸载插件及核心（需要交互确认）
附加选项：
  --tag v2.6.4                       使用指定正式 Release
  --proxy https://your-proxy/        下载加速前缀（只用于 GitHub ZIP）
  --help                            显示帮助
默认使用 HTTPS 直连，不关闭证书检查；不添加软件源、不强制依赖、不自动启用组网。
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --install) ACTION=install ;;
        --luci-only) ACTION=install; CORE=none ;;
        --no-web) CORE=easytier-noweb ;;
        --check) ACTION=check ;;
        --status) ACTION=status ;;
        --backup) ACTION=backup ;;
        --uninstall) ACTION=uninstall ;;
        --tag) [ "$#" -ge 2 ] || die '--tag 缺少值'; TAG=$2; shift ;;
        --proxy) [ "$#" -ge 2 ] || die '--proxy 缺少值'; PROXY=$2; shift ;;
        --help|-h) usage; exit 0 ;;
        *) die "未知参数：$1（使用 --help）" ;;
    esac
    shift
done
case "$TAG" in latest) ;; v[0-9]*)
    printf '%s\n' "$TAG" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$' || die '版本格式应为 v数字.数字.数字' ;;
    *) die '版本格式应为 v数字.数字.数字' ;;
esac
case "$PROXY" in '') ;; https://?*) PROXY=${PROXY%/}/ ;; *) die '加速前缀必须使用 HTTPS' ;; esac

restore_config() {
    [ "$RESTORE" = 1 ] || return 0
    # Upstream prerm/postinst also move config: our persistent copy is authoritative.
    tar -xzf "$BACKUP/config.tar.gz" -C / || return 1
    RESTORE=0
}

restore_boot_state() {
    case "$BOOT_STATE" in
        enabled) /etc/init.d/easytier enable || return 1 ;;
        disabled) /etc/init.d/easytier disable || return 1 ;;
    esac
    BOOT_STATE=none
}

cleanup() {
    result=$?
    trap - EXIT HUP INT TERM
    if ! restore_config; then
        warn "配置恢复失败，请从 $BACKUP/config.tar.gz 手动恢复！"
        result=1
    fi
    if ! restore_boot_state; then warn '恢复原开机自启状态失败，请在 LuCI 核对。'; result=1; fi
    [ -z "$WORK" ] || rm -rf "$WORK"
    if [ "$LOCKED" = 1 ]; then
        rm -f "$LOCK/pid"
        rmdir "$LOCK" 2>/dev/null || :
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

detect() {
    if [ ! -f /etc/openwrt_release ] || ! has uci; then
        die '仅支持 OpenWrt / iStoreOS 等 OpenWrt 系统，请在软路由的 SSH 终端运行。'
    fi
    if [ -f /lib/apk/db/installed ] && has apk; then
        PM=apk
        ARCH=$(apk --print-arch)
        SDK=SNAPSHOT
        EXT=apk
    elif has opkg; then
        PM=opkg
        ARCH=$(opkg print-architecture | awk '$1=="arch" && $2!="all" && $2!="noarch" {if ($3>p) {p=$3; a=$2}} END {print a}')
        SDK=22.03.7
        EXT=ipk
    else
        die '未识别到 OpenWrt 原生 opkg 或 apk 软件包数据库。'
    fi
    [ -n "$ARCH" ] || die '软件包架构为空，停止安装。'
    printf '%s\n' "$ARCH" | grep -Eq '^[A-Za-z0-9_+-]+$' || die '软件包架构含异常字符。'
}

root_only() { [ "$(id -u)" = 0 ] || die '请使用 root 用户运行此操作。'; }

lock() {
    if ! mkdir "$LOCK" 2>/dev/null; then
        die "已有安装任务或遗留锁 $LOCK；确认没有其他任务后再手动移除。"
    fi
    LOCKED=1
    printf '%s\n' "$$" > "$LOCK/pid"
}

workspace() { WORK=$(mktemp -d /tmp/et-luci-install.XXXXXX) || die '无法创建临时目录。'; }

fetch() {
    url=$1
    dest=$2
    if has curl && curl -fL --connect-timeout 15 --max-time 300 --retry 2 \
        -A "easytier-oneclick/$SCRIPT_VERSION" -sS "$url" -o "$dest" && [ -s "$dest" ]; then
        return 0
    fi
    rm -f "$dest"
    if has wget && wget -T 60 -O "$dest" "$url" && [ -s "$dest" ]; then
        return 0
    fi
    rm -f "$dest"
    return 1
}

installed_version() {
    if [ "$PM" = opkg ]; then
        opkg status "$1" 2>/dev/null | awk '
            /^Version: / {v=$2} /^Status: / && / installed$/ {ok=1}
            END {if (ok) print v}'
    else
        awk -v name="$1" 'BEGIN {RS=""; FS="\n"}
            {p="";v="";for(i=1;i<=NF;i++) {
                if(substr($i,1,2)=="P:")p=substr($i,3)
                if(substr($i,1,2)=="V:")v=substr($i,3)
            } if(p==name)print v}' /lib/apk/db/installed
    fi
}

pm_install() {
    if [ "$PM" = opkg ]; then opkg install "$@"; else apk add "$@"; fi
}

update_indexes() {
    if "$PM" update; then :; else
        warn '部分软件源索引更新失败，将继续尝试已安装依赖 / 可用缓存；实际依赖安装失败会停止。'
    fi
}

prepare_tools() {
    has curl || has wget || die '需要 curl 或支持 HTTPS 的 wget。'
    has sha256sum || die '缺少 sha256sum，无法校验下载。'
    if ! has jsonfilter || ! has unzip; then
        pm_install ca-bundle jsonfilter unzip || die '基础工具安装失败，请检查固件软件源。'
    fi
    if ! has jsonfilter || ! has unzip; then die '基础工具不可用。'; fi
}

release_info() {
    has jsonfilter || die '只读查询需要 jsonfilter；安装命令会自动补齐，或先运行软件包管理器安装 jsonfilter。'
    endpoint=$API/releases/latest
    [ "$TAG" = latest ] || endpoint=$API/releases/tags/$TAG
    fetch "$endpoint" "$WORK/release.json" || die 'GitHub Release API 访问失败，请检查 DNS / HTTPS / API 限流。'
    RELEASE=$(jsonfilter -i "$WORK/release.json" -e '@.tag_name') || die 'Release JSON 无效。'
    printf '%s\n' "$RELEASE" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$' || die '上游 Release 版本格式不受支持。'
    [ "$(jsonfilter -i "$WORK/release.json" -e '@.draft')" = false ] || die '拒绝草稿 Release。'
    [ "$(jsonfilter -i "$WORK/release.json" -e '@.prerelease')" = false ] || die '拒绝预发布版本。'
    ASSET=EasyTier-$RELEASE-$ARCH-$SDK.zip
    selector="@.assets[@.name=\"$ASSET\"]"
    DOWNLOAD=$(jsonfilter -i "$WORK/release.json" -e "$selector.browser_download_url") || DOWNLOAD=
    DIGEST=$(jsonfilter -i "$WORK/release.json" -e "$selector.digest") || DIGEST=
    SIZE=$(jsonfilter -i "$WORK/release.json" -e "$selector.size") || SIZE=
    [ "$DOWNLOAD" = "$WEB/releases/download/$RELEASE/$ASSET" ] || die "上游没有匹配的 $ARCH / $EXT 正式包；不使用 uname 猜测或强制跨架构安装。"
    printf '%s\n' "$DIGEST" | grep -Eq '^sha256:[0-9a-f]{64}$' || die '上游缺少 SHA-256 摘要，停止下载。'
    case "$SIZE" in ''|*[!0-9]*) die '上游下载大小无效。' ;; esac
    say "包管理器：$PM | 软件包架构：$ARCH | Release：$RELEASE"
    say "匹配附件：$ASSET"
    say "来源：$WEB/releases/tag/$RELEASE"
}

free_space() {
    # Reserve space for ZIP + extracted packages and package manager transactions.
    tmp_need=$((SIZE * 2 / 1024 + 8192))
    tmp_free=$(df -Pk /tmp | awk 'END {print $4}')
    [ "$tmp_free" -ge "$tmp_need" ] || die "/tmp 空间不足：保守预留 ${tmp_need}KiB，可用 ${tmp_free}KiB。"
}

select_package() {
    pkg=$1
    if [ "$EXT" = ipk ]; then
        pattern="^${pkg}_[^/[:space:]_]+_(all|${ARCH})[.]ipk$"
    else
        pattern="^${pkg}-[0-9][^/[:space:]]*[.]apk$"
    fi
    selected=$(grep -E "$pattern" "$WORK/entries" || :)
    [ "$(printf '%s\n' "$selected" | awk 'NF{n++} END{print n+0}')" = 1 ] || die "ZIP 内 $pkg 包缺失或不唯一。"
    case "$selected" in *..*|*/*|*\\*) die '拒绝不安全的包文件名。' ;; esac
    unzip -p "$WORK/release.zip" "$selected" > "$WORK/$selected" || die "无法解压 $pkg。"
    [ -s "$WORK/$selected" ] || die "$pkg 包为空。"
    if [ "$EXT" = ipk ]; then
        expected=${selected#"${pkg}_"}
        expected=${expected%_all.ipk}
        expected=${expected%_"${ARCH}".ipk}
    else
        expected=${selected#"${pkg}-"}; expected=${expected%.apk}
    fi
    old=$(installed_version "$pkg")
    if [ -n "$old" ] && [ "$old" != "$expected" ]; then
        if [ "$PM" = opkg ]; then
            opkg compare-versions "$old" '>' "$expected" && die "$pkg 当前 $old 高于 $expected，拒绝降级。"
        else
            [ "$(apk version -t "$old" "$expected")" != '>' ] || die "$pkg 当前 $old 高于 $expected，拒绝降级。"
        fi
    fi
    printf '%s\t%s\t%s\n' "$pkg" "$expected" "$WORK/$selected" >> "$WORK/packages"
}

backup_config() {
    mkdir -p /root/easytier-backups
    BACKUP=$(mktemp -d "/root/easytier-backups/$(date +%Y%m%d-%H%M%S).XXXXXX")
    set --
    [ ! -e /etc/config/easytier ] || set -- "$@" etc/config/easytier
    [ ! -d /etc/easytier ] || set -- "$@" etc/easytier
    if [ "$#" = 0 ]; then rmdir "$BACKUP"; BACKUP=; return 0; fi
    tar -czf "$BACKUP/config.tar.gz" -C / "$@" || die '配置备份失败，停止操作。'
    say "配置备份：$BACKUP/config.tar.gz（可能包含组网密钥，请勿公开）"
}

install_packages() {
    root_only
    lock
    workspace
    update_indexes
    prepare_tools
    if [ "$CORE" != none ] && ! has timeout; then
        pm_install coreutils-timeout || die '无法安装核心核验所需的 coreutils-timeout。'
    fi
    release_info
    if [ -e /tmp/easytier_backup ] || [ -e /tmp/et_config_backup ]; then
        die '存在上游遗留配置备份 /tmp/easytier_backup 或 /tmp/et_config_backup，请先核对并移走，避免安装包自动恢复旧配置。'
    fi
    if [ "$CORE" != none ]; then
        other=easytier-noweb
        [ "$CORE" != easytier-noweb ] || other=easytier
        [ -z "$(installed_version "$other")" ] || die "已安装 $other，不能覆盖安装 $CORE；请选择原核心模式，或使用 --luci-only。"
    fi
    free_space
    say '下载并校验官方 ZIP…'
    fetch "${PROXY}${DOWNLOAD}" "$WORK/release.zip" || die '下载失败；可以通过 --proxy 指定自己的 HTTPS 加速前缀。'
    [ "$(wc -c < "$WORK/release.zip" | tr -d ' ')" = "$SIZE" ] || die '附件长度不匹配。'
    actual=$(sha256sum "$WORK/release.zip" | awk '{print $1}')
    [ "$actual" = "${DIGEST#sha256:}" ] || die 'SHA-256 校验失败，拒绝安装。'
    unzip -l "$WORK/release.zip" > "$WORK/zip-list" || die 'ZIP 目录无效。'
    awk '$1 ~ /^[0-9]+$/ && $3 ~ /^[0-9][0-9]:[0-9][0-9]$/ {print $4}' "$WORK/zip-list" > "$WORK/entries"
    : > "$WORK/packages"
    [ "$CORE" = none ] || select_package "$CORE"
    select_package luci-app-easytier
    select_package luci-i18n-easytier-zh-cn
    root_need=$(( $(awk -F '\t' '{print $3}' "$WORK/packages" | xargs wc -c | awk 'END {print $1}') * 2 / 1024 + 8192 ))
    root_free=$(df -Pk /usr | awk 'END {print $4}')
    [ "$root_free" -ge "$root_need" ] || die "存储空间不足：保守预留 ${root_need}KiB，可用 ${root_free}KiB；可选择 --no-web 或 --luci-only。"
    # Kernel modules and Lua compatibility must come from the firmware's own feeds.
    pm_install kmod-tun luci-compat || die '依赖安装失败；请检查固件版本与软件源、内核 ABI 是否匹配，脚本不会 force-depends。'
    backup_config
    [ -z "$BACKUP" ] || RESTORE=1
    if [ -x /etc/init.d/easytier ]; then
        if /etc/init.d/easytier enabled; then BOOT_STATE=enabled; else BOOT_STATE=disabled; fi
    fi
    tab=$(printf '\t')
    say '安装选定软件包（APK 仅对本次已校验的本地附件使用 --allow-untrusted）…'
    # Configure LuCI before i18n: both upstream packages contain the same
    # self-deleting uci-defaults language initializer. One transaction clashes.
    while IFS="$tab" read -r name version file; do
        if [ "$PM" = opkg ]; then
            opkg install "$file" || die "$name 安装失败；原配置将恢复，软件包本身不自动回滚。"
        else
            apk add --allow-untrusted "$file" || die "$name 安装失败；原配置将恢复，软件包本身不自动回滚。"
        fi
    done < "$WORK/packages"
    restore_config || die "配置恢复失败，备份位于 $BACKUP。"
    restore_boot_state || die '恢复原开机自启状态失败。'
    while IFS="$tab" read -r name version file; do
        got=$(installed_version "$name")
        [ "$got" = "$version" ] || die "$name 安装核对失败：期望 $version，实际 ${got:-未注册}。"
    done < "$WORK/packages"
    if [ ! -x /etc/init.d/easytier ] || [ ! -f /usr/lib/lua/luci/controller/easytier.lua ]; then
        die 'LuCI 或服务文件缺失。'
    fi
    if [ "$CORE" != none ]; then
        has timeout || die '缺少 timeout，无法完成核心运行核验。'
        output=$(timeout 15 /usr/bin/easytier-core --version 2>&1) || die '核心 --version 执行失败；包已安装，请核查 CPU 指令集兼容性。'
        reported=$(printf '%s\n' "$output" | awk 'NR==1 {print $2}')
        case "$reported" in "${RELEASE#v}"|"${RELEASE#v}"-*) ;; *) die '核心版本与所选 Release 不匹配。' ;; esac
        say "核心运行核验：$output"
    fi
    rm -f /tmp/luci-indexcache
    say '安装完成。重新登录 LuCI，进入「VPN → EasyTier」。'
    say '脚本不写入组网、网络、防火墙或 DNS 配置；首次安装保持上游默认未启用。'
    say '注意：包管理器会执行上游服务钩子，升级已启用的实例可能重启服务；请在 LuCI 核验状态。'
    [ "$CORE" != none ] || say '此模式未安装核心，请在「上传程序」中配置程序路径并上传对应二进制。'
}

status() {
    say "脚本：$SCRIPT_VERSION | $PM | $ARCH"
    for p in easytier easytier-noweb luci-app-easytier luci-i18n-easytier-zh-cn; do
        v=$(installed_version "$p"); say "$p: ${v:-未安装}"
    done
    if [ -x /etc/init.d/easytier ]; then /etc/init.d/easytier status || :; fi
    if [ -c /dev/net/tun ]; then say 'TUN 设备：存在'; else warn 'TUN 设备不存在；安装 kmod-tun 后仍需核对本机内核。'; fi
    say 'LuCI 路径：/cgi-bin/luci/admin/vpn/easytier'
}

uninstall() {
    root_only
    [ -t 0 ] || die '卸载必须在交互终端确认，请直接运行脚本菜单。'
    say '将备份并卸载 EasyTier 的 LuCI、语言包和核心；停止该服务，保留依赖及原配置。'
    printf '输入 REMOVE 确认：'; read -r reply
    [ "$reply" = REMOVE ] || { say '已取消。'; return 0; }
    lock
    backup_config
    [ -z "$BACKUP" ] || RESTORE=1
    if [ -x /etc/init.d/easytier ]; then
        /etc/init.d/easytier stop || die '服务停止失败，未继续卸载。'
        /etc/init.d/easytier disable || die '取消自启失败，未继续卸载。'
    fi
    for p in luci-i18n-easytier-zh-cn luci-app-easytier easytier-noweb easytier; do
        [ -n "$(installed_version "$p")" ] || continue
        if [ "$PM" = opkg ]; then opkg remove "$p"; else apk del "$p"; fi
        [ -z "$(installed_version "$p")" ] || die "$p 仍有安装记录。"
    done
    restore_config || die '卸载后恢复配置失败。'
    rm -f /tmp/luci-indexcache
    say '卸载完成；配置与持久备份已保留。'
}

menu() {
    [ -t 0 ] || { usage; die '菜单需要交互终端；请先下载脚本再运行，或使用 --install。'; }
    cat <<'EOF'
EasyTier LuCI 管理菜单
1. 安装 / 升级（LuCI + 中文 + 核心）
2. 仅安装 / 升级 LuCI + 中文
3. 查询正式 Release 与架构支持
4. 查看安装 / 服务状态
5. 备份配置
6. 卸载（保留配置，二次确认）
7. 安装 / 升级不含自建 Web 控制台的核心 + LuCI + 中文
0. 退出
EOF
    printf '请选择 [0-7]：'; read -r choice
    case "$choice" in
        1) install_packages ;;
        2) CORE=none; install_packages ;;
        3) workspace; release_info ;;
        4) status ;;
        5) root_only; lock; backup_config ;;
        6) uninstall ;;
        7) CORE=easytier-noweb; install_packages ;;
        0) exit 0 ;;
        *) die '无效选项。' ;;
    esac
}

detect
case "$ACTION" in
    install) install_packages ;;
    check) workspace; release_info ;;
    status) status ;;
    backup) root_only; lock; backup_config ;;
    uninstall) uninstall ;;
    menu) menu ;;
esac
