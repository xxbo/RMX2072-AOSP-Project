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

## Candidate preparation on November 15

`build_m2_device_tree.py` compiles the full official 20607 base and MTP overlay,
then applies the project's source USB SID0, watchdog, UFS HS-G3 and PDC overlays.
The generator reads pinned Git blobs, resolving the input-event header symlink
on Windows without modifying the upstream checkout. It checks USB, watchdog,
UFS resources and PDC routing before and after the full board overlay.

The project adds the measured boot-firmware log and ECC ramoops reservations,
retains the F.20 WLAN allocation size and renames the board selector explicitly.
A reviewed source patch replaces only SID 0's legacy PON with an upstream PON
parent and power-key child; SID 0 peripheral addresses use the upstream one-cell
form. Secondary/modem PON instances remain inactive. No resin or PMIC watchdog
driver is enabled by this change.

Each new container has one exact 20607 entry and contains no OEM binary trees.
The complete source board overlay supplies PMIC and board hardware content.
The earlier no-op/premerged failures do not establish that this new pair boots;
bootloader selection and actual runtime markers remain physical acceptance
items. The packer retains measured boot load metadata and original AVB envelopes
for the unlocked engineering trial; those envelopes do not sign the new payload.

The trial runner now reads back the paired DTBO and restores the original DTBO
alongside boot and all super chunks on failure. A new pre-policy witness records
both source-tree markers, the actual FDT digest, first-stage init digest and boot
UUID. ADB retention requires those values to match the candidate. Power checks
separately require both upstream PON parent and power-key child to bind and to
report primary subtype 4 on the same boot.

The first source-init build (run 43612987811) synchronized successfully but lacked
Soong's `external/pogreb` project. The manifest now includes that pinned project.
A bounded build retry can add other missing paths only when they name projects
in the pinned upstream manifest; it never creates substitute source or libraries.
Source-init and source-PON kernel builds are still in progress. No M2 handset
boot, cold-start or recovery result is claimed at this stage.
