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
