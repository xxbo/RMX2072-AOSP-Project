# RMX2072 花屏原因分析与排查方案

2026-11-18 最新补充：[原厂正常显示与早期开屏时钟对照](M3_STOCK_LINK_CLOCK_2026-11-18.md)。F.20 正常实屏与开机 trace 确认 60 Hz 区间的 DSI bit/byte/pixel 设频为 660/82.5/110 MHz；trial 64 约为 421.6/52.7/70.3 MHz。下一项实验仅对齐这组传输时钟，根因及实屏修复尚未确认。

适用状态：RMX2072，trial 60 / kernel 30，用户于 2026 年 11 月 16 日确认。代码基线为 [PR #22](https://github.com/xxbo/RMX2072-AOSP-Project/pull/22) 的 `bringup/m3-display` 分支，提交 `0e905be5ab76b250b93bab3507d8a31dd1d3f9f2`。

**当前重点是实际送显链路：HWC 缓冲区导入、DPU 取像素与 DSC 编码、DSI 传输、面板解码。正常截图尚不足以确定故障落在哪一层。下一轮先做同图原生实屏对照，并采集 Android 花屏时的活跃 framebuffer 与显示平面状态，保持 PPS 和时钟配置不变。**

## 为什么截图正常而屏幕花屏

BootAnimation 的图像缓冲区进入两条不同路径。截图由 SurfaceFlinger 通过当前 ANGLE / SwiftShader 的 CPU 渲染路径重新合成；物理屏幕则由 DRM HWC3 提交显示平面，DPU 读取图像并经过 DSC、DSI 送入面板。

正常截图说明图像能够被软件正确读取和合成，但没有验证硬件读取时采用的地址、行跨度、像素格式、同步状态，以及后续压缩传输是否正确。截图不是 DPU 扫描输出的读回。

## 已有实验说明了什么

| 实验 | 已有结果 | 判断边界 |
| --- | --- | --- |
| trial 55 | 面板发送的 PPS 改成与 ACK 编码器计算值一致，实屏仍花屏 | 单独修正这组 PPS 不足以解决问题 |
| trial 58 | 已知六色图截图约 99.70% 像素完全匹配，其余差异位于边缘附近且每通道不超过 5/255；记录中的实屏照片描述为完整色带与密集噪声交替 | 已确认软件截图与物理输出不一致 |
| trial 59 | 每包两片 DSC 的修改已由寄存器确认，操作者报告实屏无变化 | 分包数量修改已生效，但没有修复故障 |
| trial 60 | 原生测试的 XRGB8888 线性缓冲区 pitch 为 4352 字节，与 SSPP stride 一致，UBWC 关闭；两个 DSC bank 的已解码公共 PPS 字段匹配参考值 | 结果只适用于 Android 启动前的原生测试；不是花屏时 Android 的活跃状态 |

来源：[显示实验记录](https://github.com/xxbo/RMX2072-AOSP-Project/blob/0e905be5ab76b250b93bab3507d8a31dd1d3f9f2/docs/M3_PHYSICAL_DISPLAY.md#trial-55-pps-correction-accepted-physical-corruption-remains)、[trial 58](https://github.com/xxbo/RMX2072-AOSP-Project/blob/0e905be5ab76b250b93bab3507d8a31dd1d3f9f2/build/device/m3-display-58-2026-11-15.json)、[trial 59](https://github.com/xxbo/RMX2072-AOSP-Project/blob/0e905be5ab76b250b93bab3507d8a31dd1d3f9f2/build/device/m3-display-59-2026-11-15.json)、[trial 60](https://github.com/xxbo/RMX2072-AOSP-Project/blob/0e905be5ab76b250b93bab3507d8a31dd1d3f9f2/build/device/m3-display-60-2026-11-15.json)。

## 当前定位中的三个盲区

**测量时刻不同。** trial 60 在原生测试完成四次翻页后读取寄存器，随后关闭 CRTC 并释放缓冲区。Android 接管时会重新建立显示状态。原生的 pitch、format 和 DSC 配置不能直接代替 Android 的实际状态。[原生测试代码](https://github.com/xxbo/RMX2072-AOSP-Project/blob/0e905be5ab76b250b93bab3507d8a31dd1d3f9f2/scripts/device_audit/drm_panel_smoke.c#L203)

**原生彩条对行错误不敏感。** `drm_panel_smoke.c` 的颜色只取决于横坐标，每一行都是相同的竖向色条。重复行或行错序可能仍然看起来像彩条。因此，“短暂看见彩条”不能证明原生画面完整正确。[像素填充代码](https://github.com/xxbo/RMX2072-AOSP-Project/blob/0e905be5ab76b250b93bab3507d8a31dd1d3f9f2/scripts/device_audit/drm_panel_smoke.c#L130)

**PPS 发送成功不等于面板内部配置已核验。** 面板驱动在主机 transfer 返回足够长度后打印 `PPS accepted`；代码没有读取面板内部 PPS。trial 60 验证了编码器侧的寄存器，DSC 到面板解码器这一段仍需保留为候选。[面板驱动](https://github.com/xxbo/RMX2072-AOSP-Project/blob/0e905be5ab76b250b93bab3507d8a31dd1d3f9f2/device/realme/bladerunner_48m/display/panel-samsung-rm19795.c#L40)

## 实验一 建立同图原生显示基线

目标：判断花屏是否在绕过 Android HWC 的原生 KMS 路径中仍然出现。

1. 使用同一份 1080×2400 固定图案作为原生 KMS 和 BootAnimation 的输入，包含上下不同的标记、细横线和可识别的逐行或分组行标识。两条路径使用一致的图案内容与方向。

2. 原生缓冲区按驱动实际返回的 pitch 逐行填充；RGBA 转为 XRGB 等格式时显式处理通道顺序和 alpha，不能直接照搬原始字节。记录图案摘要、buffer 尺寸及分配长度，检查写入范围。

3. 在 Android 启动前保持静态画面，留出足够拍照时间，同时保存原生 framebuffer、plane、DPU 和 DSI 状态。当前探针有 15 秒总超时，延长停留时间时须同步调整有上限的超时与收尾逻辑。

4. 完成后关闭测试 CRTC、释放缓冲区和 DRM master，再让 Android 接管；两者不要同时控制显示。用相同方向拍摄 Android 阶段的实屏，并保存对应截图。

先保持 kernel 30、DTBO、图形库、GSI、PPS 和时钟配置不变。原生探针和测试图案的改动单独记录，避免把多种配置变化混入同一轮。

| 对照结果 | 优先排查范围 |
| --- | --- |
| 原生同图也花屏 | 共用的 DPU 取像素、DSC 编码与合并、DSI 传输、面板初始化和解码 |
| 原生完整正确，Android 花屏 | Android buffer 导入与布局、同步和缓存可见性，以及 Android 接管后的重新配置差异 |
| 原生结果不清楚或照片不能比较 | 改善图案和采样，不把“出现彩条”记为物理显示通过 |

即使两条路径表现不同，也需要比较实际显示平面和配置，不能只凭对照结果断定具体某个组件有错。

## 实验二 采集 Android 真正送显的缓冲区

目标：在已知图案出现且实屏花屏的时刻，把 HWC 输入、DRM atomic state 和 DPU 寄存器对应到同一块缓冲区。

在 HWC 导入 framebuffer 和提交 plane 的位置增加有数量上限的诊断记录，覆盖 BootAnimation 首次有效提交及稳定花屏时刻。沿用受控诊断机制；当前普通 GSI shell 没有挂载 debugfs，不能假定普通 ADB 能直接取得寄存器快照。

| 采集对象 | 需要记录的内容 |
| --- | --- |
| 身份与时刻 | boot ID、uptime、layer 或 buffer 标识、提交序号 |
| 实际 framebuffer | FB_ID、宽高、DRM fourcc、modifier、各 plane 的 pitch 与 offset、可核验的分配长度 |
| 活跃显示平面 | plane ID、CRTC ID、绑定的 FB_ID、source crop、目标矩形、rotation、alpha 与 blend 配置 |
| DPU 取像素 | 活跃 SSPP 的地址、stride、format、unpack、fetch mode、UBWC 状态；地址按驱动映射关系核对 |
| 同步与缓存 | acquire fence 的等待或传递、提交与完成时序、CPU 写入结束到设备读取之间的缓存同步路径 |
| 输出链路 | 同一提交稳定后对应的 DSC、DSI 配置，与原生参考快照逐项比较 |

只把 atomic state 中实际活跃的平面与寄存器关联；未使用寄存器 bank 的非零值可能是残留状态。尽量关联同一提交，无法做到时必须记录采样时间差。

当前 BootAnimation 使用 DEVICE composition，必须追踪它对应的实际 framebuffer。SurfaceFlinger 中另一个 FramebufferSurface 的分配信息不能代替这块直接送显缓冲区。

pitch 是每行的实际字节跨度，可能包含对齐填充。例如 1080 像素、每像素 4 字节的有效数据为 4320 字节，原生分配的实际 pitch 为 4352 字节；这本身正常。应核对“分配器元数据 → HWC 导入 → DRM framebuffer → SSPP stride”是否一致，不能直接把所有路径硬改成 4320 或 4352。

## 修复选择与验证标准

若发现实际 framebuffer 的 pitch、offset、format 或 modifier 与硬件编程不一致，先修复该处并重复同图对照；若布局一致，再分别核对 fence、CPU 缓存同步和缓冲区生命周期，检查 buffer 是否过早复用。任意增加等待或调用 msync 都不能直接当作已验证的修复。若原生同图也花屏，或 Android 对应输入与取像素状态均相符，则继续检查共用 DSC／DSI／面板链路。

PPS 修正和两片每包已经做过，应保留已有结果，避免重新将它们写成确定根因。后续只有在新证据指向具体参数时，才单独改变该参数并记录结果。缺少 Health HAL 的 SystemServer 问题独立跟踪，当前显示隔离实验保持范围集中。

- [ ] 原生 KMS 与 Android 使用同一诊断图案，边框、上下标记、行标识和色块均可比较。

- [ ] 实屏没有重复行、错位、噪声带或缺失区域；以实屏对照为准，截图正常只作为辅助证据。

- [ ] 硬件快照与活跃 framebuffer、plane、采样时刻对应，明确区分原生阶段和 Android 阶段。

- [ ] 每轮记录唯一改动、相关镜像或代码摘要、实屏照片、截图、显示状态及结论。

- [ ] 区分“命令成功”“事件完成”“截图正确”和“物理显示正确”；通过前三项不自动判定最后一项通过。

**当前状态：故障范围已收敛，具体根因和修复仍待上述实机对照确认。**

## 第 61 轮对照结果（2026 年 11 月 16 日）

已执行实验一：原生 KMS 和 Android 使用同一份带分组行号、细横线的 RGB 图案，原生保持 30 秒后关闭 CRTC、释放缓冲区，再交给 Android。kernel 30、DTBO、有效设备树、图形库、GSI、PPS、时钟和测试卷种子保持不变。

用户确认并提供照片：**原生阶段已经花屏**。Android 接管后仍花屏，用户进一步明确“花屏的内容有所变化”。因此两阶段均不通过，不能记成完全相同的输出，也不能再用短暂出现彩条证明原生正确。

实验二取得部分证据：独立只读 DRM 探针在同一次启动的 115.138 和 120.140 秒读到活跃 plane 41 / CRTC 89 / FB 95，实际格式 ABGR8888、linear、1080×2400、pitch 4352、offset 0；两次重读绑定一致。原生则是 XRGB8888、pitch 4352，分配 10,444,800 字节，SSPP stride 与 pitch 一致。Android 的运行时 DPU 寄存器、分配长度、提交 fence 和缓冲区生命周期尚未覆盖；查询得到 IN_FENCE_FD=-1 不能证明提交时没有 fence。

这一结果支持优先排查共用的 DPU 取像素、DSC/pingpong/merge、DSI 和面板通路。原生照片中三组可辨认行号相隔 144 个源图像行，恰为三个 48 行 slice；这只是待验证线索，不是已确定的故障周期或根因。下一步先把活跃通路、分包和行边界与官方 20607 配置对应，再选择单项改动。暂不推进 Health HAL，也不改写 pitch 或重复已失败的 PPS 假设。

手机留在可用的 GSI ADB 中；实屏和桌面仍未通过。详见[第 61 轮记录](../build/device/m3-display-61-2026-11-16.json)和[阶段结果](M3_PHYSICAL_DISPLAY.md#trial-61-result-corruption-reproduced-before-android)。


## 第 62 轮：单 DSC 仍复现花屏

已按官方列出的另一种拓扑做对照：单 LM、单 DSC 编码两片、单 DSI。寄存器确认单 DSC 生效，16 项隔离检查通过，PPS、分包、报告的 DSI 速率和测试输入保持不变。用户确认原生阶段“还是一样”，Android 阶段“一样，与上次无变化”。因此花屏无需双 DSC 合并也能复现，尚不能定位到某个具体共用组件。

手机继续留在 enforcing 的 GSI ADB，SurfaceFlinger 运行。下一步应把 DPU 显存取像素与后续压缩输出分开验证；不要重测冷启动或把这轮写成修复通过。[实验代码与完整结果](M3_DSC_TOPOLOGY_ISOLATION.md#trial-62-result)。

## 第 63 轮：绕过显存读取仍有条状噪声与缺失

已执行硬件红、绿、蓝各 8 秒的对照。SSPP 寄存器确认 solid-fill 生效，源地址和 stride 均为零，常量颜色及全屏尺寸正确；单 DSC 路由、DSC 参数和 DSI 分包寄存器保持一致。用户反馈：“我能看到颜色的变化，但是还是有一条一条的噪声和缺失”。因此本轮能够在不读取 framebuffer 的情况下复现花屏，不能继续把显存 pitch 或 Android 合成当作唯一故障解释。

随后普通显存红色的寄存器和映射检查通过，但用户“没注意”，这段实屏记为未观察，不能判断与硬件红色的差异。恢复图案后，探针及父进程均确认填色参数清零，普通取像素路径恢复，Android 17 的 enforcing、SurfaceFlinger 和 ADB 回来。桌面仍未进入，本轮最终 Android 实屏也未重新确认。

用户要求今天到此结束，未再发起新测试。下一次继续定位填色之后的 DPU、DSC 编码与分包、DSI 和面板解码通路；尚未证明某个具体组件有错。保持“6.18 + GSI + 移植驱动 → 实屏正确出图 → AOSP 桌面”的目标，不重复冷启动或看门狗故障注入。[完整证据](M3_DPU_SOLID_FILL_ISOLATION.md#trial-63-result)。

## 第 64 轮：面板状态可读，完整 PPS 一致，实屏仍花屏（11 月 18 日）

原生阶段用户反馈“和之前完全没区别，还是一样的”，Android 阶段“仍然一样花屏”。两阶段仍不通过。面板电源状态读取返回官方预期的 `0x9c`；完整 88 字节发送 PPS 与原生 DSC0 寄存器字段一致。尝试读取 PPS 写地址 `0x9e` 得到 16 个零，不能解释为内部 PPS，更不能据此判断配置为空或写入失败。

另已在电脑上合并 F.20 实际选中的 DTB 12 和 DTBO 17，与官方 Q 源码比较：开屏、亮屏、关屏及 PHY 数组逐字节一致，16 项时序和 DSC 标量也一致。没有发现这些数组中的固件版本差异。运行时 CCF 记录显示核心 200 MHz、DSI 位时钟约 421.632 MHz；原厂设备树指定 660 MHz，但这里还没有原厂运行时寄存器或物理频率测量，不能仅凭这一差异认定根因。

下一步对照原厂实际 DSI／PHY 传输设置及行、包边界，再选有依据的单项测试。保持 PPS、布局和当前图形输入固定。手机已在同一次启动中通过 196.985 秒检查，留在 enforcing GSI，ADB 和 SurfaceFlinger 正常；桌面仍未进入。本轮主机会话中断和本地候选分块单比特差异均在写入前处理并单独记录，未将异常字节写入手机，也不作为显示故障的解释。[第 64 轮完整证据](M3_PANEL_READBACK_2026-11-18.md#trial-64-result-physical-corruption-persists)。
