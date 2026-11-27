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

## 第 71 轮 Health 候选

[源码构建 45002345247](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/45002345247)
成功，2,332 条目标命令没有缺失依赖。固定源版本、源码摘要、产物归属和
压缩包摘要均通过验证。11 个产物文件中，6 个与现有图形载荷重叠的共享库
字节完全相同；vendor 只新增 Health 服务、init/VINTF 配置、V5 接口库和
libpng，另更新文件标签与已严格编译的策略。仍为 64 MiB 文件系统加 AVB。
[构建记录](../build/device/m3-health-build-2026-11-22.json)。

第 71 轮候选的 27 项[输入对比](../build/device/m3-framework71-preflight-2026-11-22.json)
通过：内核、DTB/DTBO、GSI、显示开关、图案、guardian 与密钥保留；LP
元数据和 extent 也不变。RAM data 扩为已校验的 2 GiB，metadata 种子不变。
这些是本地准备结果，真机 Health 回调、BatteryService 和桌面尚待验证。

第 71 轮实际在 EDL 回读阶段中断，尚未发送 GSI 放行命令。候选写入收到
完成确认，boot、DTBO 和 super 前 8 段回读通过；第 9 段收到的
384,827,392 字节也与候选前缀相同，但 Windows ReadFile 在 16:54 失败。
紧随其后的原厂恢复因端口消失未能开始。USB 重插后短暂枚举为
`05c6:900e` / COM9，之后再次消失。用户配合重新进入 9008 后，在 COM6
完成原厂回写；17:11 的 F.20、ADB、boot_completed 和两份 LP 元数据验证
通过，未重复回读原厂整区。[恢复记录](../build/device/m3-framework71-restored-2026-11-22.json)。
不能将该事件归因于尚未验收的 Health 或新框架。900E 根因仍未确定。
[中断证据](../build/device/m3-framework71-interruption-2026-11-22.json)。

## 第 71 轮重试：Health 已通过，阻塞推进到 Power HAL

原厂恢复后重试同一候选，boot、DTBO 和 super 全部 17 段回读通过。
boot `c4b86563-5714-4f06-855e-26cf1525e734` 中，源码 Health 在
`u:r:rmx_health:s0` 下注册 `android.hardware.health.IHealth/default`。
BatteryService 记录 `Waited 0ms and received the update`，初始回调已通过。
2 GiB RAM data 样本使用约 41%，本次采集没有 ENOSPC；原厂 userdata 不变。
同一次启动的 ADB 传输与稳定性检查通过 196.859 秒，guardian retained，
手机留在 GSI。未重复冷启动或故障注入，也未新增实屏验收。

下一处实际致命错误是 `HintManagerService.java:334`：没有 Power HAL 时，
构造函数读取空 `SupportInfo.headroom`，导致 system_server 退出。
后续采样中 battery/activity/window 不可查询，是这次进程退出后的状态，
不能据此否定已经收到的 Health 回调。当前仍未到达 Launcher 或开机完成。
[真机结果与日志摘要](../build/device/m3-framework71-result-2026-11-22.json)。

下一步提供项目源码 Power AIDL 服务，明确报告尚未实现的能力为不支持；
不给出虚假的性能会话或余量测量。保持第 69 轮显示输入、同一 GSI 和
2 GiB/32 MiB 测试卷，先验证框架越过 HintManagerService，再看 WindowManager
和 Launcher。电量/充电驱动仍未移植，audioserver 的独立空指针崩溃仍待处理。

项目 Power 服务已实现，使用固定 AOSP 的冻结 V7 NDK 接口。能力位全为
false/0；会话创建、周期、通道和 headroom 同步查询返回
`EX_UNSUPPORTED_OPERATION`，不分配虚假会话或伪造余量。接口允许忽略的
oneway 提示保持无操作，不写频率/电源节点。`SupportInfo` 保留完整的嵌套
parcelable，让框架能查询“不支持”，而不是得到空服务。
源接口摘要见 [固定输入](../build/m3-power-source.json)，项目源码在
`device/realme/bladerunner_48m/m3-power/`。

Power 使用平台公开 HAL server 属性；合并策略已在第 71 轮当前 GSI 上
严格编译通过，neverallow 保持启用，未加载新策略、未改变 enforcing。
[策略编译记录](../build/device/m3-power-policy-2026-11-22.json)。
本地集成继续拒绝覆盖字节不同的现有 HAL/图形库；第 72 轮对比要求测试卷
完全相同，并仅允许 Power 文件、标签及合并策略改变。构建和真机结果待验证。

## 第 72 轮：Power、HintManager 和 WindowManager 通过启动入口

[Power 构建](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/45008097656)
成功，1,758 条目标命令没有缺失依赖；源码和产物摘要均核验通过。
只新增服务、init/VINTF 配置及两个 AIDL 接口库，重叠的库与上一轮字节相同。
vendor 仍为 64 MiB 文件系统加 AVB。[构建记录](../build/device/m3-power-build-2026-11-22.json)。
30 项[候选对比](../build/device/m3-framework72-preflight-2026-11-22.json)全部通过；
同一内核、DT、显示参数、GSI、2 GiB data/32 MiB metadata、LP 元数据和 extent。

从第 71 轮 retained GSI 自动进入 COM6 9008，核验机内旧布局后只更新
super 第 0 段及配套 boot。boot/DTBO 和完整 super 回读全部通过。没有再次
备份或回读原厂分区。新 boot 为 `b32f1c72-fb87-41e1-8a49-33dac9bdda38`。

项目 Power 在 `u:r:rmx_power:s0` 下注册 `IPower/default`。框架实际调用
`getSupportInfo`，HintManagerService 完成启动，`performance_hint` 可查询：
preferred rate 为 -1，hint sessions、CPU/GPU headroom 都正确显示不支持。
Health 初始回调仍为 0 ms；activity、window、package 服务都已注册。
同一次启动 ADB 检查通过 196 秒，guardian retained，手机留在 GSI。
[真机结果与证据摘要](../build/device/m3-framework72-result-2026-11-22.json)。

这尚不代表整个框架稳定：启动随后卡在 AudioService 构造函数的
`AudioSystem.muteMicrophone`。audioserver 仍在 `AudioFlinger::onFirstRef()+712`
空指针崩溃；日志明确显示设备和效果两种音频 HAL 均未声明，工厂选择返回空。
Android Watchdog 记录 main handler 阻塞 67 秒并重启 system_server，
内核 boot ID 和 ADB 保持不变。Launcher 未启动，boot_completed 未设置。
这是本轮自然出现的框架故障，不是注入的看门狗测试。

下一阶段目标是项目源码音频 HAL 的设备/配置和效果工厂入口，先让
audioserver 注册 AudioFlinger/AudioPolicy、AudioService 完成构造，再看 Launcher。
同版本 [FactoryHal.cpp](https://android.googlesource.com/platform/frameworks/av/+/refs/tags/android-17.0.0_r1/media/libaudiohal/FactoryHal.cpp)
要求设备接口与效果工厂类型及主版本匹配；只补 IConfig 不足以通过工厂选择。
目前 `/dev/snd` 仅有 timer，不能宣称 PCM、扬声器、麦克风或 DSP 已移植。
后续实现必须区分接口可用和真实音频硬件能力。显示内核与参数继续保持不变。

## 第 73 轮准备：项目 Audio Core / Config / Effect

项目 `m3-audio` 同一进程提供冻结 AIDL V4 的 `IConfig/default`、
`IModule/default` 和 `IFactory/default`。实现完整接口方法，以当前内核的
可用能力为边界：端口、路由、麦克风、效果列表为空；无有效端口时拒绝
创建流、patch 和效果句柄；未接通的音量、静音、时钟控制返回不支持。
配置不覆盖 AOSP 默认策略，不伪造扬声器、PCM 输出或 DSP 功能。

这一步解决工厂缺失并验证 framework 启动，不等于音频硬件移植完成。
无默认输出时 AudioPolicyManager 可能无法初始化真实路由；需要真机区分
AudioFlinger/AudioPolicy Binder 注册、AudioService 构造和完整路由能力。
当前目标仍为通过 AudioService 后检查 Launcher 的真实画面。

构建使用[固定源版本和摘要](../build/m3-audio-source.json)，集成只允许增加
源码音频载荷。任何不同字节的已有图形/Health/Power 库都会被拒绝。
候选保持第 69 轮显示参数和第 72 轮 2 GiB/32 MiB 测试卷。原厂恢复集
继续仅保留一份，不新增原厂整区回读。源码构建、严格策略编译和真机结果
在完成后追加；当前尚不作第 73 轮通过结论。

第 72 轮同一 retained GSI 上的合并 SELinux 策略已严格编译通过，
neverallow 检查启用；未加载策略、未改变 enforcing。
[Audio 策略证明](../build/device/m3-audio-policy-2026-11-22.json)。
三个音频实例均使用 GSI 已有的 `hal_audio_service` 标签及公开 server 属性。
13 项载荷碰撞/篡改、显示保留、测试卷及增量更新检查通过。

[Audio 源码构建 45012264891](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/45012264891)
成功，2014 条目标命令无缺失依赖。13 个产物文件均通过源版本、
源码和归档摘要核验；9 个新增文件，重叠库全部字节相同。
vendor 文件系统为 64 MiB，GSI 和已有驱动载荷未替换。
[构建及组合记录](../build/device/m3-audio-build-2026-11-22.json)。

第 73 轮 30 项[候选对比](../build/device/m3-framework73-preflight-2026-11-22.json)
全部通过：保留内核、DT、显示参数、GSI、测试卷、LP 元数据和 extent；
仅增加音频文件并更新标签/策略。下一步真机验证三个接口注册、
audioserver、AudioService 和 Launcher。

## 第 73 轮：音频入口通过，发现 16 MiB Java 堆上限

boot/DTBO 和 super 全部 17 段回读通过，仅写变化的 super 第 0 段和 boot。
boot `af9d53f4-d880-4306-87b3-dfa46287c16b` 中，三个音频实例在
`u:r:rmx_audio:s0` 注册，框架实际调用 IConfig、queryEffects 和 getAudioPorts。
AudioFlinger 创建、primary interface 加载成功，AudioPolicy 创建并记录
`AudioSystem ready`。原有 `AudioFlinger::onFirstRef()+712` 空指针未再出现。
AudioService 完成构造，记录到启动阶段 500。

后续 system_server 在多个线程发生 OOM：Java 堆 growth limit 只有
16,777,216 字节，而 MemTotal 为 7,607,848 KiB，采样 MemAvailable 仍有
4,545,908 KiB。`dalvik.vm.heap*` 属性全部缺失。zygote 的联动重启也重启
了 audioserver/Audio HAL，因此不能将本轮写成音频进程已持续稳定验收。
无真实输出端口时，路由/音量初始化仍会报错并重试；没有声音能力结论。
Launcher 和 boot_completed 尚未到达。ADB 同次启动通过 197.078 秒，
guardian retained，手机留在 GSI。
[第 73 轮结果](../build/device/m3-framework73-result-2026-11-22.json)。

下一轮保持所有 HAL/显示输入与测试卷，仅增加六项 Dalvik 堆属性。
采用固定 AOSP `phone-xhdpi-6144-dalvik-heap.mk`：初始 16m、增长上限
256m、最大 512m、目标利用率 0.5、最小/最大空闲 8m/32m。AOSP 此目录
无 8 GiB 专用配置；在实测约 7.25 GiB 可见 RAM 的手机上采用其 6 GiB
手机配置，不修改 GSI。源版本、摘要和值见
[堆配置固定输入](../build/m3-dalvik-heap-source.json)。

第 74 轮 34 项[候选对比](../build/device/m3-framework74-preflight-2026-11-22.json)
全部通过。vendor 仅 `/build.prop` 改变，逐属性检查只增加固定的六项
堆参数；所有 HAL/图形文件、SELinux、显示输入、测试卷和 LP 布局相同。
下一步上机检查实际属性、OOM、AudioService 和 Launcher。

## 第 74 轮：AudioService 到阶段 600，桌面前阻塞于 Keymaster 导入

完整回读通过，boot 为 `efad714b-7e3d-4c66-b787-c170f875df6a`。六项堆属性
全部与固定配置相符，采集窗口内没有再出现 OOM。音频三接口在 enforcing
下注册，AudioFlinger/AudioPolicy 初始化完成并进入线程池；现场查询捕获
`media.audio_flinger`、`media.audio_policy` 和 `audio` 均为 found。
AudioService 到达启动阶段 600，SystemUI 进程启动。

随后 system_server 在 `LockSettingsService.initializeSyntheticPassword`
退出：`SyntheticPasswordCrypto.createBlob` 导入密钥时得到
`Error::Km(UNIMPLEMENTED)` / -100，最终抛出 `Failed to encrypt blob`。
项目 `m1-keymaster-info/service.cpp:81` 的 `importKey` 目前确实直接返回
未实现。该故障在后续框架启动中重复；audioserver/音频 HAL 随 zygote 联动
重启，不是此前的 AudioFlinger 原生空指针。音频初始化后仍无真实路由，
音量初始化会重试，不能宣称硬件音频或整个框架已稳定。

Launcher 尚未形成可验收桌面，`sys.boot_completed` 未设置。下一阶段目标
是接通项目 Keymaster 到 TEE 的密钥导入及后续 AES-GCM 操作，让合成密码
初始化完成，再继续 Launcher。目标仍为 6.18 + GSI + 移植驱动的真实桌面。

ADB 同次启动检查通过 196.563 秒，guardian retained，手机留在 GSI；内核、
DTB/DTBO、显示配置和测试卷未变，未做冷启动或故障注入，未回读原厂整区。
主机在已写入 gsi-stable 证明后收集 logcat 时使用 Windows GBK 解码而失败；
已修为显式 UTF-8，并在同一启动重新采集、核验身份和 retained 状态。
没有重启手机或重复稳定性测试。该主机错误与 Keymaster 框架崩溃分开记录。
[第 74 轮结果与证据摘要](../build/device/m3-framework74-result-2026-11-22.json)。
