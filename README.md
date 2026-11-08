# RMX2072 AOSP Project

Independent Android platform research and porting project for the **realme X50 Pro Player Edition (RMX2072 / bladerunner_48m)**, powered by the Qualcomm Snapdragon 865 (SM8250/Kona).

The long-term goal is to bring a current AOSP-based Android release to the device and investigate a maintainable modern kernel path, including Android Generic Kernel Image (GKI).

> **Project status: Physical 6.18 diagnostic userspace reached on RMX2072.** A controlled handoff using the stock DTB bundle and original DTBO reached the RAM-only supervisor and executed its EDL return at kernel uptime 90.74 seconds. USB, sustained stability and Android 17 boot remain unvalidated.

Execution path: **GitHub Actions kernel/driver builds + official Android 17 ARM64 GSI + local USB hardware validation**. See [build execution](docs/BUILD_EXECUTION.md), the [captured device baseline](docs/DEVICE_BASELINE_2026-11-06.md), and the manually triggered [Legacy Kernel Build](.github/workflows/legacy-kernel-build.yml).

Existing experiment results are consolidated into main: [full Kleaf 6.18 build](docs/GKI_618_BUILD.md), [source snapshot](docs/GKI_618_SOURCE_MIRROR.md), and [NQ-NCI compile/KMI limitations](experiments/nfc_nq/PORTING_LOG.md). The locked generic GKI + strict NFC [run #9](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42226214281) passed; the downloaded NFC module also passed matching-kernel CRC checks. Module loading and device hardware tests remain unperformed.

Current execution evidence: [locked GKI + strict NFC run](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42226214281), [corrected legacy build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866), and [downloaded ARM64 + GMS image preflight](docs/GSI_PREFLIGHT_2026-11-06.md). The GSI is hash-verified; partition capacity and FCM/VNDK gaps are still open.

**Current handset state:** restored to stock-kernel logging-reader Android after the successful 6.18 handoff probe; full boot/DTBO readback hashes and stock boot completion passed. The 6.18 log records eight CPUs activated, diagnostic init, no USB UDC, and an explicit EDL restart. This probe retains downstream board descriptions and does not validate the project's upstream USB DTS, which still loops. See [independent kernel bring-up](docs/INDEPENDENT_KERNEL_BRINGUP.md) and the [runtime record](build/device/handoff-runtime-2026-11-08.json). GSI work remains deferred until independent kernel stability and hardware dependencies are resolved.

## Goals

Current board/kernel work beyond logging is detailed in the [November 7 adaptation review](docs/ADAPTATION_REVIEW_2026-11-07.md), including actual configuration gaps and the Android desktop critical path.

The active phase is [independent 6.18 kernel bring-up](docs/INDEPENDENT_KERNEL_BRINGUP.md): hardware mutex/watchdog dependencies, a verified early log path and stable RAM-only USB diagnostics. GSI integration is deferred.

Latest follow-up: [runtime snapshots](build/device/runtime-snapshots-2026-11-08.json) confirm CPUs `0-7` online and hardware-lock/RPMh driver binding with the legacy DT. USB wrapper/HS PHY remain unbound. [Disabling CPU idle](build/device/cpuidle-isolation-result-2026-11-08.json) did not resolve the upstream-DTS restart loop. The handset has been restored and stock Android boot completion verified again.

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

The exact partition layout, boot image header version, AVB state, firmware revision and hardware component variants must be verified on the physical device before flashing.

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
