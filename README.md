# RMX2072 AOSP Project

Independent Android platform research and porting project for the **realme X50 Pro Player Edition (RMX2072 / bladerunner_48m)**, powered by the Qualcomm Snapdragon 865 (SM8250/Kona).

The long-term goal is to bring a current AOSP-based Android release to the device and investigate a maintainable modern kernel path, including Android Generic Kernel Image (GKI).

**RMX2072 has mounted the official Android 17 QPR1 ARM64 + GMS image under Linux 6.18.32.** USB supplied the image's requested blocks to a read-only dm-user target. The kernel mounted ext4 through the GSI's signed dm-verity root. A second boot ran the GSI's own toybox in a chroot and resolved the dependencies of its init executable with explicit bootstrap library paths. Starting Android as PID 1 and reaching the framework remain open. See the [GSI experiment and replay instructions](docs/ANDROID17_USB_MOUNT.md).

> **Linux 6.18 reads all six UFS LUNs on RMX2072 at two-lane HS-G3 Rate B.** Two warm diagnostic boots completed 76 MiB of direct reads each with the AXI and UniPro core clocks at 300 MHz. The second boot also verified the complete diagnostic boot image and stock DTBO through their GPT partitions. Display and Android 17 boot remain open. See the [G3 evidence](build/device/ufs-g3-2026-11-10.json).

Linux 6.18 also parsed both F.20 `super` metadata slots and created read-only dm-linear mappings for `system`, `vendor` and `product`. All three full-device SHA-256 hashes matched the running F.20 logical devices. See the [dynamic partition test](docs/SUPER_READONLY.md).

The diagnostic now reads the F.20 filesystems through dm-verity. Two physical boots mounted `system` and `vendor` as EROFS and `product` as ext4. Each read 1,028,739,072 verified bytes. A deliberately wrong root hash returned EIO on a separate read-only target. See the [AVB and mount evidence](docs/AVB_VERITY_MOUNTS.md).

Execution path: **GitHub Actions kernel/driver builds + official Android 17 ARM64 GSI + local USB hardware validation**. See [build execution](docs/BUILD_EXECUTION.md), the [captured device baseline](docs/DEVICE_BASELINE_2026-11-06.md), and the manually triggered [Legacy Kernel Build](.github/workflows/legacy-kernel-build.yml).

Existing experiment results are consolidated into main: [full Kleaf 6.18 build](docs/GKI_618_BUILD.md), [source snapshot](docs/GKI_618_SOURCE_MIRROR.md), and [NQ-NCI compile/KMI limitations](experiments/nfc_nq/PORTING_LOG.md). The locked generic GKI + strict NFC [run #9](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42226214281) passed; the downloaded NFC module also passed matching-kernel CRC checks. Module loading and device hardware tests remain unperformed.

Current execution evidence: [locked GKI + strict NFC run](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42226214281), [corrected legacy build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866), and [downloaded ARM64 + GMS image preflight](docs/GSI_PREFLIGHT_2026-11-06.md). The GSI is hash-verified; partition capacity and FCM/VNDK gaps are still open.

**Verified recovery baseline:** stock-kernel logging-reader Android has repeatedly been restored with full boot/DTBO readback hashes and stock boot completion, including after the USB-backed Android 17 mount. The USB diagnostic has recorded CPUs `0-7` online, a configured high-speed USB UDC and a working RAM-only shell. See [independent kernel bring-up](docs/INDEPENDENT_KERNEL_BRINGUP.md) for historical comparisons and current qualifications.

## Goals

Current board/kernel work beyond logging is detailed in the [November 7 adaptation review](docs/ADAPTATION_REVIEW_2026-11-07.md), including actual configuration gaps and the Android desktop critical path.

The active phase is [independent 6.18 kernel bring-up](docs/INDEPENDENT_KERNEL_BRINGUP.md): hardware mutex/watchdog dependencies, a verified early log path and stable RAM-only USB diagnostics. GSI integration is deferred.

Latest follow-up: a physical SID-only comparison keeps kernel, ramdisk, command line, original DTBO and 24 other base trees byte-identical. SID `0x740` stops after communication start; SID `0`, mask `0`, yields a configured USB device and a completed 130,524-byte diagnostic transcript. SCM, apps SMMU, GCC, RPMh clocks/regulators and HS PHY are active on this RAM-only profile. See the [comparison evidence](build/device/usb-staged-sid-comparison-2026-11-09.json) and [bring-up journal](docs/INDEPENDENT_KERNEL_BRINGUP.md).

The [paced stability record](build/device/usb-soak-2026-11-09.json) contains all 29 validated responses and the separate failed burst probes. A subsequent RMX2072 trial registered the APSS watchdog on 6.18, traced a successful start, four keepalives and a stop, and recovered F.20 after a final same-boot USB sample at 524.64 s. See the [physical trial](docs/INDEPENDENT_KERNEL_BRINGUP.md#apss-watchdog-on-the-paced-sid0-profile) and [UFS reset, PHY and supply dependencies](docs/POST_USB_PLATFORM_DEPENDENCIES_2026-11-09.md).

The 6.18 debug kernel now returns to Qualcomm 9008 from either the ramdisk timer or a live ACM command on this handset. A staged TLMM test bound the driver and queried GPIO 180 with all other lines reserved. Electrical device reset remains untested. See the [EDL and UFS bring-up record](docs/RMX2072_EDL_AND_UFS.md).

The native QMP PHY passed two internal HS-B/G3 calibration cycles. The original G1 host profile provides a fallback with both core clocks fixed at 37.5 MHz. The G3 profile uses the F.20 clock range of 37.5 to 300 MHz and retains the same 19.2 MHz reference. See the [PHY test](docs/UFS_PHY_BRINGUP.md) and [UniPro bring-up record](docs/UFS_HOST_BRINGUP.md).

- Build and boot an AOSP-based Android 17 system on RMX2072.
- First establish a known-good baseline using the existing device tree, vendor components and a compatible kernel.
- Inventory the official Realme kernel sources, community device trees, proprietary vendor components and firmware dependencies.
- Investigate migration from the legacy Qualcomm 4.19 kernel lineage toward a modern Android Common Kernel / GKI branch.
- Preserve a reproducible build, test and recovery process.

## Target device

| Item | Value |
| --- | --- |
| Device | realme X50 Pro Player Edition |
| Model | RMX2072 |
| Device codename | bladerunner_48m |
| SoC | Qualcomm Snapdragon 865 |
| Platform | SM8250 / Kona |
| Architecture | ARM64 |
| Android target | Android 17 (AOSP) |
| Kernel research target | GKI / ACK 6.18 |
| Known legacy kernel lineage | Linux 4.19.x |

The F.20 handset has a boot-v2 image, 4 KiB pages, a single boot partition and an unlocked bootloader. Firmware and partition details are recorded in the [captured baseline](docs/DEVICE_BASELINE_2026-11-06.md).

## Repository layout

```text
.
├── README.md
├── docs/
│   ├── PROJECT_OVERVIEW.md
│   ├── HARDWARE_INVENTORY.md
│   ├── KERNEL_PORTING.md
│   ├── DRIVER_MIGRATION_MATRIX.md
│   ├── DRIVER_DEPENDENCY_MAP.md
│   ├── GKI_MIGRATION.md
│   ├── GSI_BUILD_GUIDE.md
│   └── COMPATIBILITY_MATRIX.md
├── device/                 # Project-owned device configuration and patches
├── kernel/                 # Project-owned kernel work; upstream sources stay external
├── vendor/                 # Metadata and extraction notes; do not commit proprietary blobs
├── build/                  # Build configuration and manifests
├── tools/                  # Reproducible helper scripts
└── .github/workflows/      # CI and validation workflows
```

## Source references

These are upstream references, not copies of their contents:

- [Realme X50 Pro 5G Play Android Q kernel source](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source)
- [Realme shared Android S kernel source for GT Neo2 / X50 Pro / GT Master Explorer](https://github.com/realme-kernel-opensource/realme_GTneo2-X50pro-GTMasterExploratory-AndroidS-kernel-source)
- [RMX2072 device tree (bladerunner_48m)](https://github.com/IGaganpreetSingh/android_device_realme_bladerunner_48m)
- [Project Elixir SM8250 community kernel](https://github.com/ProjectElixir-Devices/android_kernel_realme_sm8250)
- [Android Common Kernel documentation](https://source.android.com/docs/core/architecture/kernel)
- [Generic Kernel Image overview](https://source.android.com/docs/core/architecture/kernel/generic-kernel-image)

## Source inventory and pinned revisions

- [Automated kernel research pipeline](docs/KERNEL_RESEARCH_PIPELINE.md)
- [Kernel tree diff findings](docs/KERNEL_TREE_DIFF_FINDINGS.md)
- [KGSL / Adreno 650 research](docs/KGSL_ADRENO_RESEARCH.md)
- [Driver migration matrix](docs/DRIVER_MIGRATION_MATRIX.md)
- [Driver dependency map](docs/DRIVER_DEPENDENCY_MAP.md)

- [Source manifest](sources/SOURCE_MANIFEST.md)
- [Machine-readable source lock](sources/SOURCE_LOCK.json)
- [Kernel source inventory](docs/SOURCE_INVENTORY.md)
- [Source license audit](docs/SOURCE_LICENSE_AUDIT.md)
- [Development plan](plan.md)

## Engineering principles

1. **Bootable milestones first.** Keep a recoverable stock baseline and validate each change independently.
2. **Separate system, kernel and vendor work.** AOSP/GSI, GKI and proprietary vendor compatibility are related but distinct tracks.
3. **Prefer upstream implementations.** Reuse upstream Linux and Android Common Kernel code where suitable; port downstream code only where necessary.
4. **Do not assume GKI compatibility.** A legacy kernel with module support is not automatically GKI. KMI, module ABI, boot flow and vendor interfaces must be validated.
5. **Keep proprietary material out of Git.** Do not commit vendor blobs, firmware, factory images, keys, personal data or other files without clear redistribution rights. Record extraction instructions and hashes instead.
6. **Document test evidence.** Mark every feature as untested, build-tested, boot-tested or hardware-tested.

## Current status

- [x] GitHub repository created.
- [x] First-pass driver migration matrix and dependency map documented from pinned source evidence.
- [x] Confirm exact device model and F.20 firmware build from the handset; stock boot after unlock verified.
- [x] Capture partition map, boot image metadata and AVB status.
- [x] Archive and hash local boot/recovery/firmware and calibration backups (userdata excluded; complete restore still untested).
- [ ] Complete source and proprietary-component inventory.
- [ ] Reproduce an existing community ROM/device-tree build.
- [ ] Boot an Android 17 GSI on a compatible baseline.
- [x] Build a generic Android 17 GKI 6.18 distribution; RMX2072 board bring-up remains open.
- [ ] Validate hardware features and recovery/OTA strategy.

## Safety

Kernel and partition experiments can permanently damage device availability or erase data. Keep a verified stock firmware package, working recovery/EDL path and backups before any bootloader, partition or flashing operation. Never flash an image solely because it compiles.

## License

No project-wide license is declared yet. Each upstream source retains its own license. Before publishing code, identify the applicable licenses and add an appropriate license and attribution notices.
