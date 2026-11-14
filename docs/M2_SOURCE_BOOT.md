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

The source PON parent has no `mode-*` properties. In the pinned ACK
`drivers/power/reset/reboot-mode.c`, an unmatched mode returns zero and the
notifier invokes the hardware write only for a nonzero mode. Thus the new parent
does not add reboot-mode register writes in this configuration. This source
audit does not replace the physical EDL/reset ordering test.

The official Q source comments out the legacy device-tree vendor fstab; the
measured F.20 tree contains that entry. M2 deliberately uses the already accepted
project ramdisk fstab. The source checker requires the absence of the legacy DT
fstab and extra PON mode properties. Firmware vbmeta partition names and PSCI
properties match the measured baseline; the obsolete `kasan_multi_shot` DT
bootarg is absent from the Q source.

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

The live retained M1 boot `2e26c4dd-3cab-41a9-8396-7912c0a0ffac` supplies the
bound-platform-device list. `m2-m1-resource-reference.json` records 79 validation
nodes covering those active devices, their regulator children, interrupt/timer
providers and reserved memory. References are compared by provider path and
argument cells, not numerical phandle equality. The source tree passes this
comparison; the explicitly replaced PON is checked against its new parent/child
binding. This measurement file is a validation input only, never used to
construct the source device tree. It does not qualify inactive display, audio,
radio or other unported hardware.

Source-init run 43614577780 passed the previous dependency failure, then rejected
the obsolete `BOARD_BUILD_SYSTEM_ROOT_IMAGE` product variable. That variable and
the deprecated 64-bit Binder setting were removed for Android 17. The build
continues with the same pinned upstream sources and project product.

`build/device/m2-source-dt-build-2026-11-15.json` records the clean offline build,
its output digests and the complete recovery-set recheck. That record deliberately
marks hardware acceptance as not run. `fetch_m2_artifact.py` installs only artifacts
from a successful pinned workflow and checks source/configuration/output digests.
`rebuild_m2_source_trial.py` then prepares one current candidate while verifying
that the GSI, signed vendor, guard and super container remain the accepted inputs.

The reconnect observer captures arrival uptime and the same-boot component and
power-provider evidence before retention. Missing source markers, mismatched init
or power-provider evidence requests guarded rollback. The existing M1 cold-start
record remains valid under the extended checker. A disconnected power-key start
and a separate watchdog expiry/recovery run are still required on the new pair.

Run 43616087095 reached the next product check and required explicit 64-bit app
support for the arm64-only target. The project now declares the same ABI support
flags as upstream `core_64_bit_only.mk`, without adding an Android image build.
The hosted runner also releases unused preinstalled SDK space before AOSP sync;
the previous host had only 24 GiB free after fetching the selected sources.

An upstream `bionic/libc/Android.bp` dependency audit additionally identified
`libscudo`, `gwp_asan` and `gwp_asan_headers` in static libc. Their pinned
`external/scudo` and `external/gwp_asan` projects are included explicitly.

The first three failed build logs are indexed by run, source revision, first
failure and full-log digest in `build/device/m2-build-progress-2026-11-15.json`.
Run 43617659636 was superseded during sync; run 43617966430 includes those libc
dependencies. Host checks passed all 81 cases, including the four DTC-dependent
checks run after adding the checked compiler to PATH. M2 acceptance also rejects
a missing, duplicated or writable LUN in the six-disk same-boot witness.

Kernel run 43613974200 failed when the hosted runner exhausted disk space,
including its own worker log. GitHub's check annotation reports
`System.IO.IOException: No space left on device`; no artifact or job log was
available. This is a host failure, not evidence of a compiler or handset failure.
The bootstrap workflow now removes unused hosted SDK/tool caches before syncing
the pinned Kleaf toolchains and records free space before building.

Source-init run 43617966430 passed arm64 product configuration after the bounded
repair added the real `toolchain/pgo-profiles` project. Blueprint then required
`kernel-config-soong-rules`, declared in the pinned `kernel/configs/build/Android.bp`.
Both projects are now explicit workspace dependencies. This is still a source
workspace failure before compiling the target executable.

The static target dependency audit also follows modern protobuf into
`external/abseil-cpp`, and `libsnapshot_init` into `external/libchrome` with its
`external/modp_b64` and `libnativehelper` dependencies. These real upstream
projects are selected explicitly. Host Python launchers/stdlib are already
provided by the pinned build-tools project; no replacement libraries or stubs
are introduced.

Run 43619675442 completed Blueprint bootstrap after adding `prebuilts/siso`,
then Soong reported the missing team metadata `trendy_team_webapps_cros_android`.
The exact upstream definition is in
`frameworks/base/core/java/android/hardware/serial/Android.bp`; the selected
workspace now includes its source project rather than synthesizing that module.
This check is global to the partial workspace even though serialservice is not
part of the requested init target.

`frameworks/base` is sparsely checked out to that original metadata file only;
its Git revision remains in the resolved manifest and the sparse path is saved
with the build evidence. This avoids making unrelated framework modules part
of the partial workspace. No init or library implementation is taken from that
sparse project, and no team declaration is fabricated.

Kernel run 43619212111 succeeded after the disk-space fix. The selected artifact
members, raw Image, source patches, resolved common source and required built-in
configuration passed local verification. The raw Image digest is
`96631ce06d589f82267aa6f833fd1bb86dfabced4aba3a92a03bf518f720b487`.
`build/device/m2-source-kernel-build-2026-11-15.json` records the result. Source-init
run 43621938934 failed on another missing owner declaration; the handset still runs the accepted M1 image.
No M2 boot has been flashed. Before any candidate write, the runner requires the
current raw kernel, ramdisk, boot and build records to agree, rejecting an
incomplete component refresh before entering EDL.

Run 43621938934 required `trendy_team_aaos_vac_triage`, declared in the pinned
`packages/services/Car/teams/Android.bp`. That project is now sparsely checked
out to its original team metadata only, with the resolved revision and sparse
path checked by the artifact installer. Run 43623644069 passed these owner checks.

The standard libfdt merge keeps the base root compatibility unless a fragment
changes it; DTBO root selector properties are not payload. The source overlay
now explicitly supplies the measured `qcom,kona-mtp` compatibility list and
`oplus,dtsi_no = <20607>` in its root fragment. This preserves the conditions
used by the SCM recovery and PON notifier guards regardless of bootloader
selector-copy behavior. Both the offline effective tree and the pre-policy
runtime witness must carry that identity. The rebuilt pair passes the 79-node
resource comparison and the USB/UFS/watchdog/PDC/PON checks. This remains an
offline result; hardware selection and recovery still need the M2 trial.

Run 43623644069 then failed global Soong analysis on the unrelated
`apex.apexd_test_bootclasspath-fragment`: its Java test payload has no framework
dex jar in this native-only workspace. `system/apex` now keeps all implementation
sources while sparse checkout excludes only `apexd/apexd_testdata/`. The exact
exclusion and pinned project revision accompany the artifact and are validated
locally. No init source, target dependency implementation or build-tool validation
is patched. Run 43625784408 passed this test-data error.

Run 43625784408 next reported an Error Prone requirement from the unrelated
`framework-virtualization.impl` Java module. Upstream init only consumes
Virtualization's `libavf_cc_flags` headers and `avf_build_flags_cc` defaults.
The project is now sparse to those original files, its root package metadata,
and the build directory's flag declaration; these exact paths are also verified
on artifact installation. The missing-path parser now recognizes question-mark
punctuation in diagnostics and its regression tests pass. Source preparation
and target compilation are separate workflow steps. Run 43627891448 reached the next global graph error;
no M2 image has been flashed.

Run 43627891448 passed source preparation, then the upstream Rust aconfig
generator panicked on `libaconfig_android_hardware_biometrics_rust`, an unused
keystore2 module whose framework declaration is absent. Selecting all `system/`
projects was pulling server, networking and security components into a static
init build. The manifest now explicitly selects the native init/storage/base
libraries and required build-tool projects: 115 initial projects instead of 152.
The real init dependency graph is still built, and missing dependencies of the
requested target remain fatal. No Rust generator or init implementation is
patched. This workspace change does not alter the handset GSI, project HAL or
vendor. Run 43629741053 is building the bounded selection; handset M2 acceptance
remains unrun.
