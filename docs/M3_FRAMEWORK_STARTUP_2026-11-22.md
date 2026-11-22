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
