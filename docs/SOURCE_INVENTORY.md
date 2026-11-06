# Kernel Source Inventory — Phase 01

> Snapshot date: **2026-11-06 UTC**  
> Scope: public source repositories relevant to realme X50 Pro Player Edition (RMX2072 / bladerunner_48m) and Snapdragon 865 (SM8250/Kona).  
> Immutable pins: [sources/SOURCE_LOCK.json](../sources/SOURCE_LOCK.json) · [Human-readable manifest](../sources/SOURCE_MANIFEST.md)

## 1. Executive findings

1. The official RMX2072 player-edition kernel source is Linux **4.19.81**.
2. Realme's later shared Android S source is Linux **4.19.157**. It is useful as a later downstream reference, but its build.config.common still declares BRANCH=android-4.19-stable and KMI_GENERATION=0.
3. The newest community SM8250 kernel inspected in this pass is **4.19.325** on SM8250-Common/android_kernel_realme_sm8250:lineage-24.0. It is still a 4.19 downstream kernel, not a modern GKI kernel.
4. Project Elixir's Kraken-2.0 branch is **4.19.297**; it is a useful historical reference, but it is not the newest inspected tree.
5. The official Android 17 GKI reference is pinned separately at android17-6.18-2026-09_r13, commit ecdaacc9a0ee87eaf9544e1836d86bd9d590312e.
6. The RMX2072 device tree explicitly depends on device/realme/sm8250-common and vendor/realme/bladerunner_48m; the exact compatible common-tree/vendor pair still needs to be reconstructed.
7. There are two provenance hazards: an RMX2072 F.15 versus F.17 vendor mismatch, and a current SM8250 common tree whose proprietary blob list is sourced from the different RMX3371 model.

## 2. Kernel source lineage

| Source | Kernel | Commit date | Assessment |
|---|---:|---|---|
| Realme official Android Q | 4.19.81 | 2020-06-30 | Exact player-edition baseline |
| Realme official Android S | 4.19.157 | 2023-03-17 | Later shared downstream reference |
| Project Elixir SM8250 | 4.19.297 | 2023-12-19 | Historical community reference |
| AOSPA SM8250 | 4.19.318 | Not recorded in this snapshot | Alternate downstream reference |
| SM8250-Common current kernel | 4.19.325 | 2026-11-01 | Newest inspected community kernel snapshot |
| Official Android Common Kernel | 6.18 | 2026-11-04 commit | Android 17 GKI target reference |

### Critical GKI clarification

The Android S 4.19.157 tree contains files named build.config.gki and build.config.gki.aarch64, including KMI symbol-list settings. However, its build.config.common declares:

    BRANCH=android-4.19-stable
    KMI_GENERATION=0

The current SM8250-Common 4.19.325 tree declares the same branch family and KMI_GENERATION=0. These files show that GKI-related build tooling was present in the legacy tree; they do **not** turn Linux 4.19 into the Android 17 GKI architecture. Our modern GKI reference is the separate official ACK 6.18 tag.

## 3. Device-tree and vendor dependency graph

The inspected RMX2072 device trees use this dependency pattern:

- device/realme/bladerunner_48m
  - device/realme/sm8250-common
  - vendor/realme/bladerunner_48m

Evidence:
- RMX2072-specific BoardConfig.mk includes device/realme/sm8250-common/BoardConfigCommon.mk.
- RMX2072-specific device.mk inherits device/realme/sm8250-common/common.mk.
- The sreelekshman device tree also inherits vendor/realme/bladerunner_48m/bladerunner_48m-vendor.mk.

This dependency graph is clear at the makefile level, but the compatible branch pair is not yet proven. The 2023 device tree should not automatically be combined with a 2026 common tree without checking product variables, VINTF, HAL versions, partition definitions and build history.

## 4. Proprietary asset inventory

### RMX2072-specific list

The sreelekshman RMX2072 device tree's proprietary-files.txt contains **104 file mappings** across these categories:

- ACDB and audio calibration
- Audio firmware and libraries
- Camera configuration, sensor libraries and tuning data
- Charger / VOOC firmware
- Display calibration
- Goodix fingerprint firmware
- Keymaster
- NFC
- Sensors
- Touchscreen firmware
- Vibrator firmware
- Widevine firmware
- Wi-Fi firmware/configuration

The list header identifies RMX2072_11.F.15 as the source firmware.

### Shared SM8250 list

The current SM8250-Common/android_device_realme_sm8250-common:lineage-24.0 common tree contains **1,366 proprietary file mappings**. Its list header explicitly identifies **Realme GT Neo 3T (RMX3371_14.0.0.2100(EX01))** as the source for the listed blobs.

This is a shared platform tree with a blob inventory from a different handset. Do not import its proprietary files as an RMX2072 vendor package. It may still be valuable for shared configuration and newer interface examples, subject to compatibility review.

## 5. Firmware-version mismatch

Two source references disagree:

| Artifact | Firmware provenance |
|---|---|
| RMX2072 device-tree proprietary-files.txt | RMX2072_11.F.15 |
| RMX2072 vendor-tree update commit | RMX2072_11.F.17 |

This may be a stale extraction list, a vendor update without a matching list update, or another packaging difference. We have not established which. Keep both pins, do not combine blindly, and resolve the mismatch using the actual source archive and file hashes when available.

## 6. Repository scale and checkout strategy

GitHub repository size metadata (approximate KB, not exact download size):

| Repository | Approximate size |
|---|---:|
| Official Android Q kernel | 190,438 KB |
| Official Android S kernel | 189,294 KB |
| Project Elixir kernel | 2,030,567 KB |
| AOSPA kernel | 1,417,684 KB |
| SM8250-Common kernel | 1,944,989 KB |

Recommended handling:
- Do not mirror full kernel repositories into this project.
- Start with one kernel tree at a time.
- For history and metadata inspection, use shallow single-branch clones pinned to the exact SHA.
- For targeted diff analysis, use partial clone and sparse checkout where practical.
- For full kernel builds, budget for the complete working tree, toolchain and output directory.
- Keep build outputs and downloaded proprietary materials outside the Git repository.

## 7. License and redistribution status

See [SOURCE_LICENSE_AUDIT.md](./SOURCE_LICENSE_AUDIT.md). In short:
- Kernel repositories contain Linux kernel COPYING and per-file SPDX declarations; check every imported file.
- Some device-tree files carry Apache-2.0 headers, but repository-level license metadata is absent.
- Vendor repositories contain proprietary binaries; they remain external references only.

## 8. Phase 01 completion status

| Task | Status |
|---|---|
| Resolve and record immutable refs for official Q/S kernels | Complete |
| Record community kernel candidates and versions | Complete |
| Record RMX2072-specific device-tree candidates | Complete |
| Record shared SM8250 common device-tree reference | Complete |
| Record RMX2072 vendor reference and provenance | Complete |
| Pin official Android 17 GKI 6.18 reference | Complete |
| Complete file-level license review | In progress |
| Resolve F.15/F.17 mismatch | Open |
| Verify exact device-tree/common-tree/vendor branch pairing | Open |
| Clone and run source-tree diffs | Next task |
| Reproduce a kernel build | Not started |

**Next technical task:** compare the pinned kernel trees by subsystem and configuration, starting with arch/arm64/configs, Qualcomm drivers, techpack, memory allocation and build configuration. Do not begin 6.18 driver porting until the baseline diff and dependency inventory are available.
