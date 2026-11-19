# v1.0.0 验证报告

核对日期：2026-11-19。安装器 SHA-256：`30a720789043473f82b1dd412649fed75299231e31ec96741e5cce69d7facc6f`。

## 已验证

| 验证层级 | 结果 | 范围 |
| --- | --- | --- |
| Shell 语法 / 静态检查 | 通过 | POSIX sh、BusyBox ash、ShellCheck 0.9.0 |
| 失败路径回归 | sh 24/24、ash 24/24 | 实际 jsonfilter、紧凑 JSON、44 个 Release 选择器、错误摘要/长度、空成功/失败下载、假安装成功、降级拒绝、配置恢复、真实并发锁、信号清理 |
| 全部上游附件 | 44/44 | v2.6.4，22 种包架构 × IPK/APK；大小、SHA-256、ZIP 完整性、176 个包的名称/版本/架构 |
| 核心版本命令 | 22/22 | IPK 核心，x86_64 为宿主机原生执行，其他为 QEMU user 模拟；不是对应真机指令集下限测试 |
| APK 核心内容 | 44 个散列匹配 | 每个架构 easytier/easytier-noweb 的 APK 核心内容散列，均与对应 IPK 二进制一致 |
| 官方 x86_64 rootfs 安装场景 | 6/6 | 两代包管理器 × 完整/noweb/仅 LuCI 三模式 |
| 跨版本升级 | 4/4 | 两代系统的完整与仅 LuCI 模式：v2.6.2 → v2.6.4；noweb 旧版不存在，不算升级通过 |
| 重复安装 / 配置保留 | 6/6 | 比较 UCI 和 TOML 配置 SHA-256，保留原 init 自启禁用状态，首次配置 enabled/web_enabled 均为 0 |
| 交互卸载 | 2/2 | IPK/APK 的 LuCI + 中文包，真实伪终端输入 REMOVE；校验卸载记录及配置散列、持久备份 |

软件包记录和核心版本均在事务结束后检查，不以安装命令的退出码单独认定成功。真实固件 rootfs 来自官方目录，下载散列与官方 sha256sums 一致；两代 rootfs 的散列见 [事务记录](firmware-smoke.json)。

## 固件事务明细

| 固件 | 格式 | 模式 | 安装/重复安装/配置保留 | 跨版本升级 |
| --- | --- | --- | --- | --- |
| OpenWrt 24.10.8 x86_64 | ipk | full | 通过 | v2.6.2 → v2.6.4 通过 |
| OpenWrt 24.10.8 x86_64 | ipk | noweb | 通过 | 未测试（旧版无此变体） |
| OpenWrt 24.10.8 x86_64 | ipk | luci-only | 通过 | v2.6.2 → v2.6.4 通过 |
| OpenWrt 25.12.6 x86_64 | apk | full | 通过 | v2.6.2 → v2.6.4 通过 |
| OpenWrt 25.12.6 x86_64 | apk | noweb | 通过 | 未测试（旧版无此变体） |
| OpenWrt 25.12.6 x86_64 | apk | luci-only | 通过 | v2.6.2 → v2.6.4 通过 |

测试中只将 GitHub Release API 与 ZIP 下载替换为已从宿主机下载、与官方摘要一致的原始附件缓存；固件依赖仍通过真实官方软件源安装。原因是 Docker 网络中访问 GitHub 附件超时，宿主机访问成功。不能将此称为路由器网络上的端到端在线下载通过。

## 实际发现并修复的问题

1. 上游 LuCI 与中文包均包含同名语言初始化文件，IPK 一次安装会产生冲突。改为先完成 LuCI 配置，再安装中文包；没有使用 force-overwrite 或 force-depends。
2. 上游旧版及当前服务的停止钩子删除 `/tmp/easytier-*.*`，曾把安装器暂存包一并删除。工作目录和锁改用 `/tmp/et-luci-install.*`，真实跨版本升级已通过。
3. OpenWrt 25.12 rootfs 默认无 timeout。完整模式按需从固件源补装 coreutils-timeout，核验真实核心版本 `2.6.4-8428a89d`。
4. IPK 架构名含下划线，不能从最后一个下划线拆版本。改为去掉完整已知架构后缀，并核对数据库中的完整包版本。
5. 上游升级钩子可能重新启用自启，安装器记录并恢复旧的 init 自启开关；未声称运行中组网无中断。

## 全架构清单与边界

已逐一核对官方 24.10.8 的 36 种、25.12.6 的 35 种包架构，共 71 个固件/ABI 条目，见 [完整清单](firmware-architecture-inventory.json)。44 个条目有上游精确对应附件；另外 27 个没有精确附件，脚本明确拒绝，不强制映射。附件可用不是固件安装已验证。

上游发布的 22 种包架构：

```text
aarch64_cortex-a53
aarch64_cortex-a72
aarch64_generic
arm_arm1176jzf-s_vfp
arm_arm926ej-s
arm_cortex-a15_neon-vfpv4
arm_cortex-a5_vfpv4
arm_cortex-a7
arm_cortex-a7_neon-vfpv4
arm_cortex-a8_vfpv3
arm_cortex-a9
arm_cortex-a9_neon
arm_cortex-a9_vfpv3-d16
arm_fa526
arm_xscale
mips_24kc
mips_mips32
mipsel_24kc
mipsel_24kc_24kf
mipsel_74kc
mipsel_mips32
x86_64
```

以下仍未验证，不算通过：

- 除 x86_64 以外的对应官方固件内安装、依赖解析、LuCI 页面实际渲染。
- iStoreOS 原版镜像和具体软路由硬件。
- 使用固件自身内核的 TUN/procd 服务运行、已启用实例的实际运行状态与组网数据面。
- LuCI 浏览器登录、节点互通、跨网段路由和自建控制台监听。
- 带核心包的交互卸载；本轮卸载实测覆盖的是仅 LuCI + 中文包。

Docker 使用宿主机内核，日志中的 ubus 不可连接、TUN 设备缺失不能当作固件自身内核服务通过或失败的证据。以上为安装器本地实现阶段的验证，没有操作用户的真实路由器；这些记录不证明线上安装入口可达，当前源码入口见 README。

## 证据与复跑

- [上游全附件元数据及核心执行](upstream-assets.json)
- [官方 rootfs 实际事务](firmware-smoke.json)
- [sh 回归日志](logs/regression.log)、[ash 回归日志](logs/regression-ash.log)
- [IPK 卸载日志](logs/uninstall-ipk.log)、[APK 卸载日志](logs/uninstall-apk.log)
- 安装明细日志的相对路径列在 firmware-smoke.json 的 log 字段。
- tests/ 下脚本含命令行说明，audit_upstream.py 与 firmware_smoke.py 使用已验证附件缓存。复跑全选择器测试需设置 EASYTIER_RELEASE_JSON 为捕获的官方 Release JSON；需要真实 jsonfilter。

上游来源：[LuCI 仓库](https://github.com/EasyTier/luci-app-easytier)、[正式 Release](https://github.com/EasyTier/luci-app-easytier/releases/tag/v2.6.4)、[OpenWrt 24.10.8](https://downloads.openwrt.org/releases/24.10.8/targets/x86/64/)、[OpenWrt 25.12.6](https://downloads.openwrt.org/releases/25.12.6/targets/x86/64/)。
