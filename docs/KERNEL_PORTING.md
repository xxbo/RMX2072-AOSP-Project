# Kernel Porting Strategy

## Starting point

Use the official RMX2072 Android Q 4.19.81 source as the device-specific legacy baseline. Compare it with the later shared Realme Android S 4.19.157 tree and the SM8250-Common 4.19.325 community tree.

The 4.19.325 tree is the newest inspected community reference, not a proven RMX2072 build. Its current shared device-tree proprietary-file list is sourced from RMX3371. Its KONA/Oplus configuration is useful for understanding downstream implementation and build wiring, but must not be copied as the final RMX2072 configuration.

The modern target is the pinned Android 17 ACK/GKI 6.18 reference. It is a research baseline, not a device-ready kernel.

## Staged approach

1. Reproduce a known-compatible kernel/device build before changing architecture.
2. Capture exact RMX2072 firmware, DTB/DTBO, partition/boot metadata and recovery facts.
3. Compare official and community source trees by subsystem; trace Kconfig, Makefiles, DTS bindings, firmware and userspace contracts.
4. Map each driver to upstream Linux/ACK implementations and classify it as reuse, DTS/config adaptation, vendor-delta port, ABI bridge or userspace/firmware integration.
5. Resolve shared foundations (clock, regulator, pinctrl, interconnect, SMMU/IOMMU, DMA-BUF, firmware loading and Qualcomm IPC) before porting upper-level drivers.
6. Port one independently testable subsystem at a time.
7. Build against the exact 6.18 toolchain/config, audit KMI and module dependencies, then load and hardware-test on the target device.
8. Keep a known-good rollback image and record evidence for every milestone.

## Canonical driver planning documents

- [Driver migration matrix](./DRIVER_MIGRATION_MATRIX.md) — per-subsystem evidence, migration disposition, priority and acceptance criteria.
- [Driver dependency map](./DRIVER_DEPENDENCY_MAP.md) — shared foundations and the recommended dependency order.
- [Hardware and source inventory](./HARDWARE_INVENTORY.md) — RMX2072-specific firmware/configuration evidence and unresolved physical variants.
- [KGSL / Adreno 650 research](./KGSL_ADRENO_RESEARCH.md) — the first content-aware source comparison and GKI KMI investigation.
- [Kernel tree diff findings](./KERNEL_TREE_DIFF_FINDINGS.md) — structural source and config findings.
- [GKI migration research](./GKI_MIGRATION.md) — ACK/GKI architecture and KMI constraints.

## First-pass migration order

| Wave | Scope | Exit condition |
|---|---|---|
| 0 — Device facts | Exact firmware, component IDs, DTB/DTBO, partition/boot metadata and recovery baseline | No unresolved board/vendor pairing assumptions |
| 1 — Platform base | Kona DTS, clocks/resets, PMIC/regulators, pinctrl, interconnect, LLCC, SMMU, UFS, USB/ADB | Stable boot, storage, ADB and clean critical probe logs |
| 2 — Memory, display and touch | DMA-BUF/secure heaps, DRM/MSM, panel and GT9886 | Visible UI, brightness, touch and suspend/resume |
| 3 — GPU | KGSL-vs-DRM decision, A650 firmware/GMU, KMI and memory path | GPU submission and graphics userspace pass |
| 4 — Qualcomm IPC and connectivity | SMEM/GLINK/QRTR/QMI/remoteproc/IPA, modem, WLAN and Bluetooth | Calls/data/Wi-Fi/BT and subsystem recovery |
| 5 — Power, thermal and audio | Charger/VOOC, fuel gauge, TSENS/BCL/LMH, Q6/ASoC | Safe charging, thermal control and audio route tests |
| 6 — Camera and remaining peripherals | Spectra, sensors, fingerprint, NFC, haptics and secure services | Per-component hardware tests with retained logs |

Do not begin the full camera or audio migration before the memory, IOMMU and Qualcomm IPC foundations are understood.

## Rules

- Prefer upstream drivers where they cover the exact hardware and required Android interfaces.
- Do not equate an upstream directory or Kconfig symbol with device support.
- Do not copy a complete 4.19 downstream subsystem into GKI without tracing its dependencies and API/KMI surface.
- Treat vendor kernel modules, proprietary userspace libraries, firmware and HALs as separate compatibility surfaces.
- Keep the existing KGSL userspace ABI in view: upstream DRM/MSM with Adreno 650 support is not a drop-in replacement for a vendor stack expecting KGSL nodes/ioctls.
- Treat ION-to-DMA-BUF as a cross-subsystem ABI migration affecting GPU, camera, audio and video.
- Treat camera Spectra, Q6 audio, modem/IPA, secure memory and OPlus charging as integrated stacks, not single C files.
- Do not import RMX3371 proprietary blobs or assume the shared SM8250 config is the RMX2072 final config.
- Compiling a driver does not prove runtime correctness.
- Track source SHA, file-level license, Kconfig, DTS bindings, firmware, exported symbols, KMI, module signing and module load order.
- Keep stock boot/vendor images and a tested recovery route available.

## First experimental port

The first driver experiment is NQ-NCI for the RMX2072 SN100 NFC controller. The target's official 20607 DTS node, I2C address and GPIO assignments are now identified, and the newer SM8250-Common source contains SN100-aware driver logic. An external-module port is staged at \`experiments/nfc_nq/\` on branch [experiment/nq-nci-gki-6.18](https://github.com/xxbo/RMX2072-AOSP-Project/tree/experiment/nq-nci-gki-6.18).

The first pass deliberately limits changes to current I2C/class APIs and localizes the vendor NFC UAPI header. Legacy GPIO calls remain for the compile experiment so the exact GKI export/KMI blockers can be observed before deciding whether to convert the driver to descriptor-based GPIO. The first compile-smoke workflow has produced an AArch64 relocatable nq-nci.ko against the pinned 6.18 source. Because the workflow uses modules_prepare without a full kernel build, MODPOST warned that Module.symvers was missing; this is not KMI certification or hardware validation. The next gate is a full GKI symbol/export audit.

## Current status

- Source inventory and immutable source pins: recorded.
- KGSL/Adreno 650 first-pass content research: completed; no GKI module build or device test.
- First-pass driver migration matrix and dependency map: recorded; non-GPU subsystem content diffs remain open.
- Exact RMX2072 device/vendor F.15/F.17 pairing: unresolved.
- Physical handset/boot/partition/AVB capture: not recorded.
- Legacy kernel build reproduction: not completed.
- ACK/GKI 6.18 build, module load and hardware validation: not started.
