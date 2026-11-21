# F.20 实际 PPS 顺序与第 69 轮实屏修复

当前目标：项目 6.18 + Android 17 GSI + 源码/移植驱动进入 AOSP 桌面。第 69 轮已在原生和 Android 阶段通过用户实屏验收，下一步处理 Android 框架启动阻塞。本阶段没有重复冷启动或原厂整区备份。

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

与第 65 轮的 ACK 默认 PPS 对照，前 88 字节也不是完全相同：偏移 86 为 ACK `0x6b`、原厂标准包 `0x63`，最后一组 RC range 的 min-QP 分别为 13、12。因此也不能把旧 ACK 默认参数的实验等同于原厂标准 PPS 路径。

完整 on-sequence 对照也通过：原厂唤醒后的前 28 条命令，其类型、载荷和声明的等待值全部与项目导入的 60 Hz 命令表相同，均为 LP，随后才出现额外标准 PPS。这使“仅补发标准包”的对照有明确边界；不等于其他寄存器或面板内部状态已经相同。

参考[下游 dsi_display_enable](https://github.com/SM8250-Common/android_kernel_realme_sm8250/blob/b76eb6c93add8152b1aa873da0d8d7f495cccab0/techpack/display/msm/dsi/dsi_display.c)在 `dsi_panel_enable()` 后调用 `dsi_panel_update_pps()`，与本次实际顺序相符。参考源码不是 F.20 二进制的完全对应源码，本次结论以真机发送日志为依据。

**纠正此前边界：第 66–68 轮所谓匹配“原厂 PPS”，实际只匹配选中 DT 的静态 `0x9e`，不代表原厂最后发送的运行时 PPS。** 既有 43 项配置检查没有验证这一命令差异，不能解释成原厂完整显示状态均已复现。

## EoT 的缺口

本次实时 `/proc/config.gz` 确认 DEBUG_FS、DEVMEM、PROC_KCORE、KPROBES、DYNAMIC_DEBUG、FUNCTION_TRACER 均未启用。已检查的 host register dump 只通过 debugfs 提供，厂商 panel/dsi_cmd 接口不是 host MMIO 读取。没有取得 F.20 EOT_PACKET_CTRL 实测值，不能把 DT 推断升级为运行值。保留 EoT 假说，优先测试已经捕获到的缺失标准包。

## 第 69 轮：只补发标准包

源码增加默认关闭的 `panel_samsung_rm19795.pps=1` 开关，在原有完整 on-sequence 后、display-on 前，以 LP 发送类型 `0x0a` 的 128 字节 PPS。内容由同一 `ctx->dsc` 打包，与当前编码器及 `0x9e` 一致；失败时退出 prepare，不能把传输失败当作出图成功。

保持第 68 轮的编码器参数、原有 `0x9e`、660 MHz、PHY、EoT、单 DSC 路由、测试图、GSI 和可写测试卷。**这轮隔离“补发标准包”的影响，不同时切换到 F.20 后发包的 RC 参数。** 因而这也不是完整复刻原厂 PPS 路径。若无改善，后续再单独评价运行时 RC 参数。

验收需要三层证据：完整 128 字节发送记录与返回值、编码器/原有输入保持不变、用户观察原生和 Android 实屏。编译成功或发送返回非负不等于花屏修复。测试失败恢复 F.20；仅保留原厂恢复集和当前候选。

新增的发送记录检查拒绝缺块、重复块、负返回值、短返回值和错误长度，并关联同 boot 首帧中的包类型、LP 标志及先后顺序。打包[负向检查](../build/device/m3-standard-pps-packer-guard-2026-11-21.json)确认旧第 68 轮内核不能配上新 PPS 开关，原候选元数据未被改写。

以下保留实验前的假说和对照边界；实际构建和真机结果见后文。

构建记录：首次工作流 #39 因提交参数同时打开 legacy PON 和 source PON，在入口互斥检查退出，未开始内核编译、未生成候选。修正为 `pon_power=false, source_pon=true, display=true` 后，同一源码提交 `c8ce89da8b1451ba48a2ba3c84b334380763164a` 的工作流 #40（44884169265）开始构建。该主机参数错误未涉及手机刷写。

## 第 69 轮真机结果：两阶段均正常

工作流 #40 成功，选取的内核及源码清单摘要校验通过；没有声称校验完整 ZIP 摘要。当前候选打包配方为 `5806bae317f096540a100b15ed60b61dd54e640f`，22 项刷前检查全部通过，候选 super 的 17/17 分段回读通过。原厂恢复文件继续复用同一份，没有新建原厂镜像副本或再次回读原厂整区。

同一次真机启动 `a1ffd3bd-be48-43d9-9822-98839f722720`：

- 原生阶段用户反馈：**“显示的图案完全正常，未出现噪点！”**
- Android 接管后用户反馈：**“完整！正常！你做到了”**
- `RMXPPS standard-transfer ret=132 payload=128`；完整四块载荷验证通过。首帧轨迹确认 LP、类型 `0x0a`，位置在原有厂商命令之后、display-on 之前。
- 与第 68 轮比较的 46 项运行配置检查全部通过：原有 PPS/编码器参数、660 MHz 时钟、PHY、EoT、路由、测试图、GSI、源码启动组件及测试卷保持一致，原有命令序列仅增加标准 PPS。
- API 37、6.18.32 内核、SELinux enforcing、认证 GSI ADB 在同一 boot 完成 194.687 秒检查，进入 retained；SurfaceFlinger、composer、allocator 和 maintenance 已注册。
- Android 内部截图为 1080×2400，SHA-256 `9bbc264ead848e3b73af9a083165f3a309445c852d170e6d653b031ac923dccc`，与第 61 轮同一测试图截图逐像素一致。此前内部图正确而实屏花屏，本次实屏成功由上述用户反馈独立确认。

这组单变量结果支持：**项目面板初始化缺失标准 PPS 是当前花屏的关键软件缺陷，补齐后该配置下的原生和 Android 实屏均恢复正常。** 没有把成功扩大为所有刷新率、面板休眠唤醒、硬件 GPU 或桌面已经通过；也没有声称读到了 DDIC 内部解码状态，或完整复现 F.20 的最后一份 RC 参数。

证据：[刷前检查](../build/device/m3-standard-pps-69-preflight-2026-11-21.json)、[46 项运行对照](../build/device/m3-standard-pps-69-runtime-2026-11-21.json)、[完整首帧解码](../build/device/m3-first-frame-69-2026-11-21.json)、[两阶段实屏及 Android 状态](../build/device/m3-display-69-2026-11-21.json)、[验收摘要](../build/device/m3-standard-pps-69-result-2026-11-21.json)。

## 下一阶段：让 Android 框架进入桌面

本轮没有改动 Android 框架、测试卷或图形栈来掩盖显示结果。同一 boot 的只读检查发现 `installd` 未注册，PackageManager 多次等待 installer 超时；`activity`、`window` 和 `sys.boot_completed` 尚未就绪。下一步先查清 installd 的 init 导入、可执行文件和启动失败记录，再验证包管理、ActivityManager、WindowManager 与 Launcher。此处是已观察到的阻塞，不宣称是桌面的唯一剩余问题。

手机留在当前 GSI，未恢复 F.20。当前镜像仍带分阶段观察的主机门控：**再次重启仍需电脑观察器放行，否则会进入 180 秒 EDL 回退**。本次 retained 只保证当前启动的调试状态；下一阶段需在保存显示成功基线后处理正常启动入口，不重复冷启动或看门狗故障演练。磁盘仍只保留原厂恢复集和当前候选固件。
