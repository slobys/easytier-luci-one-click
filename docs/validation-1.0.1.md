# v1.0.1：APK 架构识别修复验证

日期：2026-11-19。修复 `aarch64 / apk` 无匹配包的用户反馈。

## 根因与修复

旧脚本直接使用 `apk --print-arch`。这个选项打印 APK 的编译架构 `APK_DEFAULT_ARCH`，不一定是 OpenWrt 配置的包 ABI。在原版 OpenWrt / iStoreOS 的 Rockchip ARM 镜像中，实际结果均为：

```text
apk --print-arch       → aarch64
/etc/apk/arch          → aarch64_generic
DISTRIB_ARCH           → aarch64_generic
固件基础软件源路径     → packages/aarch64_generic/
EasyTier 附件          → EasyTier-v2.6.4-aarch64_generic-SNAPSHOT.zip
```

新脚本优先读取 `/etc/apk/arch`；文件缺失或为空时读取 `/etc/openwrt_release` 中的 `DISTRIB_ARCH`，最后才回退编译架构。不会把所有 `aarch64` 强制换成 generic，不修改固件架构文件，不使用 `--arch` 或强制跨架构安装。`opkg` 检测保持原逻辑。

参考 APK 实现：[--print-arch](https://github.com/alpinelinux/apk-tools/blob/master/src/apk.c) 与 [数据库读取 etc/apk/arch](https://github.com/alpinelinux/apk-tools/blob/master/src/database.c)。镜像身份、安装器散列和原始来源见 [JSON 记录](validation-1.0.1.json)。

## 回归结果

- 修复前，用真实 jsonfilter、配置架构 generic、APK 编译架构 aarch64，复现用户同样的拒绝选包错误：[红灯日志](logs/v1.0.1/red.log)。
- 修复后，sh / BusyBox ash 各 32 项通过：[回归日志](logs/v1.0.1/ci.log)。
- 原有 44 个附件选择器的测试已改为走完整 `detect → release_info`，不再只手动赋值 ARCH 后测试选包。
- 新增配置优先级、DISTRIB_ARCH 回退、x86 最终回退、裸 ARM 不猜测、缺失精确包拒绝、异常值不执行等场景。
- README 五个下载命令的成功、失败、空文件、无效 Shell 共 20 个子场景通过：[入口日志](logs/v1.0.1/entrypoints.log)。
- Shell 语法、ShellCheck、源文件 SHA-256 与 diff 检查通过。

## ARM 原始固件验证

| 原始固件 | 检测/精确选包 | 完整安装及核心版本命令 | 重复安装/配置散列/原自启禁用 |
| --- | --- | --- | --- |
| OpenWrt 25.12.6 Rockchip NanoPi R2S | 通过 | 通过 | 通过 |
| iStoreOS 25.12.6 2026110611 Rockchip R4S | 通过 | 通过 | 通过 |

两套镜像均从官方目录下载并核对官方 SHA-256，保留各自原始 rootfs、APK 数据库和软件源。原版 iStoreOS 的架构与用户反馈相同，但不代表已识别用户的具体硬件型号。

实际安装 `easytier 2.6.4`、`luci-app-easytier 2.6.4-r1` 和对应中文包，安装后核对数据库版本，执行 `easytier-core --version` 得到 `2.6.4-8428a89d`。随后写入测试标记、禁用 init 自启、重复安装，验证 UCI/TOML 散列与自启禁用状态。日志：[OpenWrt](logs/v1.0.1/openwrt-arm.log)、[iStoreOS](logs/v1.0.1/istoreos-arm.log)。

测试在 x86 Docker 中使用 QEMU user / PRoot 执行 ARM 原生包管理器与安装器。依赖由安装器预备阶段从固件源安装，随后完成插件安装与重复安装。GitHub 的 wget 下载使用已验证摘要的原始附件/API 缓存，不声称已验证用户网络上的端到端下载。

### 测试环境调整

这些是模拟环境的准备，不是对用户系统或产品脚本的修改：

- 解压固件 SquashFS，不创建设备节点；在容器中绑定 `/dev`、`/proc`、`/sys`，准备启动时常见的 `/tmp/log`、`/tmp/run`、`/tmp/lock` 及 DNS 文件。
- 旧版 PRoot 对 APK 的 access 检查和 fd 相对路径存在不一致。最初出现「文件存在但被当成包名」「日志目录缺失」「缓存只读」等模拟器故障。用同一隔离工作目录同时挂载至容器的 `/tmp` 和 `/target/tmp`，让真实路径与模拟根路径一致后重跑成功；没有修改安装器规避这些故障。
- 日志中 ubus 未运行及部分容器挂载点不可见，不用作固件内核服务通过或失败的证据。

仍未验证：用户真机、固件自身内核下的 TUN/procd 运行、LuCI 浏览器渲染、实际组网数据面及其他 ARM ABI 的固件安装。不得把本轮两套 ARM rootfs 的通过扩展为全架构真机兼容。v1.0.0 历史矩阵没有改写为 v1.0.1 新结果。

## 用户重试

已下载成功的 HSTS 提示不是该架构错误的原因，不需要为此关闭 TLS 校验或修改系统架构配置。重新下载更新的安装器并执行原安装命令即可；不需要先卸载插件或删除组网配置。
