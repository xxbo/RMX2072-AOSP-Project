# trial 65 手动重启后的门控超时与 F.20 恢复

本阶段目标是停止循环重启、保存日志并恢复可用系统。显示花屏和 AOSP 桌面目标保持不变，本次没有追加显示试验、冷启动试验或看门狗故障注入。

## 触发与证据

用户说明：“按电源键或手动重启后开始”。电脑接入时发现的是 6.18 诊断串口 COM7，没有 GSI ADB。

- 第一次串口采样对应 boot `f141a3d2-45c7-488d-8274-3bd700abae1e`，uptime 为 179.19 秒，仍在诊断 initramfs。
- 随后新 boot `5af855be-cf59-43ff-9f7a-42ae8d304ccb` 在 59.97 秒可读；trial ID 仍为 65，返回定时器为 180 秒。`/run/m3-display-gate-ready` 对应该 boot，`/run/m3-display-start` 不存在，PID 1 仍是诊断 shell，Android 尚未启动。
- 上一次启动的 ramoops 中保留了可读行：`[181.242229] reboot: Restarting system with command 'edl'`。该日志同时报告 1979 corrected bytes 和 1270 unrecoverable blocks，内容部分损坏。这里只将可读行与当前门控状态、源码相互核对，不能把整份日志当作完整可靠记录，也不能据此排除所有其他故障。

`m1-autoboot.sh` 的 `/m3-display-staged` 分支每次开机都等待电脑写入本次 boot ID；`diag-supervisor.sh` 独立运行 180 秒 EDL 返回定时器。上次 GSI 的 `retained` 只表示当次 Android guard 保留运行，并不会改写下一次开机的门控策略。

因此，本次确认的是手动重启后重新进入测试门控、未获放行而触发 EDL 返回。没有证据将初始触发归为 GSI 自行崩溃。定时器请求 EDL 后为何没有持续停留在 EDL，仍未单独定位；不能声称该部分已验证自动恢复。主机这次在采集后主动发送 EDL，成功进入 Sahara 恢复。

## 收尾与防止误报

恢复使用原有 F.20 恢复集，仅回写 boot、DTBO 和 super。原厂 userdata 不写入；仍只保留恢复集与当前候选。逐块回读、开机身份、LP 元数据和完整 super 摘要的最终证据见 [恢复记录](../build/device/m3-reboot-loop-recovery-2026-11-20.json)。连续 ADB 观察不包含额外重启。

最终 19 次回读全部匹配（boot、DTBO、17 块 super）；F.20 开机完成、两份 LP 元数据和手机端完整 super 摘要均匹配。boot `f9eda4c4-f202-4130-b68d-4cfb3e25d287` 连续观察 192.422 秒，最终 uptime 为 217.28 秒，跨过原来的 180 秒返回点，没有出现新 boot。用户确认“已正常显示，暂未再重启”。手机留在 F.20，恢复与观察进程已结束。

已修正打包器与 trial runner 的结果描述：

- 显式保存 `boot_start_policy` 和 `host_start_required_after_every_reboot`。
- 保留结果明确标注 `retention_scope=current-boot-only`；staged 镜像输出每次重启仍需主机放行的说明。
- 更正 trial 65 暂停记录文档中“自主交接”的措辞。源码顶部也明确区分自主 UFS 启动与主机门控显示实验。

这些改动仅修正元数据和描述，没有改变或验证新的启动策略。此次解除循环使用 F.20 恢复。以后若继续把 GSI 留在手机上，必须先处理 staged 镜像重启仍依赖电脑的问题，不能以当次 ADB/guard 正常替代这个条件。
