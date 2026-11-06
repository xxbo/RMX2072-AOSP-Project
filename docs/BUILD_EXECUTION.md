# Build and device-test execution

The execution path is GitHub Actions for kernel/driver builds, a selected official Google Android 17 ARM64 GSI for the system layer, and the locally connected RMX2072 for flashing and hardware tests. A local full AOSP build host is not required for this phase.

## Legacy build gate

`Legacy Kernel Build` is manually triggered. Run `stage=config` first; use `stage=kernel` after configuration validation.

Configuration validation passed in [run 42224170969](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42224170969). The first full legacy kernel/modules run has been dispatched; its build result remains pending.

Inputs are fixed by `sources/SOURCE_LOCK.json` and `build/legacy-kernel.json`. The selected community 4.19.325 source has the complete Techpack reference, while the official Q/S trees contain Techpack stubs. This is a candidate build, not a proven F.20 source match. The actual handset runs 4.19.157-perf+.

The build uses `vendor/kona-perf_defconfig`, `vendor/oplus.config` and a small project-owned GT9886 fragment supported by the running F.20 configuration. It verifies required assignments in the generated `.config`. Makefile-injected Techpack flags still need comparison with that generated config; this does not solve all source-pairing gaps.

Clang r416183b is pinned to an immutable official prebuilt commit and selected because the kernel's build.config.common names it. Host package versions, commands, archive hashes, final config hash, build logs and output hashes are retained as evidence. Build identity/time are fixed. This has not yet established byte-for-byte reproducibility across independent builds.

The full build requests Image.gz, DTBs and modules. Outputs include Module.symvers and System.map when produced. Modules in this job target the selected 4.19 kernel, not 6.18. No boot.img, automatic flashing or device-ready ZIP is produced. Source revisions and file-level licenses remain authoritative when redistributing any resulting artifact.

## ACK 6.18 gate

The existing `experiment/gki-6.18-repo-mirror` branch has already passed a complete Kleaf build in [run 42194678844](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42194678844), producing a 687,670,307-byte uploaded artifact. Its workflow, source pins and NFC experiment are now being integrated into the mainline execution path. Preserve this evidence instead of repeating an initial generic-kernel feasibility experiment.

The kernel/common pin already resolves to 6.18.32. The main workflow now locks all 58 manifest projects using the resolved snapshot from that successful run, verifies every checkout and adds a strict NQ-NCI DDK compilation gate. A kernel/common SHA alone is insufficient. The default manifest includes extra device/test projects; evaluate its groups and workspace footprint on the Actions runner rather than downloading everything blindly.

Then build a generic ACK baseline, add a separate KGSL compile/KMI probe, and introduce the RMX2072 boot/DTS/UFS/USB changes. A generic GKI Image is not an RMX2072 boot image. The existing boot header is v2 with an embedded DTB bundle; vendor_boot/init_boot are absent from the physical GPT.

## GSI gate

Select an official ARM64 GSI without GMS for the initial experiment, record its exact build/download/hash, and inspect its actual VINTF matrices, VNDK/linker support, sparse/raw size and system partition fit. Stock F.20 declares vendor FCM 5, while the inspected Android 17 source's default matrix list begins at FCM 7. Resolve this gap with image evidence and a compatibility test, not by arbitrarily changing the declared vendor target level.

First test the system layer against the compatible stock kernel/vendor. Test a new 6.18 kernel separately so failures can be isolated. Keep the existing local backups; full-system recovery from them is not yet exercised.

## Evidence and synchronization

Commit project-authored code/configuration, source pins and redacted findings promptly. Keep full images, proprietary vendor files, calibration/secure data, device identifiers and raw captures local. Public CI artifacts contain build products/provenance only; private handset backups must never be added to Actions artifacts.

Record build-tested, boot-tested and hardware-tested independently. Update this document and the compatibility matrix after each actual run.
