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
实际屏幕；不以 ADB 或内部截图替代桌面验收。

## 第 70 轮真机结果

26 项[候选检查](../build/device/m3-framework70-preflight-2026-11-22.json)通过，
内核、DTB/DTBO、GSI、显示开关和测试卷种子保持第 69 轮输入。活跃 LP
布局仅 vendor 改变；另一份 LP 元数据的 system 覆盖同一片 vendor 字节，
因此它的摘要也随之改变。元数据和全部 extent 不变，未把它当作回滚槽。
候选 boot 和 super 回读通过；未重新备份或回读原厂 super。

boot `8135c6b2-9905-4c2b-8908-d986e7422672` 上 `ro.boot.rmx_scratch=1`，
installd/storaged 均运行。包管理扫描完成 201 个系统包，installd 执行真实
应用数据事务，`reconcileAppsData` 完成 28 包。main 类启动缺口得到验证。
shell 执行 `service check installd` 被 `installd_service:find` 拒绝，不能
把这个 not-found 当成服务不存在；上述事务来自 installd 自身日志。

ADB、SurfaceFlinger、HWC、allocator、maintenance 在 enforcing 下可用。
system_server 随后仍因缺少 IHealth/default 在 BatteryService.onStart 退出，
activity/window 和桌面尚未出现；`/sys/class/power_supply` 为空。
[同 boot 摘要、关键日志与原始文件摘要](../build/device/m3-framework-70-2026-11-22.json)。

同一次启动连续 ADB 检查通过 197.593 秒，guardian 为 retained，未切换到
F.20。当前镜像仍是需要主机放行的显示诊断入口；这不证明重启后可无人
接管。本阶段未重复冷启动或看门狗故障测试。

main 服务启动后也暴露了测试卷容量限制：512 MiB `/data` 使用约 99%，
GSI 解压 Trichrome 系统 stub APK 时明确出现 ENOSPC。Chrome/Trichrome
本身的解压大小约 54/138 MiB，其他首次启动写入与它们共用该卷。
下一轮仅把 RAM loop0 的 data 种子扩大到 2 GiB；相同 UUID、初始标签、
32 MiB metadata 字节与摘要保留，原厂 userdata 不变。新压缩 data 种子
为 2,089,420 字节，完整解压摘要和 e2fsck 已通过。仅接受显式开启的
512 MiB → 2 GiB 转换，普通更新继续要求种子完全相同。
[容量与种子记录](../build/device/m3-scratch-expansion-2026-11-22.json)。

## 同时确认的下一处阻塞：Health HAL

第 69 轮的同 boot 日志在约 179 秒记录 BatteryService.onStart 致命异常：
`IHealth service instance default isn't available`，之后重复出现。
因此 main 类启动修复并不足以宣称桌面可用。

新增独立 Health 构建任务，使用同一 Android 17 tag 和已固定的 native
源码工作区，只编译上游 `android.hardware.health-service.example` 及其
真实依赖，保留解析后的 manifest、目标依赖图和源码摘要。其 AIDL 为 V5。
不重编内核或渲染器；产物尚未集成到第 70 轮 vendor。

该实现读取内核 power_supply。缺失电量节点时，属性查询返回不支持，
没有读数不等于电量为零或满电；项目不设置 fake_battery。后续必须先查
6.18 的实际节点，再验证服务回调、enforcing 权限与 BatteryService 的
启动结果。构建 Health 服务不代表充电/电量计驱动已经移植完成。

Health 域继承平台 `hal_health_server` 规则，按同版本上游
`vendor/hal_health_default.te` 加入 `bpfdomain`；初次缺少该属性时，严格
编译正确触发 neverallow。补齐上游域属性后，组合策略在第 70 轮同一
boot 严格编译通过，未关闭 neverallow、未加载新策略或改变 enforcing。
[策略编译记录](../build/device/m3-health-policy-2026-11-22.json)。
HAL 产物只允许增加文件或复用字节相同的共享库，拒绝替换已有图形库；
正常 Health 服务与尚未移植的 charger-mode UI 分开，当前不启用后者。

Health 构建 #2 的 2,330 条命令依赖检查发现唯一缺项为
`libhealthloop -> bpf_headers`，因而在执行不完整目标前失败。
该模块及 `bpf_syscall_wrappers` 位于同一 Android 17 tag 的
`packages/modules/Connectivity/bpf`；其测试声明引用的
`bpf_cc_defaults` 位于 `system/bpf/Android.bp`。构建补入这两个真实
项目，只展开原生头文件与默认声明，继续保留缺失依赖检查。
两个新增项目的 commit、三个 Android.bp 摘要和 sparse 选择均进入
产物验证；不合成头文件、不删除 HealthLoop 功能。

## 下午恢复与继续

11 月 22 日下午继续时，设备处于 9008/显示诊断入口。取得的 pstore 只
包含后续诊断启动：181.082 秒执行 `reboot edl`，符合未收到主机放行的
180 秒入口超时。它不能证明最初的 GSI 退出原因；不将该原因写成已定位。
16:22 用唯一原厂恢复集恢复 F.20，ADB、boot_completed、两份 LP 元数据
通过，未回读原厂整区。[恢复记录](../build/device/m3-framework70-restored-2026-11-22.json)。

第 70 轮既有 tombstone 还确认 audioserver 在
`AudioFlinger::onFirstRef()+712` 空指针 SIGSEGV。先保存这个问题；目前
已定位的框架致命点仍是更早的 BatteryService，音频是否阻塞桌面要在
Health 接入后再判断。下一轮使用相同显示输入、源码 Health 和 2 GiB RAM
data，目标为 BatteryService 通过、activity/window 注册和 Launcher 出图。
