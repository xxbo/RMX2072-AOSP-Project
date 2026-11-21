# 第 67 轮复核与 SM8250 花屏调查

当前目标：修复 6.18 原生显示输出，让 Android 17 GSI 正确显示，再推进 AOSP 桌面。**根因仍未确认。** 本阶段只复核已有真机证据、检索同芯片案例并核对源码，没有刷机、重启或新的真机实验。

## 第 67 轮是有效的失败结果

用户在 2026-11-21 补充：“67轮仍然没有改善，还是一样的花屏”。这条反馈没有分别描述原生与 Android 阶段，记录为本轮整体实屏失败，不补写两个独立观察。

11 月 20 日暂停时的记录保持不变。当时没有收到实屏结果，随后恢复 F.20；本次使用其已发布摘要复核保存的 `m3-display-at-pause.txt`，没有伪造 `gsi-accepted.json`，也没有补算未执行的 190 秒稳定性测试。

[运行时复核](../build/device/m3-stock-phy-67-runtime-2026-11-21.json)的 **43 项配置检查全部通过**：

- boot UUID 为 `790e9ef8-5e41-4066-8117-12222897de92`，快照与当时 host gate 事件一致；输入、ACM、host 事件及快照的摘要与暂停记录一致。
- PHY 十四字节为 `00 17 06 05 21 20 06 06 04 02 04 00 14 15`，恰好只有三个预期字段改变，host CLKOUT 为 `0x1514`。
- 原厂 88 字节 PPS、已解码 DSC 编码器字段、660/82.5/110 MHz 链路时钟、单 DSC 路由和分包设置均符合实验预期。
- GSI、项目 vendor、测试卷种子、源码设备树、探针及固定图没有改变。

结论是**单独对齐这三项 PHY 时序没有修复花屏**，不是“修复没有刷进去”，也不是排除了整个 PHY/DSI 层。[反馈及复核记录](../build/device/m3-display-67-reviewed-2026-11-21.json)

## 已有证据限定了哪些范围

| 真机证据 | 支持的判断 | 仍不能断言 |
| --- | --- | --- |
| F.20 正常；realme 标志正常，6.18 接管后花屏 | 优先检查 Linux 显示接管与数据输出 | 单凭标志正常不能确认面板初始化完全正确 |
| 原生 KMS 同图也花屏 | Android HWC/SurfaceFlinger 不是故障出现的必要条件 | 不是所有 Android 图形问题均已排除 |
| 硬件 SSPP 纯色仍有噪声和缺失 | framebuffer 地址、pitch、UBWC、缓存同步不是该现象的必要条件 | DSC、DSI、面板解码及供数时序仍在路径中 |
| 单 LM/DSC 与此前双 DSC 均花屏 | 双路合并不是必要条件 | 不能由此证明任一路拓扑的所有时序均正确 |
| 对齐原厂链路频率、完整 PPS、三项 PHY 时序仍失败 | 这些单项差异不足以解释故障 | 不等于原厂的动态时序、供数预算和面板内部状态已复现 |

照片中的规则条带提示分片/流同步问题，但颜色条本来逐行重复，拍照又有透视和屏幕扫描效应；此前“144 行 = 3×48”的关系只是线索，不作为根因证明。

## 同芯片及相关一手资料

### Xperia 5 II：SM8250、三星命令模式 DSC

2022 年的 [DSC Electric Boogaloo 讨论](https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2212.2/04919.html)确实记录过 SM8250 Xperia 5 II 在 60/120 Hz 下严重花屏。后续 [2023 面板系列](https://patchew.org/linux/20230521-drm-panels-sony-v1-0-541c341d6bee@somainline.org/)已经报告 DSC 可工作；[2025 v2 及 2026 年回复](https://patchew.org/linux/20251222-drm-panels-sony-v2-0-82a87465d163@somainline.org/)继续讨论命令模式传输预算、DCS/亮度操作造成的画面损坏，后来又报告相关机型能运行主线面板。

这些材料证明同芯片有可工作的实现，也说明“PPS 对了”不覆盖运行时传输行为。它们没有证明我们的故障与 Xperia 是同一原因。原讨论引用的 drm/msm issue 24 本次被站点 Anubis 拦截，没有读取其正文，不把该页面当作已经核验的结论来源。

### 已有修复必须与当前代码逐项核对

| 上游线索 | 当前适用性 |
| --- | --- |
| [每包多个 DSC slice，ce73a5db44e3](https://github.com/torvalds/linux/commit/ce73a5db44e3d5f9c0c061f0868ae209b59605f1) | 项目已回移；第 59 轮开始验证，67 仍保留两个 slice/packet。不能再次当作未尝试的新修复 |
| [slice_last_group_size，c223059e6f83](https://github.com/torvalds/linux/commit/c223059e6f8340f7eac2319470984cbfc39c433b) | 当前 ACK 使用 `(slice_width + 2) % 3`；540 宽得到 2，既有寄存器也为 2 |
| [BPC 泄漏到 DSC_ENC，144429831f44](https://github.com/torvalds/linux/commit/144429831f447223253a0e4376489f84ff37d1a7) | 当前源码已用 `bits_per_component == 10`，本机是 8 bpc；不是直接遗漏的补丁 |
| [命令模式 BURST，b173a7dcc2d0](https://github.com/torvalds/linux/commit/b173a7dcc2d06ee11f739c1bdcd51ee156b6d50c) | 第 66/67 轮 CMD_MODE_MDP_CTRL2 的 BURST 已启用；DATABUS_WIDEN 为 0，不能套用其他代际的 widebus/video-mode 修复 |
| [运行时 DCS 重新锁 PLL，6cd33b6f4155](https://github.com/torvalds/linux/commit/6cd33b6f4155efc20485929fd0b56bb704641db9)及[修正 rounding 时机，2028280686f4](https://github.com/torvalds/linux/commit/2028280686f4fa78e2f1f6dede4b6c1fd782b9e3) | 当前固定 ACK 源码没有 byte clock rounding；保留为待测线索。但已保存的 82.5 MHz CCF 读数恰好等于请求值，且本机为命令模式，尚未证实重锁触发条件 |

[Q706F 的开发者补丁](https://github.com/dasudiy/pmos-lenovo-q706f/blob/main/patches/0006-drm-msm-dsi-skip-link-clk-set-rate-on-runtime-cmd.patch)提供了 SM8250 系列运行时命令导致花屏的案例。但它直接跳过 `link_clk_set_rate()`，与上游后来保留 OPP/传输流程、正确取整频率的方案不同。不能不加分析就照抄跳过调用；也不能用视频模式面板的复现替代 RM19795 实测。

## 新确认的测量缺口：我们没有完整首帧错误历史

[离线审计结果](../build/device/m3-first-frame-gap-2026-11-21.json)使用固定版本源码并核验 Git blob：ACK `ecdaacc9…` 的镜像 `cfa72fb3…`，以及 SM8250 社区下游 `b76eb6c9…`。后者用于解释寄存器语义，不冒充 F.20 的精确二进制源码。

第 67 轮翻页后 `ERR_INT_MASK0=0x13ff3be0`。按[下游 enable_error_interrupts](https://github.com/SM8250-Common/android_kernel_realme_sm8250/blob/b76eb6c93add8152b1aa873da0d8d7f495cccab0/techpack/display/msm/dsi/dsi_ctrl_hw_cmn.c#L1197)的“清 bit 才启用”实现：

| 事件 | mask bit | 本次采样 |
| --- | --- | --- |
| CMD_MDP_FIFO_UNDERFLOW | 11 | 屏蔽 |
| CMD_DMA_FIFO_UNDERFLOW | 9 | 屏蔽 |
| HS_TX / LP_RX / BTA timeout | 6 / 5 / 7 | 屏蔽 |
| PLL_UNLOCK | 28 | 屏蔽 |
| 各 HS lane overflow | 16–19 | 屏蔽 |
| 各 HS lane underflow | 26 / 27 / 29 / 30 | 未屏蔽 |

此外，[ACK dsi_error 路径](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/gpu/drm/msm/dsi/dsi_host.c#L1555)会读取并清除错误寄存器，再交给 worker 输出聚合状态。**翻页后的无错误快照、没有 worker 日志，均不足以排除开屏瞬间的错误。** 反过来，屏蔽某中断不等于已经发生该错误，也不等于硬件状态位不会锁存；四条 HS lane 欠载未屏蔽，也构成对“持续全通道欠载”假说的限制。

这是目前最明确的取证缺口。先补测量，比继续无依据替换 PHY 数值更能区分原因。

## MDP 供数预算：有根据的候选，尚未证明

第 67 轮 `disp_cc_mdss_mdp_clk` 在 native modeset 前为 **460 MHz**，之后及翻页后为 **200 MHz**；同次 DSI pixel 为 **110 MHz**。现有 [F.20 trace](../build/device/m3-core-perf-followup-2026-11-20.json)也有 60 Hz 区间的 460 MHz 请求，随后会降到 200 MHz，不能只选择前一个频率作结论。

[ACK core perf](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/gpu/drm/msm/disp/dpu1/dpu_core_perf.c#L92)基于 `vtotal × hdisplay × refresh` 与 plane 需求计算；本模式的基础预算乘 105% 为 166,017,600 Hz，实际落到 200 MHz。相比之下，[SM8250 下游 dsi_panel_calc_dsi_transfer_time](https://github.com/SM8250-Common/android_kernel_realme_sm8250/blob/b76eb6c93add8152b1aa873da0d8d7f495cccab0/techpack/display/msm/dsi/dsi_panel.c#L5053)显式计算每帧传输预算并传给后续路径。当前原厂日志报告约 7956 µs，不能简单等同于 60 Hz 的 16.67 ms 帧周期。

高通[旧 MDSS 提交 eb007e67](https://android.googlesource.com/kernel/msm/+/eb007e67c594a2b6f94acd2b95c27565ba1fb62d)解释过“一个 DSC 编码器处理两个软分片、没有 merge”时 MDP/DSI 比例不合适造成欠载。**它是 2015 年其他代际的部分更新修复，不是 SM8250 规格或本机根因证据。** 可以指导测试，不能据此推导本机的硬性频率下限。

必须保留的反证/限制：此前双 DSC 也花屏；硬件每周期吞吐、背压和缓冲深度未测量；原厂与测试图负载不同。提高 MDP 频率即使改善，也还需重复对照才能确认机制。

另外，不能直接使用 `perf_mode=2` 并让 `fix_core_ab_vote/fix_core_ib_vote=0` 来做“只改时钟”实验。[同一 core perf 实现](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/gpu/drm/msm/disp/dpu1/dpu_core_perf.c#L220)会同时覆盖总线带宽投票，这会引入第二个变量。本阶段未写这些控制项。

## 下一轮应回答的具体问题

先准备一次**首帧取证**候选，保持第 67 轮 PPS、PHY、链路时钟、拓扑及测试图：

1. 在正常 IRQ 处理清位之前，保存有上限的原始 FIFO、timeout、ACK、PHY、PLL、mask 和 IRQ 状态；记录 boot UUID、时间与提交阶段。初始化、首次 kickoff、首帧完成各有对应采样。中断中只记录固定大小数据，延迟输出，避免大量 printk 干扰时序。
2. 记录开屏命令、亮度命令与首次提交的先后，跟踪请求/round/实际 byte、pixel、MDP 时钟，以及 PLL 真正 set-rate/prepare 次数。区别“调用了 clk_set_rate”与“硬件实际重编程”。
3. 对被屏蔽的错误，先确认状态位锁存/清除语义和中断处理兼容性；不能一次性开放全部错误并改变自动 reset 行为。记录 masked 状态是证据要求，不是要求盲目清 mask。
4. 如果首帧出现供数错误，再做独立的 MDP clock floor 对照：保留正常带宽投票与 OPP 路径，仅在本 SoC/面板使用已观测的原厂频点；核验实际频率及其余配置不变。重新完整初始化面板后比较，避免失步状态残留。
5. 如果发现 DCS 引发真实 PLL 重编程，评估完整的上游 rounding 修复及其后续修正；若没有这种行为，该线索降级。若首帧无供数/时钟异常，则回到面板命令顺序、复位/使能、DSC 流格式与解码状态的原厂对照。

不把关掉 DSC 后的黑屏当成有效对照：尚未确认 RM19795 能以当前初始化接受非压缩流。DSI 自带 test pattern 也需要先核实命令模式/压缩协议支持，不能直接拿视频模式 TPG 代替 DSC 数据。

本阶段没有构建或刷入第 68 轮。测试前只保留原厂恢复集和当前候选。实屏完整、持续正确才算显示通过；随后才继续 Health HAL / SystemServer / Launcher。保持现有 GSI 和测试卷，不重做冷启动或看门狗故障注入。

## 复核方法与验证

新增 `compare_m3_stock_phy.py --pause-record`，通过已发布暂停清单校验四份证据和同 boot host gate，显式区分 native 配置复核与 GSI 验收。新增四个回归测试，拒绝证据修改、boot 混用、未完成探针，以及缺失 acceptance 时的隐式回退。M3 测试共 21 项：17 通过、4 项环境相关跳过。

`audit_m3_first_frame_gap.py` 在离线快照上解码错误屏蔽和时钟样本，并校验四份源码及寄存器 XML 的 Git blob；不访问手机。

从仓库目录运行（外部原始记录不入库）：

```sh
python scripts/device_audit/compare_m3_stock_phy.py \
  --baseline ../records/ufs-host-g3-gsi17-firststage-ufs-66 \
  --record ../records/ufs-host-g3-gsi17-firststage-ufs-67 \
  --reference build/device/m3-dsc-pps-reference-2026-11-15.json \
  --panel-source ../reference/m2/realme-q/arch/arm64/boot/dts/20607/dsi-panel-rm19795samsung-ams641rw01_1080_2340.dtsi \
  --pause-record build/device/m3-display-67-paused-2026-11-20.json \
  --output build/device/m3-stock-phy-67-runtime-2026-11-21.json

python scripts/device_audit/audit_m3_first_frame_gap.py \
  --record ../records/ufs-host-g3-gsi17-firststage-ufs-67 \
  --pause-record build/device/m3-display-67-paused-2026-11-20.json \
  --sources ../reference/m3/research-2026-11-21 \
  --dsi-xml ../reference/m3/dsi.xml \
  --output build/device/m3-first-frame-gap-2026-11-21.json
```
