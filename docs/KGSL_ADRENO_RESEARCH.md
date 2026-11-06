# KGSL / Adreno 650 — Automated Source Research

> Research snapshot: 2026-11-06 UTC  
> GitHub Actions: [Kernel Source Research #17](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42176677695)  
> Target: Realme X50 Pro Player Edition (RMX2072), Snapdragon 865 / SM8250, Adreno 650  
> Scope: immutable source retrieval, static comparison, UAPI inventory and host LP64 layout probes  
> Status: first-pass source research complete; no kernel build, module load, device boot or hardware test has been performed.

## 1. Executive summary

The pinned Android Common Kernel 6.18 tree contains the upstream Qualcomm DRM/MSM graphics driver and an Adreno 6xx implementation whose catalog includes Adreno 650 (chip ID `0x06050002`, revision 650). The same tree does not contain the legacy `drivers/gpu/msm` KGSL driver or the KGSL UAPI header.

This gives us two distinct migration directions:

1. **Port modern KGSL to Android GKI 6.18.** Use Qualcomm's separately maintained KGSL module as a modern code reference, then resolve its Android GKI KMI, vendor-hook, Kconfig, DMA/IOMMU, firmware and module integration requirements.
2. **Use upstream DRM/MSM.** The kernel-side Adreno 650 implementation exists, but this is not a drop-in replacement for a legacy Android userspace stack that expects `/dev/kgsl-3d0` and KGSL ioctls. The RMX2072 vendor userspace/HAL compatibility must be established before considering this route viable.

The current evidence makes the first direction the more direct experiment for preserving the existing Qualcomm Android userspace contract. This is a research priority, not yet a proven bootable solution.

## 2. Immutable source revisions

| Source | Pinned commit | Kernel / role |
|---|---|---|
| Realme RMX2072 Android Q | `24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4` | Linux 4.19.81; device-origin baseline |
| SM8250-Common current kernel | `b76eb6c93add8152b1aa873da0d8d7f495cccab0` | Linux 4.19.325; newest inspected community baseline |
| Android 17 GKI | `ecdaacc9a0ee87eaf9544e1836d86bd9d590312e` | Linux 6.18; target kernel reference |
| Qualcomm Linux KGSL | `d70a6765a318eda3e400c711587ce373c693c99e` | Linux 7.2 external-module reference |

The Qualcomm KGSL source is independently pinned in `sources/SOURCE_LOCK.json`. Its upstream meta-qcom recipe identifies it as a GPL-2.0-only external module and uses a Linux 7.2 build integration. It is **not** evidence of Android GKI 6.18 KMI compatibility and must not be described as an Android 17 GKI-ready module.

## 3. Automation and coverage

Run #17 completed both jobs successfully:

- `Inventory and structural diff`
- `KGSL and Adreno 650 content research`

The KGSL scanner retrieves selected immutable raw files rather than cloning complete kernel repositories.

| Source | Files fetched | Optional files missing | Fetch errors |
|---|---:|---:|---:|
| RMX2072 official 4.19.81 | 18 / 20 | 2 | 0 |
| SM8250-Common 4.19.325 | 20 / 20 | 0 | 0 |
| Qualcomm Linux KGSL reference | 26 / 28 | 2 | 0 |

The GKI scan separately retrieved DRM/MSM, A6xx, Kconfig, defconfig, Android vendor-hook and shmem-related files. Some optional ABI-list paths were absent at the pinned GKI source revision; this means the current scan cannot yet certify the module's KMI symbol allowlist.

The workflow artifact contains both Markdown and JSON output:
- [KGSL research artifact — Run #17](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42176677695/artifacts/13483601635)
- [Full Actions run](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42176677695)

## 4. Official 4.19.81 versus community 4.19.325

The automated C-file comparison shows substantial incremental evolution in the existing KGSL implementation.

| File | Added lines | Removed lines | Detected function names added / removed |
|---|---:|---:|---:|
| `kgsl.c` | 614 | 261 | 7 / 2 |
| `kgsl_iommu.c` | 118 | 63 | 2 / 0 |
| `kgsl_sharedmem.c` | 317 | 108 | 14 / 2 |
| `kgsl_pwrctrl.c` | 173 | 99 | 2 / 0 |
| `adreno.c` | 215 | 55 | 3 / 0 |
| `adreno_a6xx.c` | 204 | 50 | 1 / 0 |
| `adreno_a6xx_gmu.c` | 86 | 36 | 1 / 0 |
| `adreno_a6xx_preempt.c` | 90 | 19 | 0 / 0 |

Two files are present in the community tree but absent from the official Q baseline:

- `drivers/gpu/msm/kgsl_reclaim.c`
- `drivers/gpu/msm/kgsl_timeline.c`

The largest text churn is in shared-memory management and the main KGSL device implementation. This is where a deeper semantic review should begin. Added/removed line counts and regex-detected function names are navigation aids, not semantic change scores.

## 5. KGSL userspace ABI

### 5.1 Official 4.19.81 → community 4.19.325

| Metric | Result |
|---|---:|
| Existing ioctl names | 55 → 62 |
| Added ioctl names | 7 |
| Removed ioctl names | 0 |
| Changed ioctl macro definitions | 0 |
| UAPI structs | 9 added, 0 removed |
| Common structs with detected text changes | 0 |

The seven added ioctl names are:

- `IOCTL_KGSL_GPU_AUX_COMMAND`
- `IOCTL_KGSL_TIMELINE_CREATE`
- `IOCTL_KGSL_TIMELINE_DESTROY`
- `IOCTL_KGSL_TIMELINE_FENCE_GET`
- `IOCTL_KGSL_TIMELINE_QUERY`
- `IOCTL_KGSL_TIMELINE_SIGNAL`
- `IOCTL_KGSL_TIMELINE_WAIT`

This is encouraging for the old-to-community transition: the scan did not detect removals or changed ioctl macro definitions. It does not establish semantic compatibility for every vendor userspace client.

### 5.2 Community 4.19.325 → Qualcomm Linux 7.2 KGSL reference

The modern Qualcomm reference has a larger UAPI surface:

- 4 additional ioctl names were detected.
- 11 additional UAPI structs were detected.
- 35 common struct definitions had text changes.
- No removed ioctl names were detected in this comparison.

The modern reference is a different codebase/build target. These differences identify areas to inspect; they are not a migration patch or proof of ABI compatibility.

### 5.3 Layout probe

The workflow compiled generated `sizeof` / `offsetof` probes against each UAPI header using the runner's host C compiler in 64-bit LP64 mode.

| Source | Probe | Structs measured | Field offsets measured |
|---|---|---:|---:|
| Official 4.19.81 | Passed | 83 | 308 |
| Community 4.19.325 | Passed | 92 | 346 |
| Qualcomm Linux 7.2 reference | Passed | 103 | 409 |

For 83 common structs between official Q and community 4.19.325, the probe found zero size changes and zero field-offset changes. For 92 common structs between community 4.19.325 and the modern Qualcomm reference, it also found zero size changes and zero field-offset changes.

**Important limitation:** this is a host x86_64 LP64 probe, not an AArch64 cross-compile. The parser does not fully model every C construct (for example nested unions, conditional compilation, bitfields or all pointer/array cases). It is a useful first-pass ABI signal only. We still need a pinned Android/AOSP AArch64 toolchain, compile-time assertions and eventually userspace ioctl tests.

## 6. Android 17 GKI 6.18 graphics architecture

The pinned GKI tree shows:

| Evidence | Result |
|---|---|
| `drivers/gpu/msm` legacy KGSL directory | Absent |
| `include/uapi/linux/msm_kgsl.h` | Absent |
| `drivers/gpu/drm/msm` upstream driver | Present |
| `include/uapi/drm/msm_drm.h` | Present |
| Adreno 650 chip ID `0x06050002` in A6xx catalog | Present |
| Adreno revision 650 catalog entry | Present |
| A650 GMU firmware name referenced | Present |
| A6xx GPU implementation | Present |
| A6xx GMU implementation | Present |

The GKI tree therefore has kernel-side support for the Adreno 6xx family and an explicit A650 catalog entry through DRM/MSM. It does not ship the old KGSL character-device/UAPI implementation in the inspected source revision.

This distinction is central:

- **GPU hardware support exists** in the modern upstream driver.
- **Legacy KGSL userspace ABI support does not exist** in this GKI tree.
- A kernel driver being present does not imply that the existing RMX2072 vendor graphics libraries can use it.

The current `gki_defconfig` scan did not find an explicit `CONFIG_DRM_MSM` assignment. We must inspect the complete device/vendor config fragments and the final merged kernel config before assuming the driver is enabled in a target build.

## 7. Modern KGSL integration risks against GKI

The Qualcomm Linux 7.2 KGSL reference uses an Android shmem vendor hook:

`android_rvh_shmem_get_folio`

The pinned GKI 6.18 tree contains the hook declaration and exports its tracepoint. The scanner did not find the hook in the inspected GKI/OPLUS ABI symbol-list paths. It also found an Android vendor-data field macro and a potential slot in `shmem_inode_info`, while the relevant config/default evidence is not sufficient to prove the field is enabled in a target GKI build.

These are **KMI/configuration gates to investigate**, not a final verdict that the module cannot be built:

1. Locate the exact KMI symbol list and symbol-list generation inputs for the intended Android 17 GKI build.
2. Confirm whether `android_rvh_shmem_get_folio` is an allowed vendor-module dependency for that build.
3. Verify the `ANDROID_VENDOR_DATA` / `ANDROID_VENDOR_OEM_DATA` configuration and struct layout in the target build.
4. Inspect all undefined symbols referenced by the KGSL module and compare them against exported GKI symbols and the applicable KMI list.
5. Resolve dependencies on Qualcomm QFPROM/NVMEM, MDT loader, IOMMU, DMA-BUF, memory reclaim, trace hooks and firmware loading.

The source-level presence of a hook or export alone is not sufficient to prove GKI module compatibility.

## 8. Initial migration assessment

| Route | Current evidence | Main unknowns |
|---|---|---|
| Port modern Qualcomm KGSL to GKI 6.18 | Modern KGSL source exists; A650 firmware names and code paths are present; GKI has relevant Qualcomm infrastructure | KMI allowlist, API drift, module build, vendor hooks, memory/IOMMU integration, exact firmware and userspace ABI |
| Use GKI DRM/MSM directly | Upstream 6.18 DRM/MSM and A650 catalog are present | Compatibility with RMX2072 vendor userspace, Android graphics HAL integration, buffer/sync ABI, display integration |
| Forward-port old Realme KGSL 4.19 | Exact device-origin source is available | Very large kernel API gap, old framework assumptions and long-term maintenance burden |

**Recommended research priority:** investigate the modern Qualcomm KGSL module against the exact Android 17 GKI KMI/build target first, while keeping DRM/MSM as the upstream architectural fallback/reference. Do not yet choose either route as the final implementation.

## 9. Next GitHub Actions research gates

1. **GKI KMI symbol audit:** discover the exact ABI/KMI lists for the pinned Android 17 GKI release and compare every undefined symbol from the modern KGSL module.
2. **AArch64 UAPI ABI validation:** repeat `sizeof` / `offsetof` probes with the pinned Android LLVM toolchain and add compile-time assertions for all common KGSL structs.
3. **Kconfig dependency closure:** recursively resolve all KGSL dependencies and selected symbols against the actual target GKI config fragments.
4. **Module build experiment:** create a separate, manually triggered workflow using the exact GKI build environment. Do not run full module builds on every push.
5. **Device/vendor pairing:** resolve RMX2072 device-tree and vendor firmware versions before any boot-image or module integration experiment.

## 10. Limitations

- The modern Qualcomm KGSL source is a Linux 7.2 external-module reference, not an Android GKI 6.18 drop-in driver.
- The GKI source inspection is pinned to the recorded commit; it is not a complete device-specific Android 17 kernel build.
- The LP64 probe is not an AArch64 cross-compile and is not a runtime userspace ABI test.
- Function detection uses regular expressions rather than a full C parser or compiler AST.
- Text diff counts do not measure semantic behavior changes.
- No proprietary firmware, vendor libraries, factory images or device dumps were downloaded.
- No kernel was compiled, module-loaded, booted or tested on RMX2072.
