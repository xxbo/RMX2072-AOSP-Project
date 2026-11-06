# Kernel Tree Diff Findings — Phase 01

> Snapshot: 2026-11-06 UTC  
> Automated run: [GitHub Actions #4](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42163188475)  
> Artifact: [kernel-source-research-4](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42163188475/artifacts/13478280146)

## 1. Scope and confidence

This report summarizes immutable source revisions from sources/SOURCE_LOCK.json. GitHub Actions recursively enumerated selected source trees, parsed kernel Makefiles and config inputs, and compared selected module Makefiles.

The scan is read-only. It did not compile a kernel, generate a merged .config, boot a device, or test hardware.

Path additions/removals are structural signals. They do not prove that a driver is new, removed, compatible or functionally different. A path can move, be renamed, become conditional, or be supplied through another tree.

## 2. Kernel lineage confirmed

| Source | Kernel version | Scanned file paths | Role |
|---|---:|---:|---|
| Realme official Android Q | 4.19.81 | 55,680 | Device-origin baseline for RMX2072 Player Edition |
| Realme official Android S | 4.19.157 | 54,640 | Later official shared downstream reference |
| Project Elixir | 4.19.297 | 68,898 | Historical community reference |
| AOSPA | 4.19.318 | 69,070 | Alternate community reference |
| SM8250-Common | 4.19.325 | 67,460 | Newest inspected community reference |
| Android Common Kernel | 6.18.32 | Targeted Gitiles listing | Modern Android 17 GKI reference |

The file-path counts cover the selected top-level trees only, not every repository path. The GKI scan is directory-level and is not included in the recursive counts.

All six immutable kernel commits resolved successfully in Actions run #4. The Makefile parser independently recovered the expected 4.19 versions and the GKI tree's 6.18.32 version.

## 3. Highest-impact structural finding: Qualcomm Techpack

The official Q and S trees contain only a techpack/stub directory. The community kernel trees contain substantial standalone Qualcomm Techpack source trees.

| Techpack | Project Elixir 4.19.297 | SM8250-Common 4.19.325 |
|---|---:|---:|
| Display | 345 paths | 345 paths |
| Audio | 488 paths | 496 paths |
| Camera | 459 paths | 393 paths |
| Video | 52 paths | 52 paths |

The official Android Common Kernel 6.18 tree has no top-level techpack directory in the inspected revision.

This is a major source-layout and integration difference. It does not establish that every file is newly written: some code may have been relocated or carried from vendor downstream trees. We must trace the relevant implementation and its dependencies before deciding whether to port, replace or drop it.

## 4. Subsystem findings

### 4.1 KGSL / Adreno 650

- The selected drivers/gpu/msm path count grows from 85 in the official Q tree to 90 in the 4.19.325 tree.
- The 4.19.325 KGSL Makefile adds kgsl_reclaim.o and kgsl_timeline.o.
- Adreno CoreSight is no longer listed as an unconditional object in the same way; the current Makefile wires adreno_coresight.o through CONFIG_CORESIGHT_ADRENO.
- The core Kona/Adreno build wiring remains recognizable. This looks like an incremental downstream evolution rather than a wholesale GPU-driver replacement.

Next files to inspect: kgsl.c, kgsl_mmu.c, kgsl_pwrctrl.c, kgsl_sharedmem.c, adreno.c, adreno_a6xx.c, kgsl_reclaim.c and kgsl_timeline.c.

### 4.2 Qualcomm clock tree

The broad drivers/clk/qcom path count grows by 51 files between official Q and the 4.19.325 tree. However, a targeted comparison of the Makefile shows that the Kona-specific object wiring is unchanged:

- camcc-kona.o
- debugcc-kona.o
- dispcc-kona.o
- gcc-kona.o
- gpucc-kona.o
- npucc-kona.o
- videocc-kona.o

Most of the additional files and Makefile entries belong to other Qualcomm platform families such as Scuba, Lagoon and Khaje. They should not be treated as useful SM8250 changes without checking their SoC and Kconfig dependencies.

### 4.3 Qualcomm SoC integration

The drivers/soc/qcom path comparison reports 40 added and 3 removed paths in 4.19.325 versus the official Q tree.

The current Makefile also adds include paths into Techpack display code and has Oplus-specific watchdog integration. This confirms that the downstream tree is more tightly integrated with vendor display and platform code.

### 4.4 Display, camera and audio

The community trees have separate Techpack display, camera and audio build systems. The current display Makefile wires the MSM display stack, rotator and PLL components. The camera Makefile has Oplus-specific conditional integration.

These components are likely to be among the most difficult parts of a 6.18 migration because the upstream ACK tree does not preserve the vendor Techpack directory layout. We need to map their actual interfaces to DRM/KMS, V4L2/media, ALSA/ASoC, remoteproc and other upstream frameworks.

### 4.5 Thermal and power

The community thermal Makefiles add QPNP ADC thermal support and remove the old Horae shell thermal object. The 4.19.325 tree also contains additional Qualcomm thermal files such as ADC TM and BCL-related components.

We need to distinguish generic Qualcomm support from device-specific temperature, battery and charging policy.

### 4.6 IOMMU

The current Makefile adds virtio-iommu.o. This is not evidence of a new physical SM8250 IOMMU implementation. The Qualcomm SMMU path and its device-tree bindings need a separate content-level review.

### 4.7 Input and sensors

The drivers/input path has large path churn. The earlier official Q to Android S comparison shows VL53L1 files moved into a Kona-specific subdirectory. The current community tree has a substantially different file count from the original baseline.

Treat this as a relocation and integration investigation, not as hundreds of confirmed removed input features.

### 4.8 WLAN and USB

The WLAN tree has only a small path change: the WLAN firmware service files move from a cnss2 location to cnss_utils. USB has additional Qualcomm gadget/RMNET support in the community tree.

These changes need to be checked against the target modem, Wi-Fi firmware, IPA and vendor HAL interfaces.

## 5. Defconfig and build configuration findings

### 5.1 Kona performance defconfig size

| Source | Config options parsed |
|---|---:|
| Official Q 4.19.81 | 748 |
| Official S 4.19.157 | 865 |
| Project Elixir 4.19.297 | 744 |
| AOSPA 4.19.318 | 744 |
| SM8250-Common 4.19.325 | 740 |

These counts represent explicit enabled/disabled/value assignments parsed from the defconfig file, not the final kernel .config.

- Official Q to S: 167 added, 50 removed and 1 changed option.
- Official Q to Project Elixir: 75 added, 79 removed and 2 changed options.
- Official Q to SM8250-Common: 120 added, 128 removed and 5 changed options.
- Project Elixir and AOSPA have byte-identical Kona performance and Kona normal defconfigs in the pinned revisions.
- Their separate sm8250_defconfig files differ: AOSPA has 9 added, 21 removed and 2 changed options compared with Project Elixir.

### 5.2 Important config-composition discovery

The current SM8250 common device tree's BoardConfigCommon.mk declares:

- TARGET_KERNEL_SOURCE := kernel/realme/sm8250
- TARGET_KERNEL_CONFIG := vendor/kona-perf_defconfig vendor/oplus.config

The pinned 4.19.325 kernel tree contains both inputs. The vendor/oplus.config fragment has 89 parsed options and includes Oplus-specific device features such as fingerprint, charging and sensor integration.

Therefore, the correct build configuration is not just kona-perf_defconfig. The fragment must also be merged. The final generated .config is the authoritative result and remains to be verified by a reproducible build.

The fact that a CONFIG symbol is absent from one defconfig does not prove that it is disabled: Kconfig defaults and additional fragments may affect the merged result.

## 6. GKI 6.18 implications

The official Android Common Kernel tag resolves to a Makefile version of 6.18.32. Its directory inventory includes substantial upstream Qualcomm clock, SoC, thermal and IOMMU trees, but no top-level Techpack directory.

This suggests a split migration strategy:

1. Reuse upstream ACK implementations where the relevant hardware block and interface are already supported.
2. Port the minimum Qualcomm vendor extensions required by SM8250.
3. Replace vendor-only framework integrations where an upstream subsystem provides equivalent functionality.
4. Keep proprietary userspace HAL and firmware dependencies outside the kernel source migration itself.

A matching directory or Kconfig symbol is not enough to prove binary or hardware compatibility.

## 7. Source pairing and unresolved risks

The current SM8250 common device tree explicitly selects the kernel source path and the Kona/Oplus config pair above. Its branch is lineage-24.0, matching the pinned current SM8250-Common kernel branch name.

However, this does not prove that the old RMX2072-specific device tree and the current common tree form a working combination. No current RMX2072-specific device-tree repository was found under the SM8250-Common organization in the initial search. The device-tree/common-tree/vendor pairing still requires a compatibility audit.

The RMX2072 device-tree proprietary list identifies RMX2072_11.F.15, while the pinned RMX2072 vendor repository update says RMX2072_11.F.17. This mismatch remains unresolved.

## 8. Recommended next research order

1. **Build configuration and source pairing:** verify the exact device-tree/common-tree/kernel branch combination and produce the merged .config from the declared defconfig plus fragments.
2. **KGSL:** compare the actual 4.19.81 and 4.19.325 C sources for MMU, memory management, power, GMU/HFI, Adreno A6xx and the reclaim/timeline additions.
3. **Display:** map Techpack SDE/DSI/DP/rotator interfaces to ACK 6.18 DRM/KMS.
4. **Camera:** map CamX/ISP/CSIPHY/CSID/CAMSS-related code and vendor dependencies.
5. **Audio:** map QDSP6/ADSP, APR, ASoC codecs, routing and machine drivers.
6. **Memory and DMA:** investigate ION, DMA-BUF, heaps, CMA, SMMU and the memory-management extensions.
7. **Connectivity and power:** investigate CNSS/WLAN, IPA/RMNET, thermal, charging and battery policy.

The next automation stage should use sparse, commit-pinned checkouts for these selected paths and generate C/header content diffs. Full kernel builds should remain a separate gated workflow.
