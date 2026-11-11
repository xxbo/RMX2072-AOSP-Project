# RMX2072 AOSP Project

Independent Android platform research and porting project for the **realme X50 Pro Player Edition (RMX2072 / bladerunner_48m)**, powered by the Qualcomm Snapdragon 865 (SM8250/Kona).

**Target:** boot an Android 17 ARM64 GSI from internal UFS on a project-built ACK 6.18 kernel, with source-built board device trees, device-specific vendor software and ported drivers. F.20 provides reference measurements and recovery images. The [development plan](plan.md) tracks remaining firmware dependencies separately.

**Next milestone:** cold-boot without a host serving the image, then connect ADB and verify Android init as PID 1, API 37 and a UFS-backed system with the project vendor. The [bring-up stack](https://github.com/xxbo/RMX2072-AOSP-Project/pull/9) already records UFS HS-G3 and execution of the GSI's toybox in a USB-backed chroot. [Handset evidence](https://github.com/xxbo/RMX2072-AOSP-Project/blob/f2f6385af354d1c157b319030d5d458134a66acf/build/device/gsi17-usb-mount-2026-11-10.json)

### Diagnostic checkpoints

The November 9 mainline snapshot below predates the stacked UFS and GSI trials linked above.

> **Project status: Physical 6.18 USB diagnostic shell and ten-minute paced transfer test passed on RMX2072.** Correcting the primary USB IOMMU SID to 0 enables host enumeration and end-to-end ACM commands. One boot completed 606.17 seconds of verified responses and 7.25 MiB of checked payloads. Uncapped bursts still have short transfers; display, UFS and Android 17 boot remain unvalidated.

Execution path: **GitHub Actions kernel/driver builds + official Android 17 ARM64 GSI + local USB hardware validation**. See [build execution](docs/BUILD_EXECUTION.md), the [captured device baseline](docs/DEVICE_BASELINE_2026-11-06.md), and the manually triggered [Legacy Kernel Build](.github/workflows/legacy-kernel-build.yml).

Existing experiment results are consolidated into main: [full Kleaf 6.18 build](docs/GKI_618_BUILD.md), [source snapshot](docs/GKI_618_SOURCE_MIRROR.md), and [NQ-NCI compile/KMI limitations](experiments/nfc_nq/PORTING_LOG.md). The locked generic GKI + strict NFC [run #9](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42226214281) passed; the downloaded NFC module also passed matching-kernel CRC checks. Module loading and device hardware tests remain unperformed.

Current execution evidence: [locked GKI + strict NFC run](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42226214281), [corrected legacy build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866), and [downloaded ARM64 + GMS image preflight](docs/GSI_PREFLIGHT_2026-11-06.md). The GSI is hash-verified; partition capacity and FCM/VNDK gaps are still open.

**Verified recovery baseline:** stock-kernel logging-reader Android has repeatedly been restored with full boot/DTBO readback hashes and stock boot completion, including after the ten-minute USB test. The latest 6.18 profile records CPUs `0-7` online, a configured high-speed USB UDC and a working RAM-only diagnostic shell. Original DTBO remains unchanged. See [independent kernel bring-up](docs/INDEPENDENT_KERNEL_BRINGUP.md) for historical comparisons and current qualifications. GSI remains deferred while platform dependencies are adapted.

### November 9 board notes

Current board/kernel work beyond logging is detailed in the [November 7 adaptation review](docs/ADAPTATION_REVIEW_2026-11-07.md), including actual configuration gaps and the Android desktop critical path.

The [November 9 kernel journal](docs/INDEPENDENT_KERNEL_BRINGUP.md) records the diagnostic baseline used by the later Android and storage trials.

Latest follow-up: a physical SID-only comparison keeps kernel, ramdisk, command line, original DTBO and 24 other base trees byte-identical. SID `0x740` stops after communication start; SID `0`, mask `0`, yields a configured USB device and a completed 130,524-byte diagnostic transcript. SCM, apps SMMU, GCC, RPMh clocks/regulators and HS PHY are active on this RAM-only profile. See the [comparison evidence](build/device/usb-staged-sid-comparison-2026-11-09.json) and [bring-up journal](docs/INDEPENDENT_KERNEL_BRINGUP.md).

The [paced stability record](build/device/usb-soak-2026-11-09.json) contains all 29 validated responses, the final kernel-state summary and the separate failed burst probes. Next work is [watchdog, UFS/PHY and TLMM dependencies](docs/POST_USB_PLATFORM_DEPENDENCIES_2026-11-09.md), alongside the unresolved burst-transfer limit. This is a diagnostic baseline, not Android or production power-management qualification.

## Goals

1. Boot the Android 17 GSI and project-built vendor from UFS with usable ADB.
2. Replace the factory DTB/DTBO with source-built board trees and repeat the cold-boot, USB, UFS and recovery checks.
3. Bring up the display, graphics stack and touch until the Android launcher responds to physical input.
4. Qualify daily-use hardware, encrypted storage, power management and updates. Publish the remaining boot-chain and firmware dependencies with the test results.

## Target device

| Item | Value |
| --- | --- |
| Device | realme X50 Pro Player Edition |
| Model | RMX2072 |
| Device codename | bladerunner_48m |
| SoC | Qualcomm Snapdragon 865 |
| Platform | SM8250 / Kona |
| Architecture | ARM64 |
| Android target | Android 17 ARM64 GSI |
| Kernel target | Project-built Android Common Kernel 6.18 |
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
2. **Separate system, kernel and vendor work.** Pin the GSI, kernel, device trees and project vendor separately so regressions can be isolated.
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
- [x] Build the Android 17 ACK 6.18 kernel and demonstrate diagnostic userspace and USB on the handset.
- [x] Record two-lane UFS HS-G3 reads, verified F.20 mounts and Android 17 toybox execution in the [bring-up stack](https://github.com/xxbo/RMX2072-AOSP-Project/pull/9).
- [ ] Boot Android 17 from UFS with a source-built vendor and working ADB.
- [ ] Repeat that boot on source-built board device trees and bring up the interactive desktop.
- [ ] Qualify daily-use hardware and the update/recovery path. See [milestone acceptance](plan.md#milestones-and-acceptance).

## Safety

Kernel and partition experiments can permanently damage device availability or erase data. Keep a verified stock firmware package, working recovery/EDL path and backups before any bootloader, partition or flashing operation. Never flash an image solely because it compiles.

## License

No project-wide license is declared yet. Each upstream source retains its own license. Before publishing code, identify the applicable licenses and add an appropriate license and attribution notices.
