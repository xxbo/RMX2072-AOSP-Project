# M3: physical display on the 6.18 GSI

The current objective is physical panel output, then a running SurfaceFlinger
and AOSP Launcher on the same Android 17 GSI. Cold-start and watchdog rehearsals
are not part of this work. Each stage report identifies its objective, physical
result, next blocker and source/evidence commit.

## Starting observation, November 15

The accepted trial 36 remains on boot
`efd2f392-667a-4cf6-b252-4c76bfc5e4a9`, with authenticated ADB and
`6.18.32-android17-5-maybe-dirty-4k`. A fresh observation found SurfaceFlinger
restarting, no boot-completed property and no `/dev/dri` or `/dev/graphics`.
[Initial evidence](../build/device/m3-desktop-blockers-2026-11-15.json) identifies
the missing OpenGL ES implementation and disabled DRM/MSM kernel configuration.

## Display implementation

The project panel driver translates the selected official RM19795 Samsung
command sequence into a DRM MIPI-DSI panel. Its source is
`arch/arm64/boot/dts/20607/dsi-panel-rm19795samsung-ams641rw01_1080_2340.dtsi`
at realme commit `24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4`. The importer verifies
the Git blob SHA-256 and preserves all packet types, payload bytes, LP/HS mode
and delays: 28 initialization packets, four display-on packets and four off
packets. The filename says 2340; the selected mode actually specifies 1080x2400.
Only the 60 Hz mode is exposed initially: RGB888, four lanes, DSC 1.1 at
8 bits per component / 8 bits per pixel, two 540x48 slices. Brightness is capped
at the source's normal range (1023), with default 400; no HBM command is used.

The M3 DT overlay describes the native ACK SM8250 MDSS/DPU, DISPCC, DSI0/7nm PHY,
MMSS interconnect and RPMh MMCX domain. It uses real PM8150 L14 / PM8150L L2,L11
regulators, TLMM75 reset and TLMM66 TE. The native TLMM node is separate from
the inactive downstream node so unrelated OEM pin consumers are not enabled.
The overlapping downstream display providers are disabled after the full board
overlay; USB/UFS/PDC/PON resource checks remain required. The CPU-rendered profile now explicitly disables the inherited legacy GPU
and GMU in the final source DTBO. Trials 37-39 did not enforce this boundary;
trial 39 exposed the resulting GPU initialization BUG described below. Any display bridge or firmware handoff dependency
still needs physical qualification; successful compilation does not establish it.

Trials 37 and 38 omitted the previously established GPIO validity restriction.
The [November 9 isolated TLMM comparison](RMX2072_EDL_AND_UFS.md#why-the-gpio-mask-matters)
already showed that unrestricted registration rebooted, while exposing only
the UFS pad registered successfully. Gpiolib reads each valid pin's direction
during registration. The corrected display overlay exposes only TE 66 and
reset 75, and its checker rejects any other valid offset. This avoids probing
unrelated firmware-owned pins; it does not yet prove either display pin works.

The static KMS probe uses DRM ioctls and driver-allocated dumb buffers. It finds
a connected physical DSI connector with the expected mode, sets a colored test
pattern and waits for four actual page-flip events. It releases DRM master and
buffers before Android starts. It never writes guessed framebuffer addresses or
storage. The initramfs publishes its result and display probe/deferred-driver
logs into the existing scratch `/data` for ADB. A KMS return of success alone
is not recorded as operator-confirmed screen output.

The previously captured F.20 boot explicitly reports `iris chip enable: false`,
`soft iris enable: false` and `is_pxlw_iris5: false` for the selected RM19795
panel. Its saved log digest matches the original acquisition record. This
supports continuing the direct native DSI path despite Iris properties in the
shared board DTS; it does not warrant enabling additional GPIOs or inventing
an Iris dependency. [Stock display evidence](../build/device/m3-stock-display-reference-2026-11-15.json).
No additional stock boot was performed for this comparison.

## Graphics implementation

The bounded Android 17 source product builds ANGLE EGL/GLES, SwiftShader Vulkan,
minigbm configured for MSM and the generic DRM HWC3 service. Composer uses mapper
metadata rather than a downstream SDM/KGSL backend. These are native ARM64
libraries and HALs for the actual device. Initial CPU rendering is an explicit
intermediate dependency; this does not claim Adreno 650 support. The GSI itself,
source first-stage init and writable test-volume seeds stay fixed.

The CPU-rendered vendor sets the upstream `vendor.minigbm.debug=nocompression`
option and gives it an exact public vendor-property label. The pinned MSM
allocator otherwise offers higher-priority UBWC layouts that its CPU mapping
path rejects. Its software-renderer detection does not pass the augmented use
flags to format resolution in this tag. The existing option keeps allocations
linear without modifying the graphics binaries or enabling Adreno.
[Source analysis](../build/device/m3-linear-buffer-reference-2026-11-15.json).
Actual allocation and presentation remain pending device integration.

## Stage acceptance

### Trial 37: early boot regression

The source display kernel build passed and its selected artifact members and
panel-source digests were verified. Trial 37 preserved the GSI, vendor, DTBO and
test seeds, read back the complete current super, and verified the new boot
write. The operator observed repeated reboots. Neither diagnostic ACM nor GSI
ADB appeared, so no KMS result or physical panel output was established.
Operator volume keys returned the phone to EDL. F.20 restoration, boot
completion, both LP metadata slots and the complete physical super digest
passed. The recovered console identifies `Couldn't find UBWC config data for
this platform!` followed by MDSS probe error `-22` at 0.706972 seconds. ACK's
UBWC database matches `qcom,sm8250`; the retained legacy root compatibles do
not include it. The M3 source overlay now appends this upstream SoC identity
while preserving all measured board identities used by SCM/PON guards.

This is a confirmed display probe blocker, not a complete explanation of the
reboot loop. The console stops at 0.813605 seconds and reports 28 unrecoverable
ECC blocks. No complete panic stack was recovered. The next candidate enables
`initcall_debug` to identify any remaining early initialization stall, using
the same compiled kernel, GSI and test seeds. No screen output is claimed.
[Trial evidence](../build/device/m3-display-37-2026-11-15.json).

### Trial 38: corrected SoC identity, unresolved early reboot

Trial 38 appended the upstream compatible and enabled initcall tracing while
retaining the compiled kernel, GSI, vendor and test seeds. The operator again
observed repeated reboots before ACM or ADB. F.20 restoration, full super
readback and device-side hash, both LP slots and boot completion passed.
The preserved console reaches approximately 1.07 seconds near deferred driver
probing, but reports 905 corrected bytes and 1,673 unrecoverable blocks. It
cannot establish a last failing driver or a complete panic stack. The lack of
an intact UBWC error in this damaged record is not proof of a successful bind.
[Trial evidence](../build/device/m3-display-38-2026-11-15.json).

Trial 39 restores the known TLMM valid-GPIO restriction described above. It
exposes only display TE 66 and reset 75. This corrects a missed historical
constraint; physical boot and display results remain pending.

### Staged display diagnosis

The GPIO-limited trial 39 still did not enumerate diagnostic USB or ADB.
F.20 restoration and complete readback/device-side verification passed.
The preserved console contains an intact `a6xx_gpu.c:2658` BUG line. ACK MSM
also matches the legacy KGSL compatible; the inherited GPU was still `ok` and
lacked the upstream `qcom,gmu` link required by `a6xx_gpu_init`. The source
DTBO now disables the unported GPU and GMU, and effective-tree checks reject
any available matching node. No physical screen output is claimed.
[Trial 39 evidence](../build/device/m3-display-39-2026-11-15.json). The next diagnostic profile uses `--display --display-staged` and
keeps the same kernel binary. Three explicit population containers defer the
native display GPIO provider, display fabric/clocks and MDSS/DPU/DSI until
USB logging is connected. They reuse the already built, bounded platform
population driver; they do not substitute any display driver implementation.
The full source graph, GPIO restriction and M1 resource checks remain required.

The pre-policy script emits `M3BIND` begin/return markers for each stage and
the host records the live kernel stream before releasing a boot-ID gate.
Failure of an individual binding leaves its result in the same-boot record;
if execution remains responsive, Android startup is still attempted. This
profile explicitly records `autonomous=0` and requires a matching host gate.
It is a display fault-localization run, not a cold-start acceptance result.
No new GSI, test-volume seed or graphics userspace is installed by this profile.

The first graphics source build failed on the upstream libdisplay-info
visibility boundary. A narrow project-package fix resolved it. The second
build generated a 7,652-command target closure and identified two missing
libraries for the real VINTF fragment tool. Their pinned AOSP Gki and
vts-testcase/hal source projects are now included. Build 43672280150 generated
an 8,446-command closure and identified HardwareBuffer_aidl as the remaining
missing module through media interface metadata used by assemble_vintf. The
M3 sparse checkout now includes its pinned frameworks/base AIDL, original build
declarations and license. Build 43673925967 then exposed unrelated framework
root build-file imports. The native product now selects the two original
module blocks and package declarations byte-for-byte from pinned files, with
independent SHA-256 checks on input files and selected modules. The real AIDL
and license text stay unchanged; no implementation or dependency is stubbed.
The next source build is pending.
No missing-library stubs or skipped target checks are used.
[Build evidence](../build/device/m3-graphics-build-2026-11-15.json).
These build issues are independent of the early kernel regression: graphics
userspace was not installed in trials 37 or 38.

### Trial 40: native DRM registered, GSI retained

Disabling the inherited, unported KGSL/GMU nodes removed the identified trial
39 panic. Trial 40 bound native TLMM, MMSS interconnect, DISPCC, MDSS, DPU,
DSI and the source RM19795 panel. The intact serial stream records DPU revision
`0x60000000` and `Initialized msm 1.13.0`. Android 17 reached enforcing and
authenticated ADB on boot `7e5e1a20-264a-4a18-9e42-6b584307f8e4`; the phone
remained on this GSI after the bounded same-boot acceptance check.

The pre-policy KMS probe did **not** run a modeset: it returned
`DRMTEST blocked=no-card0 errno=2`. DRM sysfs already exposed `226:0`, but the
temporary `/dev` had no DRM node. Android ueventd created it later. A subsequent
ADB-shell attempt returned `errno=13` under enforcing and also performed no
modeset. SurfaceFlinger still aborts because the graphics vendor payload has
not been installed. Visible output, page flips and desktop startup remain
unproven. [Trial 40 evidence](../build/device/m3-display-40-2026-11-15.json).

Trial 41 creates the early DRM character node only after verifying its native
SM8250 DPU parent and reading its actual sysfs device number. It keeps the same
kernel, source trees, GSI, vendor and writable test-volume seeds. The next
physical result must come from the KMS probe, with screen observation reported
separately. No cold-start test or watchdog fault injection is planned.

### Trial 41: previous RAM journal prevented the display experiment

The unchanged super and new boot readbacks passed. Boot
`e710c03b-bb4f-4654-a98b-9a31f597cfd0` entered diagnostic recovery because the
previous trial 40 pmsg had 92 corrected bytes and 112 unrecoverable ECC blocks.
The marker parser returned `unreadable`. No display bind or modeset ran; the
observer correctly refused a missing gate. The prior console and pmsg were
preserved before the phone entered EDL without keys. F.20 restoration passed
complete super/boot/DTBO readback, both LP slots, device-side super hash and
boot completion. [Trial 41 evidence](../build/device/m3-display-41-2026-11-15.json).
This reproduces the prior RAM-journal limitation described in the trial 34
power record; it is not evidence of a new panel failure.

The next staged profile waits for a matching, one-boot host gate before
attempting Android, independently of the previous journal decision. The host
has already verified the candidate image readbacks; it preserves the old
journal decision and starts the serial stream before releasing the gate.
No host means no display bind and no Android attempt, with the existing
180-second supervisor still active. Normal autonomous boots keep their
unchanged fail-closed journal decision. This diagnostic profile remains
explicitly `autonomous=0`, and does not count as a cold-start result.

### Trial 42: first modeset exposed a DSI pixel-clock failure

The host gate, native driver binding and measured `226:0` device node passed.
The probe opened MSM DRM, found the connected 1080x2400 DSI mode and allocated
two 10,444,800-byte dumb buffers. The kernel then warned that
`disp_cc_mdss_pclk0_clk_src` did not update its configuration. The first panel
packet (`0x39`, DCS `0x9f`) timed out with `-110`; DPU frame-done/kickoff also
timed out. These are intact live-serial observations on boot
`9e44af1e-8841-4eb7-8bc2-ddc67fc34e2d`.

The initial probe incorrectly printed `kms_scanout=PASS`: the modeset ioctl
returned success and four completion events arrived, but all four reused
sequence `40` and timestamp `34.955539`. That is not advancing scanout. The
recorder rejects this result, and the probe now requires increasing sequence
and timestamps. Four focused regressions cover stale events, advancing events,
transport errors and a missing device. The new ARM64 probe compiles; it has
not yet run on the phone. The operator reported a black screen, with no color bars.
[Trial 42 evidence](../build/device/m3-display-42-2026-11-15.json).

Android 17 still reached enforcing ADB and remained on the same GSI. The next
driver work targets DSI pixel-clock/PLL sequencing. Graphics policy for both
direct and staged display paths passed strict compilation on this retained
boot, using a compiler verified byte-for-byte against the pinned GSI. No policy
was loaded. `check_m3_graphics_policy.py` records the live policy input hashes;
the graphics candidate builder can preserve the staged diagnostic path.
[Policy proof](../build/device/m3-graphics-policy-2026-11-15.json).

### Trial 43: deferred DSI parent selection did not resolve the timeout

The clock patch imports upstream `acf7a91d0b0e`'s `CLK_OPS_PARENT_ENABLE`
for the two SM8250 pixel RCGs. The project companion uses the existing ACK
6g_v2_9 source-clock acquisition and parent-setting operations for SM8250
nodes that explicitly supply those clocks. The source DT removes early
`assigned-clock-parents`; host power-on selects the parents after the manager
has enabled the PHY. Parent-setting errors propagate. Existing SM8250 DTs
without the explicit source clocks retain their previous clock-init path.

This is a testable sequencing hypothesis for trial 42's RCG timeout, not an
established hardware fix. The upstream flag has a documented probe-time PLL
regression with assigned parents. The proposed 7nm DIGTOP bias change also
has an unresolved SM8350 HDK boot regression, so it is not included here.
No PHY register values or panel commands are changed. References:
[upstream clock patch](https://lore.kernel.org/r/20260312112321.370983-9-val@packett.cool),
[probe-time regression](https://lkml.iu.edu/2606.2/04819.html),
[DIGTOP follow-up](https://lkml.iu.edu/2610.0/02665.html).

The build emits a separate clock-patch digest; artifact import verifies it
against the exact source commit. Boot packaging rejects a new display DT
paired with the old kernel. Effective-DT checks require all four explicit
source-clock references and reject early assigned parents. The next physical
trial also includes the corrected advancing-event KMS probe and DRM driver
logging (`drm.debug=0x2`) for the actual PHY/link rates. The GSI and test
volume seeds stay fixed; no cold-start or watchdog qualification is added.

The paired kernel built successfully in run `43679894046`; patch/source and
selected distribution digests passed verification. Trial 43 ran on boot
`8cbdf30b-a078-41c3-a9e3-8938f6fe839f`, using kernel image SHA-256
`1571dee26287393cf2572a314a1e1696ee58ca2eb0e855ed5e2857e82524cfd6`.
The log confirms PHY enable, restored 660 MHz VCO, then a request for
70.272 MHz pixel / 52.704 MHz byte clocks and an 843.264 MHz VCO. The pixel
RCG update and first DCS packet still time out. The corrected KMS probe stops
at the second repeated vblank event and returns failure, rather than a false
PASS. The operator missed the brief test and saw black when checking later;
there is no positive visual confirmation. Enforcing GSI ADB was retained.
[Trial 43 evidence](../build/device/m3-display-43-2026-11-15.json).

Graphics run `43675503669` completed 8,464 build steps successfully, but its
archive stage assumed a separate `vendor` output while AOSP installed into
`system/vendor`. No installable payload was saved. The archive script now
queries `TARGET_OUT_VENDOR`, validates its product path and includes that path
in the checked artifact manifest. The completed ephemeral runner cannot be
reused, so this packaging correction requires a new build. SurfaceFlinger
integration remains pending an actual verified archive.

Trial 44 keeps the trial-43 kernel and adds read-only CCF snapshots to the
pre-policy KMS probe, immediately before and after modeset. It records the
DSI PLL/byte/pixel chain's parent, rate, software prepare/enable references
and flags through native debugfs files. These counts do not prove PLL lock,
and rates may be cached; the purpose is to distinguish an unselected or
unprepared parent from a hardware clock/transport failure while the pipeline
is still active. No clock registers are written by the probe. The static ARM64
probe compiles with warnings treated as errors. Trial 44 completed on boot
`c0756d90-97b4-41f6-b74e-0181a32d4884`. Before modeset, the DSI parents were
already selected and the VCO prepare/enable counts were both 1; byte/pixel
branches also had nonzero counts. After modeset, these references remained
and CCF reported about 52.704 MHz byte / 70.272 MHz pixel clocks, but the RCG,
first DCS packet and frame completion still failed. The second stale event
was rejected. This rules out the simple missing-parent-reference explanation,
not a physical PLL failure. The next trace must identify the early clock
enable caller and its relationship to PHY reset. No additional operator
screen observation was requested for this failed transport test. Enforcing
GSI ADB remained stable and was retained.
[Trial 44 evidence](../build/device/m3-display-44-2026-11-15.json).

### Next candidate: native DSI REFGEN supply

Trial 43 also reports `supply refgen not found, using dummy regulator`.
The official board's `kona-regulators.dtsi` defines REFGEN at `0x088e7000`,
size `0x84`, and its DSI controller consumes that supply. The pinned ACK
already has `qcom-refgen-regulator.c` with the native SM8250 implementation,
but the candidate had neither its Kconfig option nor a native supply node.
Upstream commit `3aedde1859f341f0f631330928872c535769e20b` adds the same
[SM8250 DSI dependency](https://www.spinics.net/lists/kernel/msg5852544.html).

The next kernel enables the existing ACK regulator driver; the project DT
disables the legacy provider, places its native replacement in the staged
display-fabric group and connects DSI's `refgen-supply`. No private MMIO
sequence or fabricated fixed regulator is added. Full effective-DT resource
checks pass and enforce the provider, address and consumer link. Artifact
import and boot packaging require the driver to be built in. This repairs a
verified missing dependency; whether it resolves the observed clock/DCS
timeout still requires the next hardware test.

The same next trial also arms a separate 64 KiB-per-CPU clock trace before
display provider registration, filters it to DSI0 VCO/byte/pixel sources and
branches, and captures at most 16 prepare call stacks. It stops before Android
handoff and publishes at most 1,200 lines. This measures the caller behind
trial 44's pre-existing software references without writing clock rates,
enables or hardware registers. Trace setup failure is recorded and does not
prevent the existing GSI handoff.

Source review also found a separate panel error: `rm19795_send()` required
the host's returned byte count to equal the payload size. The pinned MSM
`dsi_cmds2buf_tx()` instead returns the DMA packet length, including its header
and padding (8 bytes for the first 3-byte panel payload). A successful transfer
would therefore have become `-EIO`. Accept a return at least as large as the
payload, while preserving negative errors and short-transfer rejection.
Prepare/unprepare are idempotent, and display-on is refused after a failed
prepare. This is a deterministic source fix; it does not explain trial 44's
earlier `-ETIMEDOUT` transport failure and has not yet passed on hardware.

The next kernel also logs native 7nm PLL control, lock and bias-reference
state at its existing set-rate, prepare, unprepare and PHY-enable transitions.
These bounded read-only diagnostics use the driver's mapped registers and
existing DRM debug gate; they add no register writes or clock API calls.
The build that predates these fixes is superseded before device installation.

`graphics_buffer_smoke.c` is a separate GSI userspace diagnostic, built with
the recorded NDK. It creates a real EGL/GLES context, allocates a 64x64 Android
hardware buffer through the installed allocator/mapper, imports it as an EGL
image, renders a known RGBA color, and compares both GLES and CPU readback.
Run it from the existing enforcing ADB shell with a 20-second limit after
installing the graphics vendor. It never acquires DRM master or modesets.
A pass establishes this buffer/render path in the shell domain only; composer,
SurfaceFlinger permissions, physical output and acceleration need their own
evidence. Before graphics installation, trial 44 aborts at EGL loading with
the same missing-implementation error as SurfaceFlinger.

1. Native display bindings and panel source compile; unchanged boot/storage
   resources still validate. This is an offline result, not a hardware pass.
2. On the phone, capture DRM registration, panel prepare/enable, KMS mode and
   page-flip results plus physical screen observation. Preserve ADB diagnostics
   even if the display probe fails.
3. Integrate the built graphics payload with vendor labels, permissions,
   properties and VINTF. Confirm allocator/composer registration and a stable
   SurfaceFlinger with an actual physical display.
4. Resolve remaining framework/Launcher failures and prove the real desktop.
   Adreno acceleration and real touch input remain separately reported results.

Code is tracked in [PR 22](https://github.com/xxbo/RMX2072-AOSP-Project/pull/22).
Only the original recovery set and the current image candidate are retained.


### Trial 45: boot-held clocks survive the PHY reset

Kernel run `43684993723` passed and its selected image/config/source digests
were checked. Trial 45 retained enforcing GSI ADB on boot
`04f2a639-9633-4859-a3d0-da172d7693da`. The native REFGEN provider binds,
but the first DCS command and advancing-frame check still fail. The successful
panel-transfer return path remains untested because DMA still times out.
No additional screen observation or cold-start/fault test was requested.
[Trial 45 evidence](../build/device/m3-display-45-2026-11-15.json).

The bounded trace shows PLL preparation during `of_clk_add_hw_provider()`:
first temporary parent enable, then `__clk_core_update_orphan_hold_state()`
retaining the DSI0 byte/pixel sources and branches. At 31.175 seconds the PLL
control is 1 and lock status is 0x51. `msm_dsi_host_reset_phy()` runs at
33.369 seconds. At PHY enable, software `pll_on=1` and bias references remain
1, while physical PLL control and lock are both zero. PHY configuration and
rate changes leave PLL control zero, and existing CCF references prevent a
fresh prepare call. This is a measured mismatch, independent of REFGEN.

The next candidate gives only six DSI0 clocks the native
`CLK_DONT_HOLD_STATE` flag: byte source/divider/branch/interface and pixel
source/branch. This project resets the DSI PHY and does not implement
continuous splash handoff. Other display clock chains retain their flags.
The flag prevents creating boot-held references; it does not manually edit
CCF counters or write PLL registers. The next trial must demonstrate zero
references before modeset, a new post-reset PLL lock and successful DCS/frame
progress. This candidate is not yet a hardware pass.


Pinned-source inspection explains the otherwise surprising CCF hold:
DISPCC registers its GDSC through `of_genpd_add_provider_onecell()`, which
installs `genpd_sync_state` on the provider driver. ACK CCF treats the presence
of that callback as a reason to preserve boot clock state. That callback
synchronizes power domains, without calling `clk_sync_state()`. The physical
orphan-hold stacks and persistent references match this source interaction.
The next kernel is run `43688126825` at `25ca13ba7c3a180862eba6a2f75c0ba8b05ac465`.


### Trial 46: first confirmed physical color bars

Kernel run `43688126825` completed all 788 actions; selected source and image
hashes were verified before installation. The GSI, project vendor and writable
test-volume seeds remain unchanged. Boot `a4da9689-cea2-48a0-869c-585973f1c035`
shows zero DSI0 prepare/enable references before modeset. At PHY enable the
software PLL state and bias count are both zero. After the reset, a fresh prepare
at 33.438 seconds sets PLL control to 1 and lock status to 0x51.

The panel reports successful prepare and display-on. The KMS probe obtains four
advancing sequence/timestamp pairs: 7/34.597659, 12/35.598416, 17/36.599101 and
22/37.599771. No RCG-update, DMA-command or frame-completion error appears in the
display evidence. The operator independently reports: "短暂出现了彩条"
(brief color bars appeared). The previous orphan-held clock stack is absent.
This establishes real native DPU/DSI panel output, rather than ioctl success
alone. The probe intentionally releases its buffers and display before Android.

GSI ADB returns, but the unchanged vendor still lacks EGL and SurfaceFlinger
restarts. The next objective is to install the verified source graphics payload,
validate allocator/composer registration and real EGL buffer rendering, then
reach stable SurfaceFlinger and Launcher. The initial mode does not establish
sustained refresh rate, brightness-range qualification, Adreno or real touch.
[Trial 46 evidence](../build/device/m3-display-46-2026-11-15.json).


The corrected graphics run `43682875528` has now completed compilation and
packaging. Artifact `14153035910` contains 44 verified files, 40,252,275 payload
bytes, and 8,455 dependency commands with zero missing edges. The importer
verified the complete archive SHA-256, payload inventory, source revision and
pinned HardwareBuffer declarations. Its eight external library names exist in
the active GSI; actual symbol loading and SELinux access still need the next
trial. Composing this payload with the established Keymaster/USB vendor requires
a 60 MiB unsigned filesystem. Trial 47 will reuse the proven trial 46 kernel,
GSI and scratch seeds, and install the newly signed project graphics vendor.
