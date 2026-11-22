# M3: 从已修复显示推进 AOSP 桌面

目标保持为项目 6.18 + Android 17 GSI + 源码/移植驱动进入可交互桌面。
第 69 轮的原生和 Android 实屏已通过；本阶段保持显示参数，定位框架启动阻塞。
开始时手机运行 F.20，仓库同步到 `74f4d45`，无未提交修改。

## installd 缺失的源码与记录对照

从同一份未修改 GSI 中读取，`/system/bin/installd` 和
`/system/etc/init/installd.rc` 均存在；其服务属于 `class main`。
GSI 的主 init 脚本在 `on nonencrypted` 时才启动 main 和 late_start。
上一轮项目 vendor 的板级 init 只有 early-init 日志，fstab 只有已验证的
system/vendor，没有第二阶段 mount_all，也没有 nonencrypted 事件。

第 69 轮记录确认 `/data`、`/metadata` 是 RAM 文件支持的独立可写 ext4 loop
卷，已在 Android 接管前挂载。保存的属性中 installd/storaged 没有启动状态，
SurfaceFlinger 和 zygote 则在运行；它们可通过 core 类和显式 start 独立启动。
PackageManager 多次等待 installer 超时。

这支持“测试卷绕过通常发出 nonencrypted 的流程，main 类未启动”的假说，
尚需真机验证。参考 [AOSP mount_all 的事件处理](https://android.googlesource.com/platform/system/core/+/6f22965053550a23489cac4e9bc1cff38503a2e2/init/builtins.cpp)
仅用于机制对照；设备结论以本地 GSI 脚本和同 boot 日志为准。
[摘要与文件哈希](../build/device/m3-framework-startup-analysis-2026-11-22.json)。

## 第 70 轮候选

板级 init 只在 `ro.boot.rmx_scratch=1` 的测试卷配置下，于 boot 阶段排入
nonencrypted 事件，交由 GSI 自身启动 main/late_start。打包器仅在 ramdisk
记录了已校验的 512 MiB data 和 32 MiB metadata 种子、且启用 guarded ADB
与自主 UFS 流程时生成该标记。实际挂载仍校验原有种子摘要与 loop backing；
不改变原厂 userdata，不把此流程当作正式 FBE 实现。

同时修正 vendor 重建脚本丢失已通过显示开关的问题：继承第 69 轮 PPS、
单 DSC、时钟、PHY、回读和追踪配置；拒绝无意改变 staging 模式。
GSI、内核、设备树和测试卷保持固定。本轮仍用已有诊断入口收集早期证据，
不重复拔线、冷启动或看门狗故障演练。

两项新的打包边界测试及四项既有 vendor 更新边界测试通过。
后续依次验收 installd 注册、包管理初始化、activity/window、Launcher 与
实际屏幕；不以 ADB 或内部截图替代桌面验收。候选构建和真机结果待记录。
