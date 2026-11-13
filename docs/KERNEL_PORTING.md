# Kernel Porting Strategy

## Starting point

Use the official RMX2072 Android Q 4.19.81 source as the device-specific legacy baseline. Compare it with the later shared Realme Android S 4.19.157 tree and the SM8250-Common 4.19.325 community tree.

The 4.19.325 tree is the newest inspected community reference, not a proven RMX2072 build. Its current shared device-tree proprietary-file list is sourced from RMX3371. Its KONA/Oplus configuration is useful for understanding downstream implementation and build wiring, but must not be copied as the final RMX2072 configuration.

Build the board kernel against the pinned Android 17 ACK 6.18 source. Use the warm-tested G3 board profile for driver regressions while M2 develops the source-built DTB/DTBO. [Current acceptance](../plan.md#milestones-and-acceptance)

## Staged approach

1. Reproduce the current 6.18 diagnostic on the same board profile before comparing driver changes. Retain the 4.19 builds for source and recovery comparisons.
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
| 3 — GPU | DRM/MSM A650, firmware/GMU, DMA-BUF and source-built graphics userspace | GPU submission and graphics userspace pass |
| 4 — Qualcomm IPC and connectivity | SMEM/GLINK/QRTR/QMI/remoteproc/IPA, modem, WLAN and Bluetooth | Calls/data/Wi-Fi/BT and subsystem recovery |
| 5 — Power, thermal and audio | Charger/VOOC, fuel gauge, TSENS/BCL/LMH, Q6/ASoC | Safe charging, thermal control and audio route tests |
| 6 — Camera and remaining peripherals | Spectra, sensors, fingerprint, NFC, haptics and secure services | Per-component hardware tests with retained logs |

Do not begin the full camera or audio migration before the memory, IOMMU and Qualcomm IPC foundations are understood.

## Rules

- Prefer upstream drivers where they cover the exact hardware and required Android interfaces.
- Do not equate an upstream directory or Kconfig symbol with device support.
- Do not copy a complete 4.19 downstream subsystem into GKI without tracing its dependencies and API/KMI surface.
- Treat vendor kernel modules, proprietary userspace libraries, firmware and HALs as separate compatibility surfaces.
- Prototype upstream DRM/MSM with a source-built allocator and composer for M3. Use the legacy KGSL UAPI to interpret F.20 captures.
- Treat ION-to-DMA-BUF as a cross-subsystem ABI migration affecting GPU, camera, audio and video.
- Treat camera Spectra, Q6 audio, modem/IPA, secure memory and OPlus charging as integrated stacks, not single C files.
- Do not import RMX3371 proprietary blobs or assume the shared SM8250 config is the RMX2072 final config.
- Compiling a driver does not prove runtime correctness.
- Track source SHA, file-level license, Kconfig, DTS bindings, firmware, exported symbols, KMI, module signing and module load order.
- Keep stock boot/vendor images and a tested recovery route available.

## Current status

- Source inventory and immutable source pins: recorded.
- KGSL/Adreno 650 first-pass content research: completed; no GKI module build or device test.
- First-pass driver migration matrix and dependency map: recorded; non-GPU subsystem content diffs remain open.
- The connected handset runs F.20; captured stock vendor and boot metadata are the current baseline. Historical F.15/F.17 trees remain references.
- Physical handset/boot/partition/AVB capture: completed; bootloader unlocked and stock Android boot verified. Actual DTB 12 / DTBO 17 selection and NFC provider fixups recorded.
- Legacy community build: the Goodix and qcacld build fixes passed in [run #4](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866). Physical boot of that rebuilt image is pending.
- Generic ACK/GKI 6.18 distribution: full build passed in run 42194678844. Main now freezes all manifest dependencies and runs a strict NFC DDK build. Strict NFC module loading remains untested. The separate SM8250 platform kernel reached Android 17 second-stage init under enforcing with RAM/USB-backed system and RAM-backed vendor. Port and test the board drivers on this 6.18 baseline. UFS cold boot and per-driver hardware qualification remain open. [Handset result](https://github.com/xxbo/RMX2072-AOSP-Project/blob/19d77ebfd3b5c5eed24c49c4494043a9203a12b7/build/device/gsi17-enforcing-second-stage-2026-11-12.json) · [Driver status](COMPATIBILITY_MATRIX.md).

## Measured generic-kernel platform gap

The completed run #8 configuration is not a Kona board configuration: it disables PINCTRL_MSM, COMMON_CLK_QCOM, QCOM_RPMH, QCOM_SMEM, SCSI_UFS_QCOM, ARM_SMMU, PHY_QCOM_QMP and DRM_MSM. Enabling USB_DWC3_QCOM and ARCH_QCOM alone does not supply those dependencies. The exact selected values and config hash are in `build/device/gki-platform-gaps.json`.

The pinned ACK source does provide `sm8250.dtsi` and HDK/MTP board examples, but its qcom DTS directory has no RMX2072/Realme board file. Those reference bindings need comparison with the selected stock DTB 12 / DTBO 17. The stock embedded DTB bundle is not automatically compatible with upstream 6.18 bindings.

The SM8250 platform kernel passed paced SID0 USB and warm, read-only G3 UFS tests. The APSS watchdog was exercised on a separate diagnostic boot. Uncapped USB transfers, cold storage initialization, production power handling and later module loading still need validation. Run only modules built for the selected 6.18 configuration. [Driver and handset evidence](COMPATIBILITY_MATRIX.md) · [Watchdog trial](https://github.com/xxbo/RMX2072-AOSP-Project/pull/2)
