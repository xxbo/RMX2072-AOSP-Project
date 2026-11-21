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

`decode_m3_first_frame.py --record <record> --output <json>` 复用同 boot 的严格 native capture 读取器，校验 arming/completion UUID、完整 trace 边界、导出事件数、八个 CPU 的丢失计数及必要采样点。它保留错误原始值、PLL/DCS 关联、样本上限提示，不输出根因或物理通过结论。六个单元测试覆盖 masked underflow、非错误 FIFO 状态、丢失/截断、boot 混用及实际 PLL 编程与请求的区别。

使用本地 Git Bash 执行先前跳过的四项测试后，本阶段全部 31 项 M3 测试通过，无跳过。原厂恢复集和当前候选的完整 super 字节、boot/DTBO、loader 与测试卷清单已校验；旧内核被打包器拒绝，未改写 boot 输出。[准备记录](../build/device/m3-first-frame-preparation-2026-11-21.json)

等待构建时补查了第 58–67 轮的已保存时钟：第 58–63 轮 byte/pixel 约 52.704/70.272 MHz，第 65–67 轮为 82.5/110 MHz，均曾有花屏。前组没有记录 MDP 实际频率，不能补造为 200 MHz；第 64 轮没有此次脚本选取的标准路径快照，未纳入表中。这限制了“只因当前 200/110 比例”的解释，不能用旧 MDSS 比例规则直接给 SM8250 下结论。
