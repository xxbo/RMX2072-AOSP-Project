# M3 原厂正常显示与早期开屏时钟对照

目标仍为 ACK 6.18 + Android 17 GSI + 项目源码/移植驱动，先消除实屏花屏，再推进 AOSP 桌面。

用户补充：过 realme 标志后很早就开始花屏。trial 64 的软件日志显示首次 DSI power-on 在 33.424915 秒，面板 enable 在 33.594077 秒，Android SELinux 策略日志在约 91.862 秒。观察与早期显示接管相符，但用户没有给第一个错误像素打时间戳。trial 61–64 的原生实屏结果仍是更直接的“Android 之前即可复现”证据。

## 原厂对照结果

原厂 boot、DTBO、17 个 super 块均完成回读校验，F.20 开机完成、两份 LP 元数据和手机端全 super 摘要匹配。用户确认“画面正常，没有花屏”。记录为 [原厂显示时钟证据](../build/device/m3-f20-display-clock-2026-11-18.json)。

F.20 未编译 `CONFIG_DEBUG_FS` 和 `CONFIG_KPROBES`，因此没有取得原厂运行时 MMIO 寄存器快照。没有调用可能触发 panic 的通用 display dump，也没有通过裸物理内存读取绕过这一限制。

原厂保留了 tracefs 时钟事件。一次性 post-fs-data 采集从开机 5.65 秒开始，至约 50.7 秒结束，86/86 条事件均保留，各 CPU overrun、commit overrun、dropped events 为 0。原厂日志先于 9.495710 秒设为 60 Hz，18.332926 秒才切到 90 Hz；下列 DSI 设频完成事件位于 13.743 秒，属于初始 60 Hz 区间。

| 时钟 | F.20 设频完成事件 | trial 64 CCF 读值 |
| --- | ---: | ---: |
| DSI bit | 660,000,000 Hz | 421,631,982 Hz |
| DSI byte | 82,500,000 Hz | 52,703,997 Hz |
| DSI pixel | 110,000,000 Hz | 70,271,997 Hz |

这是软件时钟操作/CCF 的证据，未使用示波器测量物理频率。F.20 的 60/90 Hz 模式日志均报告 `mdp_transfer_time_us=7956`。6.18 当前通过 DRM 模式的总像素时序和 DSC 压缩比例计算链路速率，未对齐这一原厂传输预算。

trial 64 同一次启动的 `before-modeset` 采样也为 660/82.5/110 MHz，`after-modeset` 和 `after-flips` 才变为约 421.6/52.7/70.3 MHz。这把差异进一步对应到 6.18 第一次显示编程，仍不等同于已证明时钟是花屏根因。

另一次显示息屏/亮屏追踪记录到了 `_sde_encoder_dsc_2_lm_2_enc_1_intf`，但 `peak_refresh_rate=60.0` 请求未持续固定实际模式，最终转储仍为 90 Hz；不能把该次追踪标成固定 60 Hz 通过。设置已经恢复采集前的 `60.000004`。开机追踪独立确认了上述初始 60 Hz 区间。

临时 post-fs-data 脚本与安装副本已移除。追踪和事件均已关闭、过滤器已清空；私有 trace instance 删除返回 EBUSY，保留为关闭状态，下一次切换内核时消失。普通 SurfaceFlinger/显示服务的完整转储只保留在本地，公开记录仅含显示硬件事件和摘要。

## 下一项受控验证

### trial 65 暂停点

内核构建 [#34](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/44321852995) 已成功，源码提交 `c0137943356794565b88e3eb2cdc2710411c5ec5`。选取的构建成员、源码补丁和内核输出摘要核验通过；未下载完整归档校验 archive digest。打包前后固定输入对照通过，候选 boot、DTBO 和全部 17 块 super 回读通过。

原生测试图开始后，用户回复“先暂停”，没有提供本轮画面结果。手机随后完成已启动的自主交接，进入 GSI ADB，boot ID 为 `d156e9a3-246e-4249-a618-54a0931f7aa0`。确认设备自身为 `retained` 后停止电脑端 runner、采集、串口观察及 USB 观察进程。未关机，未恢复 F.20，未继续新的测试。

主机 190 秒检查被暂停，没有 `gsi-stable.json`，不能标为完成。运行时链路时钟/PPS/路由的完整对照尚未完成，原生和 Android 实屏均未验收，花屏根因仍未确定。后续先复核已保存的同次启动记录，再取得实屏观察；不因本次暂停直接追加刷机。详见 [trial 65 暂停记录](../build/device/m3-display-65-paused-2026-11-18.json)。

### 本轮实验设置

新增默认关闭的 `msm.rmx2072_stock_linkclk=1`，仅匹配 SM8250 单 DSI、四条 D-PHY lane、RGB888 command mode、1080×2400@60、DSC 540×48/两片/8 bpc/8 bpp。开启时统一设置 byte=82.5 MHz、pixel=110 MHz，由现有 PHY/CCF 路径配置 660 MHz bit clock。

保持 trial 64 的单 DSC 拓扑、PPS、每包两片、DTB/DTBO、GSI/vendor、测试卷和同图测试不变。原厂双 DSC 路径已经由此前双/单 DSC 对照覆盖，不能同时恢复双 DSC 又改变时钟。打包器要求此补丁摘要与编译产物一致，并在 boot/USB 构建记录中保存显式开关。

验收必须先确认运行时请求、实际 CCF 读值和 PHY/PLL 状态，再观察原生与 Android 实屏。仅时钟对齐或 ADB 正常都不构成花屏修复。当前根因仍未确定，此修改是由原厂差异支持的隔离实验。

事件接口参考：[Linux Event Tracing](https://docs.kernel.org/trace/events.html)。原厂 sysfs 实现的源码参照为 [SM8250 downstream oplus_display_private_api.c](https://github.com/SM8250-Common/android_kernel_realme_sm8250/blob/b76eb6c93add8152b1aa873da0d8d7f495cccab0/techpack/display/oplus/oplus_display_private_api.c)，该社区源码不等同于已证明完全匹配的 F.20 内核源码。
