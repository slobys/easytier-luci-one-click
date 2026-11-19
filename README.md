# EasyTier LuCI 一键安装脚本

在 OpenWrt、iStoreOS 等 OpenWrt 系统中安装 [EasyTier 官方 LuCI](https://github.com/EasyTier/luci-app-easytier)。脚本使用 POSIX sh，可在 BusyBox ash 下运行。

## 快速开始

SSH 登录软路由，以 root 执行。**一条命令直接安装 LuCI + 中文语言包 + EasyTier 核心：**

```sh
wget -O /tmp/easytier-install.sh https://raw.githubusercontent.com/slobys/easytier-luci-one-click/main/easytier.sh && test -s /tmp/easytier-install.sh && sh /tmp/easytier-install.sh --install
```

**推荐：安装管理菜单，以后输入 `easytier-menu` 即可使用：**

```sh
wget -O /tmp/easytier-menu.new https://raw.githubusercontent.com/slobys/easytier-luci-one-click/main/easytier.sh && test -s /tmp/easytier-menu.new && sh -n /tmp/easytier-menu.new && chmod +x /tmp/easytier-menu.new && mv /tmp/easytier-menu.new /usr/bin/easytier-menu && easytier-menu
```

菜单选 `1` 完整安装，选 `2` 只装 LuCI。直接安装命令将 `--install` 改为 `--luci-only` 也可只装界面。后续完整升级可运行 `easytier-menu --install`；更新菜单程序本身时重新执行上述下载命令。

已有 curl 时，也可安装管理菜单：

```sh
curl -fL --connect-timeout 15 --max-time 300 https://raw.githubusercontent.com/slobys/easytier-luci-one-click/main/easytier.sh -o /tmp/easytier-menu.new && test -s /tmp/easytier-menu.new && sh -n /tmp/easytier-menu.new && chmod +x /tmp/easytier-menu.new && mv /tmp/easytier-menu.new /usr/bin/easytier-menu && easytier-menu
```

### 国内入口（Gitee）

项目源码同步至 [Gitee](https://gitee.com/naiyou88/easytier-luci-one-click)。若所在网络可以访问 Gitee raw，可用以下菜单命令：

```sh
wget -O /tmp/easytier-menu.new https://gitee.com/naiyou88/easytier-luci-one-click/raw/main/easytier.sh && test -s /tmp/easytier-menu.new && sh -n /tmp/easytier-menu.new && chmod +x /tmp/easytier-menu.new && mv /tmp/easytier-menu.new /usr/bin/easytier-menu && easytier-menu
```

Gitee 一条命令直接安装：

```sh
wget -O /tmp/easytier-install.sh https://gitee.com/naiyou88/easytier-luci-one-click/raw/main/easytier.sh && test -s /tmp/easytier-install.sh && sh /tmp/easytier-install.sh --install
```

Gitee 下载入口可能因网络或站点限制返回 403；源码同步不等于 raw 一定可下载。遇到下载失败请使用上方 GitHub 入口或下方克隆 / 上传方式。Gitee 只镜像本安装器源码，插件附件与 Release API 仍来自 EasyTier 官方 GitHub，**不代表插件安装全过程无需访问 GitHub**。

### 克隆或离线使用

```sh
git clone https://github.com/slobys/easytier-luci-one-click.git && cd easytier-luci-one-click && sh easytier.sh
```

也可以把仓库中的 `easytier.sh` 上传到软路由 `/tmp`，执行 `sh /tmp/easytier.sh`。下文命令以此路径为例；使用已安装菜单时，把 `sh /tmp/easytier.sh` 换为 `easytier-menu`。

安装后，重新登录路由器后台，进入 **VPN → EasyTier**。完整安装可以直接配置网络名称、密钥和节点；仅 LuCI 模式需要在「上传程序」中另行配置 / 上传核心。首次安装不填入组网参数，不自动启用组网。

## 常用命令

```sh
# 查询最新正式 Release、当前架构是否有对应附件（只读，需要 jsonfilter）
sh /tmp/easytier.sh --check

# 安装 / 升级；已有配置先备份，并在操作后恢复
sh /tmp/easytier.sh --install

# 不带「自建 Web 控制台」的核心，仍然包含 LuCI 网页管理
sh /tmp/easytier.sh --install --no-web

# 指定正式 Release；不会自动降级已有较新版本
sh /tmp/easytier.sh --install --tag v2.6.4

# 只升级界面与中文包，不碰已安装或手动上传的核心
sh /tmp/easytier.sh --luci-only

# 查看版本 / 服务状态，不输出网络密钥
sh /tmp/easytier.sh --status

# 备份配置，目录权限限制为当前用户可访问
sh /tmp/easytier.sh --backup

# 交互确认后停止服务、卸载插件及核心，保留配置与依赖
sh /tmp/easytier.sh --uninstall
```

`easytier` 与 `easytier-noweb` 不能共存。升级时选择原来的核心类型；脚本不会擅自卸载 / 切换类型。

完整安装的核心版本核验针对 `/usr/bin/easytier-core`。已有配置若指向其他目录，会保留原路径，不会替换外置核心；这种情况建议使用 `--luci-only`，并在 LuCI「上传程序」中管理外置核心。

## 下载与软件源

- 以该 LuCI 仓库的**正式 Release** 为准，不使用源码里的版本号推测下载地址。核对时最新为 `v2.6.4`，源码中的 `2.7.0` 尚无对应正式附件。
- `opkg` 精确匹配 `22.03.7.zip` 附件内的 IPK；`apk` 精确匹配 `SNAPSHOT.zip` 内的 APK。这里是上游附件的命名，不表示必须使用这两个版本的固件。
- 使用软件包管理器报告的架构，不根据 `uname -m` 猜 ABI，不强制安装相近架构。
- HTTPS 证书检查始终开启；验证 GitHub API 公布的 ZIP 大小与 SHA-256。若 API 不可达、限流、缺摘要，明确停止，不降级为猜链接下载。
- 默认 GitHub 直连，不内置未经选择的第三方镜像。可通过 `--proxy` 或 `EASYTIER_DOWNLOAD_PROXY` 提供自己的 HTTPS 下载加速前缀，它只作用于 ZIP 下载，API 仍直连。加速服务必须支持「前缀 + 完整 GitHub URL」。
- `kmod-tun`、`luci-compat` 及其依赖只从固件自己的现有软件源安装。不修改软件源、不跳过内核 ABI 校验、不替换 DNS。必要时补装 `ca-bundle`、`jsonfilter`、`unzip`；核心核验需要 `timeout`，缺少时补装 `coreutils-timeout`。
- 上游 APK 附件不是本机信任密钥签名的 feed 包，按上游方法，仅在校验后对本次本地 APK 使用 `--allow-untrusted`；不修改系统全局信任设置。SHA-256 校验不等同于独立发布者签名验证。

请勿使用 `wget ... | sh` 打开交互菜单，管道会占用标准输入。先下载 / 上传文件，再执行。

## 配置、失败处理与恢复

- 备份 `/etc/config/easytier` 和整个 `/etc/easytier/` 到 `/root/easytier-backups/时间.随机后缀/config.tar.gz`，备份可能含密钥，不要公开。
- 升级已有安装时，恢复原来的开机自启开关；这不等于保证升级期间运行状态不变。
- 安装 / 卸载失败也尽可能恢复原配置；**不保证软件包事务原子性，不自动回滚二进制或依赖**。按错误提示修复原因后重新运行。
- 升级已启用的实例时，上游包的安装 / 卸载钩子可能停止或重新启动服务；不能承诺无中断升级。脚本自身不生成组网、防火墙、路由或 DNS 配置。首次安装使用上游 `enabled=0`、`web_enabled=0`。
- 上游遗留的 `/tmp/easytier_backup`、`/tmp/et_config_backup` 会被上游安装钩子自动恢复。脚本遇到这两个路径会先停止，请核对并移走，避免旧配置覆盖。
- 使用独占锁与专用临时目录。遇到已有锁时停止，不删除其他安装任务的文件；确认没有安装进程后，才手动处理遗留 `/tmp/et-luci-install.lock`。
- 核验软件包数据库中的实际版本、LuCI 控制器、服务文件，完整安装还执行核心 `--version`。这不表示已经完成真实组网连通性验证。

手动恢复备份（将示例路径替换为你的真实备份路径；恢复会覆盖对应 EasyTier 配置）：

```sh
tar -tzf /root/easytier-backups/你的备份目录/config.tar.gz
tar -xzf /root/easytier-backups/你的备份目录/config.tar.gz -C /
```

恢复后按需在 LuCI 中重启 EasyTier。脚本不会自动重启整个网络或路由器。

## 兼容性与验证

详见 [验证报告](docs/validation.md)、[全部上游附件记录](docs/upstream-assets.json) 和 [官方固件安装记录](docs/firmware-smoke.json)。没有匹配包的 CPU / ABI 会明确停止，不等同于已经验证所有 OpenWrt 固件。

测试脚本位于 `tests/`：

```sh
# CI 同款：下载经过固定 SHA-256 验证的官方 rootfs，取真实 jsonfilter 跑 sh/ash 回归
python3 tests/run_ci.py

# 验证 README 的下载命令，不会把下载失败或空文件当作执行成功
python3 tests/test_entrypoints.py

# jsonfilter 必须可执行；也可指定包装了官方 musl loader 的 JSONFILTER_BIN
python3 tests/test_installer.py
TEST_SHELL='busybox ash' python3 tests/test_installer.py
```

`audit_upstream.py` 逐一校验全部上游附件与包元数据，并用宿主机 / QEMU user 执行核心版本命令；`firmware_smoke.py` 在官方 x86_64 rootfs 中测试实际安装、升级和配置保留。后者使用已校验的 GitHub 附件缓存和真实固件软件源，需要 Docker，详细参数见 `--help`。这些脚本不操作你的软路由。

## 许可证

本安装脚本以 MIT 许可证发布。EasyTier、LuCI 和上游软件包各自遵循原项目许可证；本项目不分发这些二进制。
