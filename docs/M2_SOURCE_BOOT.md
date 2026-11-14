# M2 source-built boot components

M1 trial 35 is the handset baseline. M2 keeps its GSI, signed project vendor,
disposable data/metadata seeds and verified original recovery set. Acceptance
requires source-built DTB/DTBO and first-stage init, then disconnected startup,
ADB/verified UFS identity and watchdog-triggered prepared-host recovery on the
exact candidate. No M2 hardware result is claimed by a compile success.

## First-stage init

The initial build recipe uses AOSP tag `android-17.0.0_r1`, manifest commit
`5bc9a7ce1cd78dd53613bbfd0ebf506e1e4adb0f` and system/core commit
`545d2487e38192a2ce25040897ced877cf6b4f53`. It builds the upstream static
`init_first_stage` target as a `user` product; the existing GSI supplies
second-stage init. Sources are selected from the pinned manifest and the
resolved project revisions accompany the artifact. This build does not create
another system/vendor image.

Only dependencies needed by the selected source workspace are synchronized.
`ALLOW_MISSING_DEPENDENCIES` permits unrelated modules to remain outside that
workspace; a missing dependency in the requested target remains a fatal Ninja
edge. A successful target, static AArch64 ELF inspection, source provenance
and hardware validation are required before replacing the emulator binary.

## Board source

The pinned official Android S repository has an external vendor-DTS symlink,
so that checkout alone is insufficient. The official X50 Pro Player Android Q
repository contains `arch/arm64/boot/dts/20607/`, including `kona-v2.1.dts` and
`kona-mtp-overlay.dts`, at commit
`24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4`. Its OEM selector is named
`oppo,dtsi_no`; the measured F.20 selector uses `oplus,dtsi_no`. This difference
and bootloader selection must be handled explicitly. Compiling a decompiled
factory blob is not the source replacement being pursued here.

The new components are not flashed until their inputs, selected board IDs,
reserved memory, interrupt routing and boot/recovery packaging are checked.
Only the original recovery set and current candidate image versions are kept.

The source-tree kernel option enables `CONFIG_POWER_RESET_QCOM_PON` for the
upstream `qcom,pm8998-pon` parent and `qcom,pm8941-pwrkey` child. It does not
apply M1's `qcom,qpnp-power-on` alias patch. The separate small patch logs the
actual PON revision/subtype and preserves the proven board-specific notifier
ordering: SCM selects warm EDL before the power-key driver selects reset type.
Legacy and source-tree PON build options are mutually exclusive. Source-tree
PON must pass its own warm, disconnected-start and fault-recovery tests.
