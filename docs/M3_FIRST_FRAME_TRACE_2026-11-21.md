# 第 68 轮准备：首帧取证

目标是定位第 67 轮花屏的起点，最终让 6.18 + Android 17 GSI 的实屏正确出图，再推进 AOSP 桌面。当前根因未确定，本文不是显示通过报告。第 67 轮的 PHY、PPS、链路时钟、单 DSC 路由、GSI/vendor 和测试卷保持不变。

## 取证边界

`rmx2072-first-frame-trace.patch` 应用于第 67 轮补丁之后，所有新增 tracepoint 默认关闭。只有显式打包 `--first-frame-trace`、匹配内核补丁摘要且保留 staged gate 的候选才启用。没有修改错误屏蔽、错误清除、自动复位、OPP、带宽投票、面板命令和显示参数。

复用绑定显示驱动前创建的 `rmx_m3_clk` trace instance，使用 mono 时间、每 CPU 256 KiB、禁止覆盖最早记录；八个 CPU 共 2 MiB 二进制缓冲。结束后停止记录，输出完整文本与每 CPU 的 overrun/dropped/commit-overrun 统计。禁止用截断日志的“未出现”判定无错误。首次采集未覆盖 Android 接管后的图形操作。

IRQ 中只进行有上限的 MMIO 读取及固定长度 trace 记录，不打印、不分配、不调用 clock API。DSI 原始状态每个 phase 最多保存 16 组，每 host 每 boot 一次窗口，不重置窗口。被观察寄存器沿用当前驱动显式写清的状态接口；不额外读取未知寄存器。

| phase | 采样点 | cookie |
| --- | --- | --- |
| 0 | host power-on 完成、寄存器可访问 | 0 |
| 1 | command-mode kickoff 准备完成、使能 TE 前 | encoder ID |
| 2 | PP done handler 入口、正常回调前 | encoder ID |
| 3 | DSI error IRQ，清中断和错误状态之前 | 原始 IRQ |
| 4 | host-enable 完成 | 0 |
| 5 | DPU underrun handler 入口 | encoder ID |

phase 2 handler 也可由原驱动的等待处理调用，不能单凭它声称硬件 IRQ 或物理像素正确。phase 1 是提交准备点，不冒充精确的线上首个字节时间。

每组记录 IRQ/status0/FIFO/ACK/timeout/DLN0 PHY/PLL clock/error-mask。仅在 caller 已持有活动显示/IRQ 上下文时读寄存器；DPU 侧另外检查 host power_on。达到上限后的状态不在本次窗口内，不能推断为正常。

## 时间线事件的字段

`rmx_display_step` 的 a/b/c/d 按以下表解码，不能把 CCF 请求当作 PLL 已编程。

| step | a | b | c | d |
| --- | --- | --- | --- | --- |
| link-request | byte 请求 Hz | pixel 请求 Hz | byte-intf 请求 Hz | host power_on |
| link-result | CCF byte Hz | CCF pixel Hz | CCF byte-intf Hz | 0 |
| dcs-begin | host 事务序号 | type 高 32 bit + 首字节低 32 bit | tx_len | power_on 高 32 bit + flags |
| dcs-end | 同一事务序号 | type | tx_len | flags |
| pll-set-begin | 新 VCO Hz | parent Hz | 旧 VCO Hz | pll_on |
| pll-set-end | 新 VCO Hz | parent Hz | 当前 VCO Hz | pll_on |
| pll-prepare | 当前 VCO Hz | pll_on | 0 | 0 |
| pll-prepare-result | 当前 VCO Hz | pll_on | 有符号返回值 | 0 |
| pll-unprepare | 当前 VCO Hz | pll_on | 0 | 0 |
| mdp-request | 裁剪后的 OPP 请求 Hz | 旧 perf vote Hz | new bw_ctl | new max_per_pipe_ib |
| mdp-result | OPP 请求 Hz | CCF core Hz | 有符号返回值 | 0 |

`pll-set-begin/end` 位于真实 VCO 编程函数两侧；DCS begin/end 用于关联事务，end 仅表示执行到 restore，不证明面板收到了命令或成功解码。原生 `clk` 事件仍保留，并新增 MDP 时钟过滤。首帧实验移除旧的最多 16 次 stacktrace，减小取证扰动。

## 本阶段检查和真机条件

2026-11-21 只读连接检查：手机仍为 F.20，内核 `4.19.157-perf+`、`sys.boot_completed=1`，boot UUID `73e2bf96-93f9-41cf-916e-c3b5686f919e`。这不替代刷入前的完整恢复集检查。

当前正在进行补丁应用、源码检查与构建；尚未刷入第 68 轮。试验前核验唯一候选、原厂恢复集及固定输入，取得新的完整 trace 后再判断供数/PLL/面板时序假说。失败恢复 F.20；不做冷启动或看门狗故障注入重复测试。

源码 `477dfb25c2f3d937bee27d6179d42c4abff888a5` 已触发 [内核构建 #37](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/44875114557)。本地补丁链应用及反向检查通过，脚本编译和 shell 语法检查通过；构建成功与否需单独记录。

构建 #37 在 `dsi_host.c` 编译失败：新增的 `msm_dsi_host_first_frame_sample()` 位于 `to_msm_dsi_host()` 定义之前，触发隐式声明和类型冲突。修复只把新增函数移到现有转换函数之后，没有改变采样逻辑或显示参数。该次构建没有生成可用内核，也没有刷机；手机保持原厂 F.20。修正后重新检查补丁应用，再触发新构建。

修正源码 `57e5b0c8311e86e22fc41cb8fa7438f761e4c216` 已触发[构建 #38](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/44877291283)。修正补丁反向应用检查通过；包含首帧顺序与重复同 boot 标记两项新增用例的 M3 测试共 33 项全部通过、无跳过。此处记录的是构建中状态，不是构建成功或第 68 轮真机结果。

`decode_m3_first_frame.py --record <record> --output <json>` 复用同 boot 的严格 native capture 读取器，校验 arming/completion UUID、完整 trace 边界、导出事件数、八个 CPU 的丢失计数及必要采样点。它保留错误原始值、PLL/DCS 关联、样本上限提示，不输出根因或物理通过结论。六个单元测试覆盖 masked underflow、非错误 FIFO 状态、丢失/截断、boot 混用及实际 PLL 编程与请求的区别。

使用本地 Git Bash 执行先前跳过的四项测试后，本阶段全部 31 项 M3 测试通过，无跳过。原厂恢复集和当前候选的完整 super 字节、boot/DTBO、loader 与测试卷清单已校验；旧内核被打包器拒绝，未改写 boot 输出。[准备记录](../build/device/m3-first-frame-preparation-2026-11-21.json)

等待构建时补查了第 58–67 轮的已保存时钟：第 58–63 轮 byte/pixel 约 52.704/70.272 MHz，第 65–67 轮为 82.5/110 MHz，均曾有花屏。前组没有记录 MDP 实际频率，不能补造为 200 MHz；第 64 轮没有此次脚本选取的标准路径快照，未纳入表中。这限制了“只因当前 200/110 比例”的解释，不能用旧 MDSS 比例规则直接给 SM8250 下结论。

另核对了同系列 DSC 上游修复 [12cef323c903](https://github.com/torvalds/linux/commit/12cef323c903bd8b13d1f6ff24a9695c2cdc360b)：旧代码把字面量 22 写入 CTL_FLUSH，正确含义应是 bit 22。当前固定 ACK 的 `dpu_hw_ctl.c`（Git blob `ac834db2e4c16cfd2053f9761c49d91a02bcffa6`，已与远端固定提交核验）在 `update_pending_flush_dsc_v1()` 使用 `BIT(DSC_IDX)`，并在 `trigger_flush_v1()` 先写 DSC 子块 flush、再写总 flush。因此该旧修复的语义已存在，不能作为新的缺失补丁重复移植；这项源码核对也不替代首帧运行时证据。

## 第 68 轮真机结果

构建 #38 成功，选取成员及其源码/分发摘要核验通过；没有下载并验证整个包含模块的 ZIP。内核 SHA-256 为 `f04014b02687af42f74d0edf92aa6b62c21dea20c507529d5b67466508f7ac11`，boot 为 `e3704f8b7bd8ead3f75414de5240cca607941e7bbd57f2864a593e82b1745c77`。第一次本地打包遗漏了第 67 轮已有的 panel-readback 开关，被预检拒绝；补齐后 [20 项输入检查](../build/device/m3-first-frame-68-preflight-2026-11-21.json)全部通过才刷入。实际运行的 [43 项配置检查](../build/device/m3-stock-phy-68-runtime-2026-11-21.json)也全部通过。

真机 boot UUID `de8af50f-4951-4be9-8da1-196ca5eaf8ab`。用户分别反馈原生图“**一样仍有花屏**”、Android“**一样花屏**”。因此显示未通过，根因仍未确认；本轮是有效的首帧取证，不是花屏修复。GSI enforcing ADB 同 boot 检查持续 195.203 秒，SurfaceFlinger 和 maintenance 服务存在，activity/window 仍缺失，未达到桌面。[真机记录](../build/device/m3-display-68-2026-11-21.json)

[首帧解码记录](../build/device/m3-first-frame-68-2026-11-21.json)确认：

- trace 为 230/230 个事件，八个 CPU 的丢失计数全部为零；包含 power-ready、host-enable、五次 kickoff 和对应五次 PP done handler 采样，没有达到采样上限。
- 这 12 组原始状态没有解码到 FIFO underflow/overflow、timeout、ACK、PHY error 或 PLL unlock；没有 DSI error IRQ preclear 或 DPU underrun handler 事件。FIFO 的 `0x11111010` 与 PHY 的 `0x88888` 不能因非零就当作错误。
- 42 对 DCS 事务、43 次 link-rate 请求中，仅发生一次真实 PLL set-rate，位于首个 DCS 事务之前且 `pll_on=0`。DCS 事务内没有 PLL set-rate、prepare 或 unprepare。两次 prepare/unprepare 分别属于早期初始化和原生显示生命周期，不能混称为命令期重锁。
- MDP 在 33.589678 秒已以 166,017,600 Hz 请求落到实际 200,000,000 Hz；第一次 kickoff 为 33.741103 秒。采集窗口内没有“先正常出图、随后降频”的证据，原生结束时的关闭请求不能解释开始就出现的花屏。

这里的“完整”指已启用 trace 的导出完整、必要采样点齐全，不是所有电气错误都被连续观测。错误屏蔽保持原样；边界采样不能排除所有瞬态问题，也未覆盖 Android 接管后的操作。因此把“DCS 引发 PLL 重编程”降级为本次原生失败不支持的假说，而不是宣称整个 PHY/DSI 正常。没有据此盲目提高 MDP 频率。

下一步核对原厂实际执行的开屏命令/状态与项目执行顺序，以及 DSC 流格式和面板解码使能。原厂 DT 中的命令表此前已与 Q 源码比较相同；不能重复把静态表一致冒充实际执行一致。恢复 F.20 后先查可用的运行时命令追踪接口，不重复冷启动测试。

本轮用户要求复用唯一原厂备份、停止例行整区回读。恢复脚本已按此调整并通过 14 项相关检查；本轮候选回读已经完成，随后 F.20 恢复使用新策略，结果单独记录，不将原厂镜像的预期摘要写成新回读证据。

F.20 恢复于 07:37:19 UTC 完成，boot UUID 为 `357dcda6-83fa-46dc-9f61-3eb2eaedc0af`，开机完成、固件版本及两份 LP 元数据检查通过。原厂 boot/DTBO/super 的本次观测摘要明确为 null；唯一备份的摘要单列为 expected，写入获得 loader ACK，没有进行原厂整区回读或手机端 super SHA 扫描。[恢复凭据](../build/device/m3-display-68-restored-2026-11-21.json)

### 恢复后的原厂命令追踪接口检查

同 boot 的[只读清单](../build/device/m3-f20-dsi-trace-inventory-2026-11-21.json)发现 `/sys/kernel/oplus_display/dsi_cmd_log_switch` 存在、当前值为 `0`。固定版本[同平台源码的 getter/setter](https://github.com/SM8250-Common/android_kernel_realme_sm8250/blob/b76eb6c93add8152b1aa873da0d8d7f495cccab0/techpack/display/oplus/oplus_display_private_api.c#L2950)读写日志开关变量，但这不证明 F.20 的实际日志包含每条命令的完整载荷，也不把社区源码冒充精确的 F.20 二进制源码。

当前 tracefs 提供 `sde_evtlog`，未发现独立 DSI/DCS trace event；`available_filter_functions`、`kprobe_events` 不存在，debugfs 未挂载且 `/sys/kernel/debug` 不存在。因此本次没有取得 function/kprobe/dynamic-debug 能力，不能据此断言内核未编译这些功能。接口清单脚本用远端状态标记保留查询失败，避免 stock su/ADB 返回 0 时把缺失路径误记为成功。

本次没有启用日志、挂载 debugfs、切换显示、发送 DCS 或重启。下一步先验证该命令日志的覆盖范围，再在可恢复设置的短窗口内采集原厂显示开关过程，比较项目的开屏命令、PPS 和 DSC 使能顺序；若无法取得完整载荷，明确保留这一证据缺口。当前目标仍是消除实屏花屏后进入 AOSP 桌面，不根据无报错日志宣布链路正常。
