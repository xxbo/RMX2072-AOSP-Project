# F.20 实际 PPS 顺序与第 69 轮准备

当前目标：修复项目 6.18 + Android 17 GSI 的实屏花屏，再推进 AOSP 桌面。第 68 轮仍花屏；本阶段先采原厂实际命令，不重复冷启动或整区备份。

## 原厂真机新证据

F.20 在同一次启动 `357dcda6-83fa-46dc-9f61-3eb2eaedc0af` 内完成两次短暂熄屏/亮屏。第一次保持原有 90 Hz，验证厂商命令日志能输出完整载荷；第二次请求 60 Hz，开屏日志确认实际为 1080×2400@60，然后恢复原有 `peak_refresh_rate=90.0`。日志开关从 0 临时变为 1，结束均恢复为 0；最终屏幕电源状态为 2，没有整机重启。

第一次采集的工具有一个已修正的问题：原厂 `printf` 按字节写 `/dev/kmsg`，导致标记被拆散，自动提取报错。日志开关仍经手机 trap 和主机 finally 恢复，完整原始日志留存本地。第二次改为 `echo` 单条写入，开始/熄屏/亮屏/结束标记全部闭合。没有用第一次的失败提取冒充完整采集。

第二次带摘要验证的[公开命令记录](../build/device/m3-f20-runtime-pps-2026-11-21.json)显示：

1. `2013.413866`：DCS long-write `0x39`，载荷为 `0x9e` 加 88 字节静态 PPS。
2. `2013.439465`：**标准 PPS 类型 `0x0a`，完整 128 字节**，位于整个 on-sequence 后。
3. `2013.502413`：DCS display-on `0x29`。

标准包比厂商包晚 25.599 ms，比 display-on 早 62.948 ms。两包前 88 字节有 12 个字节不同，标准包尾部 40 字节均为零。关键参数：

| 参数 | 静态 `0x9e` | 实际后发的标准 PPS |
| --- | ---: | ---: |
| initial_dec_delay | 594 | 526 |
| scale_increment | 1059 | 1190 |
| first_line_bpg_offset | 15 | 12 |
| nfl_bpg_offset | 654 | 523 |

最后五组 RC range 也不同，完整差异在 JSON 中。日志头 `flags=0x0a`，与参考下游的 LP `BIT(1)` + LASTCOMMAND `BIT(3)` 一致。`*ERROR*` 是此日志输出的等级，不能据此声称发包失败；这仍是软件 TX 记录，不是线缆捕获或面板内部 PPS 回读。

参考[下游 dsi_display_enable](https://github.com/SM8250-Common/android_kernel_realme_sm8250/blob/b76eb6c93add8152b1aa873da0d8d7f495cccab0/techpack/display/msm/dsi/dsi_display.c)在 `dsi_panel_enable()` 后调用 `dsi_panel_update_pps()`，与本次实际顺序相符。参考源码不是 F.20 二进制的完全对应源码，本次结论以真机发送日志为依据。

**纠正此前边界：第 66–68 轮所谓匹配“原厂 PPS”，实际只匹配选中 DT 的静态 `0x9e`，不代表原厂最后发送的运行时 PPS。** 既有 43 项配置检查没有验证这一命令差异，不能解释成原厂完整显示状态均已复现。

## EoT 的缺口

本次实时 `/proc/config.gz` 确认 DEBUG_FS、DEVMEM、PROC_KCORE、KPROBES、DYNAMIC_DEBUG、FUNCTION_TRACER 均未启用。已检查的 host register dump 只通过 debugfs 提供，厂商 panel/dsi_cmd 接口不是 host MMIO 读取。没有取得 F.20 EOT_PACKET_CTRL 实测值，不能把 DT 推断升级为运行值。保留 EoT 假说，优先测试已经捕获到的缺失标准包。

## 第 69 轮：只补发标准包

源码增加默认关闭的 `panel_samsung_rm19795.pps=1` 开关，在原有完整 on-sequence 后、display-on 前，以 LP 发送类型 `0x0a` 的 128 字节 PPS。内容由同一 `ctx->dsc` 打包，与当前编码器及 `0x9e` 一致；失败时退出 prepare，不能把传输失败当作出图成功。

保持第 68 轮的编码器参数、原有 `0x9e`、660 MHz、PHY、EoT、单 DSC 路由、测试图、GSI 和可写测试卷。**这轮隔离“补发标准包”的影响，不同时切换到 F.20 后发包的 RC 参数。** 因而这也不是完整复刻原厂 PPS 路径。若无改善，后续再单独评价运行时 RC 参数。

验收需要三层证据：完整 128 字节发送记录与返回值、编码器/原有输入保持不变、用户观察原生和 Android 实屏。编译成功或发送返回非负不等于花屏修复。测试失败恢复 F.20；仅保留原厂恢复集和当前候选。

当前状态：原厂采集完成，根因尚未确认；第 69 轮源码已准备，编译与真机结果待记录。
