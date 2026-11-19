# Changelog

## 1.0.0

- 发布 GitHub / Gitee 源码入口，提供直接安装、持久菜单、curl 和 git clone 命令，加入自动化 CI 检查。
- OpenWrt / iStoreOS 专用 POSIX sh 菜单与命令行安装器。
- 精确匹配官方 LuCI Release 的 CPU / ABI 及 IPK / APK，校验附件大小与 SHA-256。
- LuCI + 中文 + 核心、无自建 Web 核心、仅 LuCI 三种模式。
- 配置备份 / 恢复、升级防降级、保留配置卸载、只读状态与版本查询。
- 顺序安装 LuCI 与语言包，避免上游重复语言初始化文件造成的 IPK 冲突。
- 补齐部分固件缺少的 timeout 命令，安装后核验实际软件包与核心版本。
- 加入失败路径回归、上游全附件核对与官方 rootfs 事务验证。
