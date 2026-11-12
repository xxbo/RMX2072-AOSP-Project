# Kernel Research Pipeline

## Purpose

The Kernel Source Research workflow provides a repeatable, read-only first pass over the immutable source revisions in sources/SOURCE_LOCK.json. It replaces repeated manual repository browsing with a consistent source inventory and structural path comparison.

The research outputs are used to maintain the driver migration matrix and dependency map. They are not build or hardware-validation evidence.

## Workflow

- Workflow file: .github/workflows/kernel-source-research.yml
- Source inventory scanner: scripts/kernel_research/audit_sources.py
- KGSL content scanner: scripts/kernel_research/kgsl_content_diff.py
- Trigger: manual workflow_dispatch, relevant source-lock/scanner/workflow pushes, and a weekly Monday schedule
- Runner: GitHub-hosted ubuntu-latest
- Runtime: Python 3.12; standard library only
- Permissions: contents:read
- Outputs: source inventory and KGSL Markdown/JSON reports uploaded as 30-day workflow artifacts

The workflow does not push commits, open pull requests, modify upstream repositories, download vendor binaries, build a kernel, or flash a device.

## Research steps

The workflow currently runs two independent jobs: a broad source inventory and a targeted KGSL/Adreno 650 analysis. Both jobs are read-only and run on GitHub-hosted runners.

1. Read the pinned source lock.
2. Verify each GitHub kernel commit through the GitHub API.
3. Resolve the official Android Common Kernel 6.18 reference through Gitiles.
4. Enumerate selected kernel source trees: arch, drivers, techpack, include, kernel, mm, fs, net, block, sound, scripts, security, crypto, init, ipc and virt.
5. Extract Linux version fields from the top-level Makefile where available.
6. Extract build variables from build.config files and OplusKernelEnvConfig.mk.
7. Inventory ARM64 defconfigs, Qualcomm-related config names, driver subsystem directories and techpack modules.
8. Compare file paths in selected subsystems against the official RMX2072 Android Q 4.19.81 baseline.
9. Emit JSON for further analysis and Markdown for human review.
10. Retrieve selected KGSL/UAPI/GKI files at immutable commits; compare 4.19.81, 4.19.325 and a separately pinned Qualcomm Linux 7.2 KGSL reference.
11. Inventory KGSL ioctl names and UAPI structs; run preliminary host LP64 sizeof/offsetof probes.
12. Inspect the pinned Android 17 GKI 6.18 tree for DRM/MSM, A6xx/Adreno 650 catalog support, KGSL absence, Kconfig and shmem vendor-hook evidence.

## Run manually

1. Open the repository's Actions tab.
2. Select Kernel Source Research.
3. Choose Run workflow on the main branch.
4. Wait for the Inventory and structural diff and KGSL jobs to complete.
5. Download the kernel-source-research and kgsl-adreno research artifacts from the completed run.

The weekly schedule runs at 03:17 UTC on Mondays. Scheduled workflows may start later depending on GitHub-hosted runner availability.

## Output interpretation

- Expected kernel version comes from the source lock; the Makefile version is independently parsed where possible.
- Commit verification confirms that the pinned commit resolves to the exact requested SHA.
- File-path additions/removals are structural indicators only. They do not prove that code behavior changed, that a driver is compatible, or that a removed path has no replacement.
- The Android Common Kernel 6.18 source is queried through Gitiles directory listings and is not yet part of the full recursive file-path comparison.
- GitHub's recursive tree API may truncate very large trees; the scanner falls back to smaller subtrees where possible.
- A failed source lookup is reported and causes a non-green job so that incomplete results are not mistaken for a successful audit.
- The current source scanner parses the Kona base defconfig and Oplus config fragment. It does **not yet fully model** the Makefile-injected techpack configuration fragments under techpack/display/config, techpack/camera/config and techpack/audio/config. These are an explicit follow-up because the 4.19.325 KONA Makefiles include konadisp.conf, konacamera.conf and konaauto.conf during subsystem builds.
- A source-level Kconfig/Makefile match is not the final merged .config. The actual build system and generated config remain authoritative.

## Current findings and planning documents

- [Kernel tree structural findings](./KERNEL_TREE_DIFF_FINDINGS.md)
- [KGSL / Adreno 650 content research](./KGSL_ADRENO_RESEARCH.md)
- [Driver migration matrix](./DRIVER_MIGRATION_MATRIX.md)
- [Driver dependency map](./DRIVER_DEPENDENCY_MAP.md)
- [Hardware and source inventory](./HARDWARE_INVENTORY.md)

The first-pass driver matrix separates RMX2072-specific source evidence from shared SM8250 references. The [compatibility matrix](COMPATIBILITY_MATRIX.md) records subsequent 6.18 handset tests, including warm UFS and Android first-stage init.

## Next automation stages

### Stage A — Source structure and configuration

Current scope: commit verification, directory inventory, defconfig/config-fragment parsing, selected module Makefile content diffs and path-level comparison. Findings are recorded in docs/KERNEL_TREE_DIFF_FINDINGS.md.

Next improvement: parse the Makefile-injected KONA techpack fragments and record their exact effects separately from the base defconfig/Oplus fragment. Do not merge their exported variables into a claimed final .config unless the real build system does so.

### Stage B — Content-aware subsystem diffs

**KGSL/Adreno first pass completed.** The current workflow retrieves selected immutable source files, compares the official RMX2072 4.19.81 and SM8250-Common 4.19.325 KGSL implementations, compares them with a separately pinned Qualcomm Linux 7.2 KGSL reference, inventories UAPI ioctl/struct changes, runs preliminary host LP64 layout probes, and inspects GKI 6.18 DRM/MSM and Adreno 650 evidence. Findings: docs/KGSL_ADRENO_RESEARCH.md.

The first-pass source review has now also produced:
- docs/DRIVER_MIGRATION_MATRIX.md — per-subsystem migration disposition and risk.
- docs/DRIVER_DEPENDENCY_MAP.md — dependency graph and implementation order.
- An expanded docs/HARDWARE_INVENTORY.md — RMX2072-specific manifest clues and explicit unknowns.

Remaining automated content research, in order:
1. Display: KONA SDE/DSI/DP and OPlus panel extensions versus ACK DRM/MSM/DPU/DSI.
2. Memory: ION clients/UAPI, DMA-BUF heaps, secure buffers, SMMU and KMI dependencies.
3. Camera: Spectra CPAS/CSIPHY/CSID/ISP/SMMU/sensor pipeline and upstream media interfaces.
4. Audio: Q6 DSP, APR/GLINK, ASoC, codec and soundwire dependencies.
5. Connectivity: CNSS/ICNSS, WLAN module boundary, GLINK/QRTR/QMI, IPA/RMNET and Bluetooth transport.
6. Power/thermal: OPlus charger/VOOC/gauge, TSENS, BCL, LMH/DCVS and power_supply interfaces.
7. Touch/fingerprint/NFC/sensors/haptics: exact Kconfig selection, DTS binding, firmware loading and userspace node contracts.
8. Validate UAPI and module interfaces with the pinned AArch64 Android LLVM toolchain; audit undefined symbols against the exact 6.18 GKI KMI lists.

For each subsystem, report source presence, active build wiring, device-tree binding, firmware dependency, userspace ABI, GKI candidate and unresolved blockers. Avoid treating file counts or directory names as compatibility proof.

### Stage C — Reproducible build experiments

The generic ACK, board kernel and legacy comparison builds have separate workflows. Use the pinned toolchains and source SHAs, keep logs and artifact hashes, and record any factory input used in a comparison. [Build execution](BUILD_EXECUTION.md)

### Stage D — GKI compatibility analysis

Compare the 4.19 downstream driver interfaces with the Android Common Kernel 6.18 interfaces, classify each hardware subsystem as upstream-supported, port-required, rewrite-required or vendor-dependent, and record evidence for every conclusion.

## Security and resource policy

- Use the workflow's read-only GITHUB_TOKEN permission.
- The scanner reads external source at pinned revisions. The build uses a dedicated [ACK snapshot branch](GKI_618_SOURCE_MIRROR.md).
- Do not store extracted vendor binaries, factory images, modem firmware, DRM assets, keys, personal device dumps or credentials in workflow artifacts.
- Keep artifact retention finite.
- Do not run full kernel builds on every push. Build workflows will be explicit and separately gated.
