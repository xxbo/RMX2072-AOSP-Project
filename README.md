# RMX2072 AOSP Project

Independent Android platform research and porting project for the **realme X50 Pro Player Edition (RMX2072 / bladerunner_48m)**, powered by the Qualcomm Snapdragon 865 (SM8250/Kona).

**Target:** boot an Android 17 ARM64 GSI from internal UFS on a project-built ACK 6.18 kernel, with source-built board device trees, device-specific vendor software and ported drivers. F.20 provides reference measurements and recovery images. The [development plan](plan.md) tracks remaining firmware dependencies separately.

## Current handset result

On two warm RMX2072 boots, Android first-stage init ran as PID 1 on 6.18.32, switched root to the USB-backed Android 17 GSI and mounted the source-built vendor at `/vendor` from RAM. PID 1 then executed the GSI's `/system/bin/init selinux_setup`. Trial 02 selected genfs `202604` and passed a separate policy compile with neverallow checking enabled. The observer stopped before the kernel policy write. [Handset records](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/gsi17-project-vendor-2026-11-11.json) · [Process and replay](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/docs/ANDROID17_USB_MOUNT.md#project-vendor-and-pid-1-policy-setup)

**M1 is in progress.** PID 1 reached second-stage init under enforcing using original GSI pages from read-only RAM and a USB fallback beneath dm-verity. Second stage failed to read `/system/build.prop` after the fallback reader exited. The next storage test must keep the verified GSI available throughout init. [Handset comparison](build/device/gsi17-enforcing-second-stage-2026-11-12.json) Acceptance requires an image-server-disconnected cold boot followed by same-boot ADB on Android 17. The current fixture uses a factory-derived board DTB, original DTBO and a temporary Google emulator first-stage init. [Milestones](plan.md#milestones-and-acceptance) · [Next M1 tests](plan.md#next-work-on-m1)

### Diagnostic and build records

- 6.18 passed 606 seconds of paced USB ACM traffic. Uncapped bursts showed short reads. A later test exercised the APSS watchdog and software return to EDL. [USB soak](build/device/usb-soak-2026-11-09.json) · [Watchdog and recovery](https://github.com/xxbo/RMX2072-AOSP-Project/pull/2) · [EDL and TLMM](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/docs/RMX2072_EDL_AND_UFS.md)
- Two warm tests read six UFS LUNs at two-lane HS-G3. Later diagnostics parsed both F.20 super metadata slots and verified stock partitions with dm-verity. These results establish the storage control for M1. [PHY](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/docs/UFS_PHY_BRINGUP.md) · [G3 reads](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/docs/UFS_HOST_BRINGUP.md) · [Logical partitions](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/docs/SUPER_READONLY.md) · [Verified mounts](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/docs/AVB_VERITY_MOUNTS.md)
- Full boot/DTBO readbacks and stock boot completion verify the F.20 recovery control. Full `super` restore and the target UFS layout remain open. [Captured baseline](docs/DEVICE_BASELINE_2026-11-06.md) · [Capacity measurements](docs/GSI_PREFLIGHT_2026-11-06.md)
- Generic 6.18 Kleaf builds and the NQ-NCI DDK/CRC checks passed. NFC hardware validation is open. [Build execution](docs/BUILD_EXECUTION.md) · [Kleaf](docs/GKI_618_BUILD.md) · [Locked sources](docs/GKI_618_SOURCE_MIRROR.md) · [NFC results](experiments/nfc_nq/PORTING_LOG.md)

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
├── vendor/                 # Provenance notes for factory comparisons
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
- [x] Exercise UFS HS-G3 reads and verified F.20 mounts, then observe Android first-stage init mount both the USB-backed GSI and the RAM-backed project vendor. [Handset trials](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/gsi17-project-vendor-2026-11-11.json)
- [ ] Boot Android 17 from UFS with a source-built vendor and working ADB.
- [ ] Repeat that boot on source-built board device trees and bring up the interactive desktop.
- [ ] Qualify daily-use hardware and the update/recovery path. See [milestone acceptance](plan.md#milestones-and-acceptance).

## Safety

Kernel and partition experiments can permanently damage device availability or erase data. Keep a verified stock firmware package, working recovery/EDL path and backups before any bootloader, partition or flashing operation. Never flash an image solely because it compiles.

## License

No project-wide license is declared yet. Each upstream source retains its own license. Before publishing code, identify the applicable licenses and add an appropriate license and attribution notices.
