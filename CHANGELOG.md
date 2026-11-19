# Changelog

## 1.0.1

- 修复 APK 固件的架构识别：优先读取 `/etc/apk/arch`，缺失时读取 `DISTRIB_ARCH`，最后才使用 APK 编译架构。
- 解决 iStoreOS / Rockchip 上 `apk --print-arch` 返回 `aarch64`、包 ABI 实为 `aarch64_generic` 导致选包失败的问题；不强制跨架构、不改固件架构配置。
- 增加配置优先级、缺失回退、异常值拒绝和 ARM 完整检测链路回归。

## 1.0.0

- 发布 GitHub / Gitee 源码入口，提供直接安装、持久菜单、curl 和 git clone 命令，加入自动化 CI 检查。
- OpenWrt / iStoreOS 专用 POSIX sh 菜单与命令行安装器。
- 精确匹配官方 LuCI Release 的 CPU / ABI 及 IPK / APK，校验附件大小与 SHA-256。
- LuCI + 中文 + 核心、无自建 Web 核心、仅 LuCI 三种模式。
- 配置备份 / 恢复、升级防降级、保留配置卸载、只读状态与版本查询。
- 顺序安装 LuCI 与语言包，避免上游重复语言初始化文件造成的 IPK 冲突。
- 补齐部分固件缺少的 timeout 命令，安装后核验实际软件包与核心版本。
- 加入失败路径回归、上游全附件核对与官方 rootfs 事务验证。
