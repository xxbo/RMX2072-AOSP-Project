# 第 68 轮后的社区花屏案例对照

目标仍是项目 6.18 + Android 17 GSI + 移植驱动正确出图，再进入 AOSP 桌面。本次按用户要求搜索社区，读取开发者原始记录和源码，再与现有记录离线对照；没有访问手机、刷机、重启或重新回读原厂分区。

**结果：找到相似案例，并发现一个此前检查未覆盖的 EoT 配置差异；尚未确认花屏根因。** 原生 KMS 和 SSPP 硬件纯色也花屏，仍将重点放在其共有的 DPU/DSC/DSI/面板路径。

## 案例与适用边界

### 一加 7T Pro：最接近的噪声条带，但错误特征不同

设备为 SM8150，三星命令模式 DSC。开发者的 [8 月 17 日记录](https://github.com/Sr-0w/hotdog-linux-bringup/blob/47087509c4289c2580c54f5433e55366b2e00445/docs/evidence/2026-08-17-dsi-dsc-transport-errors.md)描述 RGB 噪声与周期条带，错误日志为 FIFO/timeout，四条 HS lane 同时欠载；DPU underrun 计数却为零。完整面板重新初始化后可恢复，扩大 DSI soft-reset 范围反而破坏 CTL start。

较新的 [8 月 20 日记录](https://github.com/Sr-0w/hotdog-linux-bringup/blob/47087509c4289c2580c54f5433e55366b2e00445/docs/evidence/2026-08-20-display-regression-01.md)仍将状态列为未解决的间歇性退化，锁屏再解锁恢复，而非永久修复。

我们的第 68 轮是初次接管就花屏，12 个边界样本未捕获上述错误，FIFO 为 `0x11111010`，并非案例中的四通道欠载特征。因此它支持“失步后可能需要完整面板生命周期恢复”和“DPU 无 underrun 不代表整条链路正常”，不能证明本机也欠载。记录提供的是开发者观察，原始本地日志未公开供本次独立复验。

该项目[更早的初次出图记录](https://github.com/Sr-0w/hotdog-linux-bringup/blob/47087509c4289c2580c54f5433e55366b2e00445/docs/evidence/2026-08-03-native-display.md)还涉及 slices-per-packet 和在 on-sequence 之后发标准 PPS。RM19795 已验证两个 slice/packet，并通过厂商 `0x9e` 在原有位置发送 88 字节 PPS；不同 DDIC 的顺序不能照搬。它提示应核对实际执行顺序，而不是再次改已核验的静态参数。

### Redmi K30 Pro / POCO F2 Pro：同 SM8250 的启动接管条纹

[项目备注](https://github.com/ccc007ccc/linux-sm8250-xiaomi-lmi/blob/3a8409fb1020b5952310072713ce97edea5e65d7/lmi/ADAPTATION_NOTES.md#display--samsung-ams667uu01)称早期白屏/条纹通过 lmi 专用 bootshim 在进入 Linux 前拉低面板 reset 解决。该文档明确标注 AI 整理；本次未取得这项 bootshim 修改的直接前后日志，作为待核对线索，不升格为已独立验证的根因。

能直接核对的 [AMS667UU01 驱动](https://github.com/ccc007ccc/linux-sm8250-xiaomi-lmi/blob/3a8409fb1020b5952310072713ce97edea5e65d7/drivers/gpu/drm/panel/panel-samsung-ams667uu01.c)确实包含 prepare 时的硬件 reset 和完整 on/off 生命周期。

RMX2072 并非没有 reset：项目使用 GPIO75、active-low，按原厂 high 20 ms → low 10 ms → high 5 ms 执行；本次离线 F.20 DT 再次确认了这些数值。若继续追此方向，需要证明引脚实际电平、reset 与首条命令的时间关系，不能照搬 GPIO46 或仅在软件里重复同一序列。

第 68 轮原生退出记录本来就包含 `0x28`/`0x10`、PLL unprepare 和 host power-off，随后 Android 仍花屏。因此普通地重跑现有 off/on 流程不能包装成新修复；引脚实际复位、时机及面板内部状态仍须分别验证。

### 小米 10：同 SM8250 的命令解析与面板状态陷阱

[显示开发记录](https://github.com/colorgarden/umi-mainline/blob/e38cb76b41c9d33bf5145732381dbf55f5f7cf1b/docs/DISPLAY.md)修正过下游命令头长度、数据长度和短写类型的误解，也记录过 host 正常而面板黑屏、重新发送 on-sequence 恢复的情况。文档有历史阶段文字，不能把每段“当前”都当作最新状态。

本次核对了[固定版本驱动](https://github.com/colorgarden/umi-mainline/blob/e38cb76b41c9d33bf5145732381dbf55f5f7cf1b/patches/panel-xiaomi-umi.c)：保留包类型、等待和完整序列，按自己的 DT 设置 EoT。其华星面板与 RM19795 不同，标准 PPS API、复位延迟及私有命令不可直接移植。我们的生成器已保留 RM19795 的 `0x39` 两字节长写、短写长度和等待时间，缺口主要是原厂实际运行时的发送序列及 host flags。

### Google SM8150 原厂代码：空包插入确实有过花屏关联

Google 的 [sm8150-floral-display.dtsi](https://android.googlesource.com/kernel/msm/+/184170bea097dec34b9871fc724dcac9b5989427/arch/arm64/boot/dts/google/sm8150-floral-display.dtsi)明确在三星 DSC 命令模式面板配置中启用 `qcom,null-insertion-enabled`，并注明缺少它会花屏。这是一条具体的一手代码线索，不是所有 Qualcomm DSC 面板都必须开启的规则。

我们离线合成 F.20 DTB12 + DTBO17 后，整个选中设备树没有该属性；第 68 轮对应寄存器值也为零。当前没有“原厂开、项目关”的证据，因此不立即加这个开关。

### 之前已查的 Xperia / Lenovo 线索

Xperia 5 II 的 SM8250 DSC bring-up 和 Lenovo Q706F 的命令期 PLL 重编程问题见[此前调查](M3_DISPLAY_RESEARCH_2026-11-21.md)。本次不把它们重新包装成新发现：第 68 轮已记录 DCS 内没有实际 PLL set-rate/prepare/unprepare。不能单凭别机亮度操作花屏，就跳过本机 `link_clk_set_rate()`。

drm/msm GitLab issue 24 本次仍被 Anubis 拦截，issue 42 未能读取正文。没有据此引用 issue 内容或声称已有适用补丁。

## 新的本机差异：EoT 追加配置

上述对照促使我们把之前未覆盖的传输 flags 加入离线检查。[审计 JSON](../build/device/m3-transport-flags-68-2026-11-21.json)使用唯一原厂恢复集与第 68 轮已采集的同 boot 快照，没有产生新镜像。

| 项目 | F.20 选中 DT / 参考实现 | 第 68 轮原生实测 |
| --- | --- | --- |
| TX EoT append | 面板节点没有 `qcom,mdss-dsi-tx-eot-append`；参考下游按 read_bool 取 false | `EOT_PACKET_CTRL=0x1`，bit0=1 |
| RX EoT ignore | 属性不存在，参考实现取 false | bit4=0 |
| NULL insertion | 选中树无启用属性 | 控制寄存器为 0 |
| reset | GPIO75，high 20 / low 10 / high 5 ms | 项目源码有同一序列；这不是引脚波形测量 |

**EoT 这一项有明确配置差异，但尚缺 F.20 的实际寄存器证据。** 同平台参考源码不是 F.20 二进制的完全对应源码，不能用 DT 推断冒充运行时读取。现有 43 项检查覆盖 PPS、PHY、时钟、路由和固定输入，没有覆盖所有 host flags。

语义依据为参考下游 [dsi_panel.c](https://github.com/SM8250-Common/android_kernel_realme_sm8250/blob/b76eb6c93add8152b1aa873da0d8d7f495cccab0/techpack/display/msm/dsi/dsi_panel.c#L2086) 的布尔解析，以及 [dsi_ctrl_hw_cmn.c](https://github.com/SM8250-Common/android_kernel_realme_sm8250/blob/b76eb6c93add8152b1aa873da0d8d7f495cccab0/techpack/display/msm/dsi/dsi_ctrl_hw_cmn.c#L111) 的寄存器写入。项目面板未设置 `MIPI_DSI_MODE_NO_EOT_PACKET`，固定 [ACK host](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/gpu/drm/msm/dsi/dsi_host.c#L878) 因而追加 EoT；这与快照一致。

必须注意寄存器基址：下游 EoT CTRL 为资源偏移 `0xcc`，NULL insertion 为 `0x2b4`。ACK 6G 的 `ctrl_base` 已加 `DSI_6G_REG_SHIFT=4`，快照分别是 `0xc8`、`0x2b0`。直接对比同名偏移会读错；本次已核对固定版 `dsi_cfg.h/c` 和 snapshot 实现。

## 下一步优先级

1. 优先查 F.20 已验证接口能否只读取得 EoT/NULL 寄存器，以及命令日志开关是否输出完整载荷。只取目标显示状态，不回读整区原厂数据；接口不具备时明确保留缺口。
2. 核实差异后，可设计只改变 RM19795 `NO_EOT_PACKET` 的对照，保留第 68 轮 PPS、PHY、660 MHz、拓扑、图案和测试卷，确认实际 EoT bit 改变后再评价实屏。它是待验证假说，不预称修复。
3. 若该差异不能解释故障，再核对 reset 电平/时序、实际开屏命令与 DSC/PPS 使能顺序；完整面板重新初始化可以作为区分状态失步的显示生命周期对照，不重复整机冷启动。
4. 保留首帧错误采样，不把“无 DPU underrun”升级成“DSI/PHY 正常”，也不扩大自动 DSI soft reset 作为补救。

本阶段结束：研究和离线对照已完成，真机新结果为“未实验”；最近实屏结果仍是第 68 轮两阶段花屏。下一阶段目标是验证 EoT 差异及原厂实际发送状态，不改动 GSI/桌面层来掩盖底层花屏。

## 复现

从工作区运行，命令只读取已保存文件：

```powershell
python work/repo/scripts/device_audit/audit_m3_transport_flags.py --boot work/recovery/f20/boot.img --dtbo work/recovery/f20/dtbo.img --cmdline work/records/f20-disconnected-power-control-2026-11-14/cmdline.txt --libfdt work/current/dtc-tools/libfdt-1.dll --record work/records/ufs-host-g3-gsi17-firststage-ufs-68 --output work/repo/build/device/m3-transport-flags-68-2026-11-21.json
```

社区源文档和代码只保存了小型本地参考文件；[来源清单](../build/device/m3-community-sources-2026-11-21.json)固定仓库提交、路径和本地规范化摘要。原始第三方文档没有复制入项目仓库，本文仅保留必要分析与原文链接。
