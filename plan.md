# RMX2072 AOSP Project — Development Plan

> Target device: realme X50 Pro Player Edition (RMX2072 / `bladerunner_48m`), Qualcomm Snapdragon 865 (SM8250/Kona)  
> System target: AOSP-based Android 17  
> Kernel research target: Android Common Kernel (ACK) / GKI, with 6.18 as a candidate to evaluate  
> Plan status: **Initial plan — pending device audit**  
> Last updated: 2026-11-06

This document is the project execution plan and source of truth for milestone order, acceptance criteria, dependencies and current status. Update it as evidence is collected. A milestone is complete only when its acceptance criteria are met and the evidence is recorded in the repository.

## 1. Project objectives

### Primary objective

Bring up a current AOSP-based Android system on the RMX2072, initially reusing the most compatible available device configuration, vendor components and kernel.

### Long-term objective

Investigate and, if technically viable, migrate the device from its legacy Qualcomm 4.19 downstream kernel to a supported ACK/GKI architecture. Maintain the device-specific kernel modules, device configuration and build process so future Android releases can be evaluated without depending entirely on a ROM maintainer.

### Engineering principles

1. **Prove the simplest path first.** Validate the Android system layer separately from kernel modernization.
2. **Preserve a known-good recovery path.** No experimental partition writes before stock firmware, partition layout and recovery method are understood.
3. **Separate AOSP, device/vendor and kernel work.** GSI, device-specific ROM integration and GKI are related but distinct workstreams.
4. **Use evidence, not assumptions.** Source availability or a successful compile does not prove device compatibility.
5. **Prefer upstream code where suitable.** Reuse upstream Linux and ACK implementations where they support the exact hardware; port downstream code only when necessary.
6. **Keep proprietary material out of this repository.** Do not commit vendor blobs, firmware, factory images, private keys, IMEI, serial numbers or personal data without clear redistribution rights.
7. **Record reproducibility.** Keep source revisions, manifests, build commands, toolchain versions, configs, hashes and test logs for each milestone.

## 2. Workstreams and dependency order

The work is divided into four tracks. Track A is the first priority. Track B can proceed in parallel after source revisions are pinned. Track C should not become a device-flashing dependency until its prototype is independently validated. Track D records integration and maintenance.

| Track | Scope | Priority | Dependency |
| --- | --- | --- | --- |
| A — Device baseline and Android bring-up | Identify handset, preserve stock state, audit Treble/VINTF/partitions, test Android 17 GSI | Highest | Physical handset and stock firmware |
| B — Source and driver inventory | Compare official/community kernels, device trees, proprietary dependencies and upstream driver status | High; parallel with A | Pinned source revisions |
| C — Kernel modernization | Rebuild legacy kernel, assess ACK/GKI branch, port modules and validate KMI | Long-term research | Track B inventory and boot/recovery knowledge |
| D — Integration and maintenance | Reproducible builds, test matrix, packaging, OTA/recovery strategy and documentation | Continuous | Evidence from A–C |

### Critical sequencing rule

Do not combine the first Android 17 system experiment with a new 6.x kernel. First establish a known-good system/vendor/kernel baseline. Change one major layer at a time so failures can be isolated.

## 3. Milestones

### M0 — Device audit and safety baseline

**Goal:** Establish exactly which RMX2072 variant and firmware are available, and how to recover the handset.

Tasks:
- [ ] Confirm model, region/SKU, RAM/storage variant and full firmware build number.
- [ ] Record Android version, vendor build, baseband and security patch level.
- [ ] Record bootloader lock state, AVB state and whether official unlock is available.
- [ ] Capture read-only device properties and kernel release.
- [ ] Capture partition names, sizes, slot arrangement and dynamic-partition status.
- [ ] Identify boot image header version and the presence or absence of `boot`, `vendor_boot`, `init_boot`, `vendor_dlkm`, `dtbo` and `vbmeta` partitions.
- [ ] Obtain the exact stock firmware package and document a verified restore/EDL/service recovery path.
- [ ] Hash locally stored stock images and record hashes (not the images themselves) in the project notes.
- [ ] Confirm whether the bootloader can be unlocked without relying on an unverified method.

**Deliverables:**
- Device facts added to `docs/HARDWARE_INVENTORY.md`
- Partition and boot-chain notes
- Stock recovery checklist and verified file hashes stored locally

**Acceptance criteria:**
- Exact device identity and firmware build are known.
- A credible stock recovery route is documented.
- No sensitive identifiers or proprietary images are committed.

**Gate:** Do not flash any experimental image before M0 is complete.

### M1 — Source pinning and reproducible legacy baseline

**Goal:** Establish trustworthy source revisions and reproduce an existing kernel/device build before changing architecture.

**Progress note (2026-11-06):** Initial source pins are recorded in sources/SOURCE_LOCK.json and sources/SOURCE_MANIFEST.md. The inventory is source-reviewed only; no kernel has been built or boot-tested by this project. The 4.19.325 SM8250-Common tree is the newest inspected community baseline, while official Android 17 GKI 6.18 is pinned separately as the migration target.

**Automation note (2026-11-06):** GitHub Actions Run #17 completed both the source-inventory and KGSL/Adreno research jobs successfully. The broad scanner verifies six kernel commits, inventories selected source trees, parses the base defconfig and Oplus config fragment, and compares selected module Makefiles. The follow-up source review found additional Makefile-injected KONA display/camera/audio fragments that the scanner does not yet parse; this gap is recorded in docs/KERNEL_TREE_DIFF_FINDINGS.md and docs/KERNEL_RESEARCH_PIPELINE.md. No kernel has been compiled or boot-tested by this project.

Tasks:
- [x] Pin the official Android Q RMX2072 kernel source at an immutable commit.
- [x] Pin the shared Android S 4.19 kernel source and record its legacy 4.19 build configuration.
- [x] Pin the Project Elixir 4.19.297 and current SM8250-Common 4.19.325 community kernel references; record AOSPA 4.19.318 as an alternate.
- [x] Pin RMX2072-specific device-tree candidates and the current SM8250 common device-tree reference.
- [x] Pin an RMX2072-specific vendor blob reference and record its firmware provenance.
- [x] Pin the official Android 17 GKI 6.18 release tag for comparison.
- [x] Add a read-only GitHub Actions workflow for pinned-source verification, tree inventory and structural path comparison.
- [x] Complete green end-to-end Actions runs and review the generated reports.
- [x] Add defconfig/config-fragment parsing and selected kernel module Makefile content diffs.
- [x] Complete the first-pass driver migration matrix and subsystem dependency map from pinned source evidence.
- [ ] Add C/header content diffs for display, camera, audio, memory, connectivity, power/thermal and peripheral subsystems.
- [ ] Extend the config scanner to parse Makefile-injected KONA display, camera and audio fragments.
- [ ] Complete file-level license and redistribution review for every source we may reuse.
- [ ] Resolve the RMX2072 device-tree / vendor-blob firmware-version mismatch.
- [ ] Verify which common device-tree branch is actually paired with each device-specific tree.
- [ ] Set up a Linux build environment and record toolchain versions.
- [ ] Reproduce a kernel build from a selected source tree, or document the exact blocker.
- [ ] Where feasible, reproduce a known community ROM build without flashing it.

**Deliverables:**
- Pinned source manifest and immutable source lock in `sources/`
- Build environment notes
- Kernel build log and artifact hashes (artifacts remain outside Git unless licensing permits)

**Acceptance criteria:**
- Every source dependency is pinned to a commit.
- At least one baseline build is reproducible, or blockers are documented precisely.

### M2 — Treble, Vendor and GSI compatibility assessment

**Goal:** Determine whether a generic Android 17 system image can work with the handset's existing vendor and kernel stack.

Tasks:
- [ ] Check `ro.treble.enabled`, CPU ABI and VNDK/vendor API properties.
- [ ] Inspect VINTF manifests and compatibility matrices from the actual device.
- [ ] Check linker namespace isolation and relevant vendor interface constraints.
- [ ] Determine system-as-root, dynamic partition and A/B details.
- [ ] Check GSI architecture, binder ABI, image size and release requirements.
- [ ] Compare the Android 17 GSI requirements with the actual vendor implementation.
- [ ] Identify required overlays, properties, init changes and compatibility workarounds.
- [ ] Select a suitable prebuilt GSI for the first experiment; record its exact source, build ID and SHA-256.

**Deliverables:**
- Compatibility findings in `docs/COMPATIBILITY_MATRIX.md`
- GSI selection record and preflight checklist

**Acceptance criteria:**
- A specific GSI image and exact device flashing/recovery procedure are selected.
- Known incompatibilities and rollback steps are documented.

### M3 — First Android 17 GSI bring-up

**Goal:** Boot Android 17 while keeping the known-compatible kernel and vendor stack unchanged wherever possible.

Tasks:
- [ ] Verify the bootloader unlock and restore procedure.
- [ ] Make and verify required backups.
- [ ] Follow device-specific instructions for the actual partition layout and fastboot mode.
- [ ] Flash only the minimum required system-layer changes.
- [ ] Capture first-boot `logcat`, kernel logs and VINTF results.
- [ ] Determine whether failures are caused by system/vendor interface, init, SELinux, partition layout or image format.
- [ ] Restore stock firmware if the test fails and record the outcome.

**Deliverables:**
- GSI test record with image hash, commands, logs and result
- Updated compatibility matrix

**Acceptance criteria:**
- Android 17 reaches the launcher and ADB is usable, or a reproducible blocker is identified.
- The test does not rely on an unverified kernel replacement.

### M4 — Own AOSP build and device integration

**Goal:** Move from a downloaded GSI to a reproducible AOSP build process.

Tasks:
- [ ] Select and pin the exact AOSP Android 17 manifest/branch.
- [ ] Establish a reproducible build host and storage layout.
- [ ] Build the generic ARM64 system target.
- [ ] Compare the locally built system image with the tested prebuilt GSI.
- [ ] Add device-specific configuration only where generic GSI behavior is insufficient.
- [ ] Keep vendor extraction metadata and proprietary blobs outside public Git history.
- [ ] Document build commands, environment variables, output artifacts and hashes.

**Deliverables:**
- Build manifest and scripts under `build/` and `tools/`
- Reproducible AOSP build instructions
- First project-built Android system image

**Acceptance criteria:**
- A clean environment can reproduce the system image from pinned sources.
- Build provenance and artifact hashes are recorded.

### M5 — Kernel source and driver asset analysis

**Goal:** Understand what can be reused, upstreamed, rebuilt or must remain proprietary.

**Progress note (2026-11-06):** The first KGSL/Adreno 650 source-analysis pass is complete. GitHub Actions Run #17 retrieved pinned RMX2072 4.19.81, SM8250-Common 4.19.325, Qualcomm Linux 7.2 KGSL reference and Android 17 GKI 6.18 files. Findings are recorded in `docs/KGSL_ADRENO_RESEARCH.md`. The pinned GKI has DRM/MSM with an Adreno 650 catalog entry, but no legacy KGSL directory/UAPI. Qualcomm's modern KGSL is a Linux 7.2 external-module reference, not a proven GKI 6.18 module. No kernel build or device test has been performed.

**Driver inventory note (2026-11-06):** A first-pass subsystem matrix and dependency graph are now recorded in `docs/DRIVER_MIGRATION_MATRIX.md` and `docs/DRIVER_DEPENDENCY_MAP.md`. The expanded `docs/HARDWARE_INVENTORY.md` distinguishes RMX2072-specific manifest evidence from shared SM8250 source examples. The review identified target clues for AMS678UW01 display calibration, GT9886 touch firmware, Adreno 650 firmware, camera sensor-module candidates, SN100 NFC configuration, Goodix fingerprint firmware, VOOC charging firmware and AW8697 haptic firmware. The official 20607 DTS now confirms the NQ-NCI node at I2C 0x28 on QUPv3 SE0, with IRQ 34, VEN 12, FIRM 35 and CLKREQ 31; the RMX2072 manifest also lists `libsn100u_fw.so`. A first NQ-NCI external-module port based on the SN100-aware 4.19.325 implementation is staged on `experiment/nq-nci-gki-6.18`, with current I2C/class API adaptations and a pinned GKI 6.18 compile-smoke workflow. Workflow run #1 is in progress. This is not yet a successful compile, KMI audit, module load or hardware test. The 4.19.325 KONA techpack build injects additional display/camera/audio config fragments; its shared Oplus touch config does not select GT9886 even though the driver exists. The F.15/F.17 vendor provenance mismatch and exact handset component IDs remain open.

Tasks:
- [ ] Compare official 4.19.81, shared 4.19.157 and community 4.19.x trees by subsystem.
- [ ] Identify the exact device configuration and downstream patches in each tree.
- [ ] Map drivers to upstream Linux and ACK implementations.
- [ ] Inventory exported symbols, private headers, firmware dependencies and userspace ioctl contracts.
- [x] Complete the first-pass KGSL/Adreno 650 source diff: official RMX2072 4.19.81 vs SM8250-Common 4.19.325.
- [x] Inventory KGSL ioctl/UAPI changes and run a preliminary host LP64 sizeof/offsetof probe.
- [x] Confirm that pinned GKI 6.18 contains DRM/MSM A6xx support with an Adreno 650 catalog entry, but not the legacy KGSL path/UAPI.
- [ ] Repeat KGSL UAPI layout probes with a pinned AArch64 Android LLVM toolchain.
- [ ] Audit modern KGSL undefined symbols against the exact Android 17 GKI KMI list and exported-symbol set.
- [ ] Identify drivers already available upstream for the exact hardware, including exact 6.18 file/config evidence.
- [ ] Identify closed-source kernel modules and userspace components that cannot be rebuilt.
- [ ] Audit ION, DMA-BUF, DMA-BUF heaps, secure buffers and their GPU/camera/audio clients.
- [x] Create the first-pass driver migration matrix from pinned source evidence.
- [x] Record the dependency order for SoC, memory, graphics, IPC, multimedia and peripheral drivers.
- [x] Expand the hardware inventory with RMX2072-specific manifest clues and unresolved physical variants.
- [x] Cross-check the official 20607 NFC DTS node and SN100 vendor-manifest evidence.
- [x] Stage the first NQ-NCI external-module port and pinned GKI 6.18 compile-smoke workflow.
- [ ] Classify each subsystem with content-level API/KMI, DTS, firmware and userspace-ABI evidence.
- [ ] Complete NQ-NCI compile smoke, imported-symbol/KMI audit and userspace ABI review.

**Deliverables:**
- Driver migration matrix in `docs/DRIVER_MIGRATION_MATRIX.md`
- Driver dependency map in `docs/DRIVER_DEPENDENCY_MAP.md`
- Kernel porting strategy in `docs/KERNEL_PORTING.md`
- Source comparison notes and pinned commit references
- Proprietary dependency inventory without redistributing blobs

**Acceptance criteria:**
- Each critical subsystem has a documented source, dependency and migration strategy.
- High-risk blockers are identified before choosing a GKI target.

### M6 — Legacy kernel reproducibility and incremental modernization

**Goal:** Build a reliable device kernel baseline and reduce downstream technical debt before attempting a major kernel jump.

Tasks:
- [ ] Rebuild the selected legacy kernel with a documented toolchain/config.
- [ ] Verify the resulting image on the device using a safe test/rollback process.
- [ ] Compare the 4.19 source trees and select the best-maintained device-compatible baseline.
- [ ] Backport security and correctness fixes where feasible.
- [ ] Prefer upstream implementations for isolated drivers where compatibility permits.
- [ ] Test each subsystem change independently.

**Deliverables:**
- Reproducible legacy kernel build configuration
- Device-tested baseline and test logs
- Backport/change log

**Acceptance criteria:**
- The selected kernel builds reproducibly and boots on the physical RMX2072.
- Recovery to the known-good baseline is demonstrated.

### M7 — ACK/GKI feasibility prototype

**Goal:** Evaluate a modern ACK/GKI kernel for RMX2072 without assuming that a successful compile implies device compatibility.

**Progress note (2026-11-06):** The first module experiment is staged on branch `experiment/nq-nci-gki-6.18`: NQ-NCI for the SN100 NFC controller, with a compile-smoke workflow against the pinned Android 17 GKI 6.18 source. The GKI source fetch, defconfig and modules_prepare pass. After fixing three missing static prototypes and replacing no_llseek with noop_llseek, workflow run #6 produced an AArch64 relocatable nq-nci.ko. MODPOST warned that Module.symvers was absent because this is a modules_prepare-only build. KMI/signing/load/probe and NFC functionality remain unverified.

Tasks:
- [ ] Select a candidate ACK/GKI branch based on the target Android release's official support matrix.
- [ ] Confirm KMI policy, protected symbol lists, toolchain and build system.
- [x] Stage the first NQ-NCI external-module compile experiment against the pinned 6.18 source.
- [x] Produce the first AArch64 NQ-NCI compile-smoke module against the pinned GKI 6.18 source.
- [ ] Build the full GKI kernel, obtain Module.symvers and audit module imports against the exact GKI KMI/export list.
- [ ] Audit the handset boot architecture and determine how GKI, DTB/DTBO and vendor modules could be packaged.
- [ ] Prototype the simplest boot path before porting all hardware drivers.
- [ ] Port or replace the minimum drivers needed for boot and basic display/input.
- [ ] Build vendor modules against the exact target KMI.
- [ ] Resolve module signing, symbol versioning, module load order and SELinux constraints.
- [ ] Validate vendor HAL dependencies on legacy kernel interfaces.
- [ ] Test camera, GPU, modem, audio, memory and secure-world paths separately.

**Deliverables:**
- GKI branch selection rationale
- KMI/module dependency report
- Prototype kernel and device-tree build artifacts
- Physical boot and hardware test logs

**Acceptance criteria:**
- The candidate kernel boots on the physical device.
- Required modules load against the selected KMI.
- Each hardware feature is explicitly marked tested, broken or not yet implemented.

**Important:** A GKI 6.18 target is a research candidate, not a guaranteed upgrade path. If the required proprietary modules or interfaces cannot be made compatible, reassess the target branch or retain the legacy kernel.

### M8 — Integrated system, hardware validation and maintenance

**Goal:** Combine the validated Android system, device configuration, vendor stack and kernel into a maintainable release.

Tasks:
- [ ] Run the full hardware test matrix.
- [ ] Validate encryption, recovery, AVB behavior and rollback.
- [ ] Measure idle drain, thermal behavior, performance and sustained stability.
- [ ] Define update packaging and OTA strategy appropriate to the device's partition layout.
- [ ] Add CI for source checks, documentation, build metadata and any feasible reproducible build steps.
- [ ] Publish release notes, known issues and recovery instructions.
- [ ] Reassess future Android and ACK branches periodically.

**Deliverables:**
- Release candidate images (distributed only where licensing permits)
- Hardware validation report
- Recovery and update documentation
- Release and maintenance policy

**Acceptance criteria:**
- Core hardware functions pass documented tests.
- Known limitations are published.
- A tested recovery path exists for failed updates.

## 4. Immediate next actions

The next work session should focus on M0, not kernel porting or flashing.

1. Obtain the handset's exact model and firmware build.
2. Run read-only ADB property and partition inventory commands.
3. Record the bootloader and AVB state.
4. Locate the exact stock firmware package and establish a restore route.
5. Add the resulting non-sensitive facts to `docs/HARDWARE_INVENTORY.md`.
6. Pin the official and community source revisions for M1.

Suggested read-only ADB collection (review output and redact identifiers before sharing):

```bash
adb shell getprop ro.product.model
adb shell getprop ro.product.device
adb shell getprop ro.build.fingerprint
adb shell getprop ro.build.version.release
adb shell getprop ro.vendor.build.version.release
adb shell getprop ro.treble.enabled
adb shell getprop ro.product.cpu.abi
adb shell getprop ro.vndk.version
adb shell getprop ro.boot.slot_suffix
adb shell getprop ro.boot.dynamic_partitions
adb shell getprop ro.boot.verifiedbootstate
adb shell uname -a
adb shell cat /proc/partitions
adb shell ls -l /dev/block/by-name
```

Do not publish raw serial numbers, IMEI, MAC addresses, account identifiers or other personal identifiers. Fastboot output should be reviewed and redacted before being added to this repository.

## 5. Definition of done

The project is not considered complete merely because an image compiles or reaches the boot animation. A release requires:

- Reproducible source revisions and build instructions
- A documented and tested recovery route
- Physical boot on RMX2072
- A completed hardware compatibility matrix
- Known issues and limitations
- Clear provenance and licensing for all included components
- No unauthorized proprietary blobs, firmware, keys or personal identifiers in the repository

## 6. Status tracking

Update the checkboxes and milestone status as work is completed. Record evidence links, commit IDs, logs and artifact hashes next to each completed milestone.

| Milestone | Status |
| --- | --- |
| M0 — Device audit and safety baseline | Not started |
| M1 — Source pinning and reproducible legacy baseline | In progress — initial source pins recorded |
| M2 — Treble, Vendor and GSI assessment | Not started |
| M3 — Android 17 GSI bring-up | Not started |
| M4 — Own AOSP build and device integration | Not started |
| M5 — Kernel source and driver asset analysis | In progress — first driver matrix, dependency map and SN100 pilot selected |
| M6 — Legacy kernel reproducibility and modernization | Not started |
| M7 — ACK/GKI feasibility prototype | In progress — first NQ-NCI GKI 6.18 compile-smoke workflow running |
| M8 — Integrated system and maintenance | Not started |
