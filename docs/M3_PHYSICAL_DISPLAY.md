# M3: physical display on the 6.18 GSI

The current objective is physical panel output, then a running SurfaceFlinger
and AOSP Launcher on the same Android 17 GSI. Cold-start and watchdog rehearsals
are not part of this work. Each stage report identifies its objective, physical
result, next blocker and source/evidence commit.

Current result (trial 63, November 16): native SSPP hardware-generated red,
green and blue still show strip noise and missing regions, with zero source
addresses/strides verified. Framebuffer fetching is not required to reproduce
this corruption. Android 17 returns with enforcing, SurfaceFlinger and ADB;
the physical image and desktop remain unaccepted. The user ended today's
session. Next resume the post-fill DPU/DSC/DSI/panel path. See the
[experiment and actual observations](M3_DPU_SOLID_FILL_ISOLATION.md#trial-63-result).

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
packets in the generated reference table. The runtime panel path replaces only
the runtime `0x9e` PPS payload with the host encoder's calculated parameters;
trial 55 verified the host-side change, but physical corruption remained.
The filename says 2340; the selected
mode actually specifies 1080x2400.
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
Trial 61 identifies the actual Android scanout as linear ABGR8888 with pitch
4352; physical presentation remains corrupted. Allocation length and runtime
Android DPU readback remain open.

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


### Trial 47: graphics vendor exposes a Keymaster loader regression

The 61 MiB signed graphics vendor passed complete storage readback, AVB and
first-stage mounting. The operator saw a brief flashing color screen, then
black. Native panel prepare/display-on still complete; KMS event details were
not collected before rollback, and no Android interface is confirmed.
GSI ADB did not enumerate. The existing guard expired and automatically returned
to diagnostics/EDL, preserving console and pmsg evidence. Original F.20 boot,
both LP metadata slots and the complete original super digest were restored and
verified. This recovery followed a real startup failure; no fault was injected.

The recovered console repeatedly shows the project Keymaster exiting with
status 1 while vold waits for android.security.maintenance. The secure domain
transition denies noatsecure. Graphics staging moved the eight accepted VNDK
runtime libraries into /vendor/lib64/rmx-keymaster and relied on an init
LD_LIBRARY_PATH setting. The pinned Android 17 Bionic linker ignores that
variable under AT_SECURE. This supports the loader-path diagnosis; the direct
linker stderr text did not survive the ring buffer. This is not evidence of a
new TEE transaction failure.

The next source HAL/client use DT_RUNPATH for that immutable vendor directory.
Because RUNPATH is not transitive, all eight existing private libraries are
explicit direct DT_NEEDED dependencies. Bionic searches a parent's RUNPATH
before namespace default directories and processes the executable's direct
load tasks before appended indirect tasks. The init environment workaround is
removed. Neither SELinux policy nor the library bytes are changed. A baseline
rebuild reproduced both previous executable hashes exactly; the new binaries
pass ELF RUNPATH and dependency-closure checks. Hardware validation remains
pending. [Trial 47](../build/device/m3-display-47-2026-11-15.json) and
[source link proof](../build/device/m3-keymaster-runtime-2026-11-15.json).

Pinned linker source: [environment handling](https://android.googlesource.com/platform/bionic/+/06356e41c5ed7b12220b24c05ba4fdb873b126a7/linker/linker_main.cpp)
and [library resolution](https://android.googlesource.com/platform/bionic/+/06356e41c5ed7b12220b24c05ba4fdb873b126a7/linker/linker.cpp).

### Trial 48: Keymaster restored; allocator blocked by device labels

Boot `10daf3a7-41a4-4f66-b345-a86eed9ab0cd` runs API 37 on 6.18.32 under
enforcing. The private-runtime source fix restores the Keymaster process in
`rmx_keymaster`, maintenance registration and retained GSI ADB. Direct HMAC and
earlyBootEnded log lines have rolled out of the collected ring, so this record
does not independently re-claim those calls. The source composer service is
registered. Native panel commands and four advancing frame events pass; the
operator reports flashing color bars after the realme logo, then black.

SurfaceFlinger loads the new graphics libraries but cannot obtain the allocator.
Both `/dev/dri/card0` and `renderD128` have correct system/graphics ownership and
0660 permissions, but carry `u:object_r:device:s0`. Enforcing denies allocator
read/write access. Its repeated exits also trigger SurfaceFlinger restarts.
No registered SurfaceFlinger service, working Android frame or desktop is claimed.

The next candidate adds only the two DRM node patterns to vendor file contexts
with `gpu_device`. Existing allocator/composer policy already grants access to
that type; the composed CIL hash remains identical to the strict-compile proof.
There is no broad permission for generic devices and no permissive-mode change.
Pinned Android 17 ueventd relabels existing nodes when coldboot encounters
EEXIST, so the nodes created by the early diagnostic are covered too.
The next objective is allocator registration, real EGL buffer rendering and
stable SurfaceFlinger, then the AOSP launcher. No manual cold-start or watchdog
fault-injection test was run. [Trial 48](../build/device/m3-display-48-2026-11-15.json)
and [pinned ueventd](https://android.googlesource.com/platform/system/core/+/545d2487e38192a2ce25040897ced877cf6b4f53/init/devices.cpp).

### Trial 49: allocator registered; native mapper discovery denied

Boot `f35092d2-e241-44db-875c-7ffc871e0428` confirms both DRM nodes now carry
`gpu_device`. The source minigbm allocator and DRM HWC3 services register and
remain alive under enforcing. Native panel commands and advancing KMS events
still pass; no separate physical-screen observation was collected for this trial.
GSI ADB returns. The early log also preserves the source Keymaster registration,
TEE hardware information, HMAC status 0 and successful TEE earlyBootEnded.

SurfaceFlinger now aborts with `gralloc-mapper is missing`. The preceding error
is servicemanager denying `find` for `mapper/minigbm`, which has fallen back to
`default_android_service`. The real mapper ELF, labeled `same_process_hal_file`,
and its native VINTF 5.0 entry are present. The shell-domain buffer diagnostic
independently reaches the same mapper error and exits 134 before EGL initialization.
This is not a rendered-buffer success.

The next candidate provides `mapper/minigbm` as `hal_graphics_mapper_service`
in vendor service contexts and labels the context file
`vendor_service_contexts_file`. Both types and the allocator-client discovery
allow already exist in the actual GSI policy; composed CIL remains byte-identical
to the strict proof. SurfaceFlinger's captured stack uses the GSI's bundled
ANGLE library; the packaged source vendor ANGLE is not claimed as its loaded
implementation. Initial rendering still targets SwiftShader, with no Adreno
acceleration claim. Next: get beyond mapper discovery, verify a real rendered
HardwareBuffer and stabilize Android composition. [Trial 49](../build/device/m3-display-49-2026-11-15.json).

### Trial 50: GLES initializes; composer hotplug socket denied

Boot `3d762fed-d1c8-4f55-93b3-faa06fcfe5d4` validates native mapper discovery.
SurfaceFlinger reports OpenGL ES 3.1 using GSI ANGLE and the source SwiftShader
driver. The allocator remains registered under enforcing. Composer reaches
client creation, but its `NETLINK_KOBJECT_UEVENT` socket is denied at creation.
Cleanup then faults in `UEventListener::StopThread`; SurfaceFlinger aborts with
`Can't create AidlComposerClient`. No registered SurfaceFlinger or Android frame
is claimed. GSI ADB is retained, and native panel/frame-event checks still pass.

The separate shell diagnostic now initializes EGL 1.5/GLES 3.1, but its
in-process minigbm mapper cannot open either DRM node. Shell lacks their
system/graphics DAC identity; direct opens return permission denied. The log
identifies buffer import with an uninitialized client driver, and the smoke
returns allocation status 5. This is a diagnostic-domain limitation, not proof
of the same failure in SurfaceFlinger. No buffer pixels passed verification.

The next policy change grants only composer self socket create/bind/read,
matching the actual pinned `utils/UEvent.h` implementation. It adds no network
capability or message-send permission. The observed cleanup bug is a separate
upstream robustness issue; the immediate device integration must permit the
hotplug listener's normal initialization. Validate the new strict policy,
then continue with composer display discovery and actual Android composition.
[Trial 50](../build/device/m3-display-50-2026-11-15.json) ·
[UEvent source](https://android.googlesource.com/platform/external/drm_hwcomposer/+/87daba89b05fabc7f1e9316e3f283f19fd0c45cd/utils/UEvent.h) ·
[Listener cleanup](https://android.googlesource.com/platform/external/drm_hwcomposer/+/87daba89b05fabc7f1e9316e3f283f19fd0c45cd/drm/UEventListener.cpp).

The updated combined policy passed the actual GSI compiler with neverallow
checks enabled on trial 50. Compiled digest:
`6dafb8272f54804fae1f30efd6378d5ec8b34403bd9f7863b0830a3829f96ed7`.
This was an isolated compile; the running phone's policy was not replaced.

### Trial 51: composer client created; allocator-client role missing

Boot `fd7c0a70-1df7-436f-af35-6d80bdaf5a52` resolves the hotplug socket failure.
SurfaceFlinger initializes GLES 3.1 and logs `Loaded AIDL composer3 HAL service`.
Composer then reaches mapper setup, where servicemanager denies discovery of
`android.hardware.graphics.allocator.IAllocator/default` to
`rmx_graphics_composer`. It subsequently aborts with `gralloc-mapper is missing`.
The allocator remains registered and enforcing GSI ADB remains available, but
SurfaceFlinger has no registered service and no Android frame is confirmed.

The next change applies the actual Android 17 full-Treble
`hal_client_domain(rmx_graphics_composer, hal_graphics_allocator)` expansion:
client-domain membership, the allocator-client attribute, and the macro's
scoped bidirectional memfd mapping permissions. Existing platform policy then
supplies allocator/mapper discovery and Binder/FD transfer rules. This uses the
standard HAL client role instead of adding isolated service-manager allows.
The non-Treble passthrough rules do not apply. Strict compilation is required
before packaging. [Trial 51](../build/device/m3-display-51-2026-11-15.json) ·
[Pinned client macro](https://android.googlesource.com/platform/system/sepolicy/+/e066568e98d86db31a9346d30977f3632fa7073c/public/te_macros).

The full client-role expansion passed strict compilation on this retained GSI,
with neverallow checks enabled. Compiled policy digest:
`45d8ca9b6c6cf9da9c916274cc7d99607f3855a4227dee4815e24b3a9f9e29e2`.
The running policy was unchanged; the next signed vendor carries the update.

### Trial 52: real display attached; SwiftShader JIT execution denied

Boot `bbe2e856-3f30-4791-ab0c-4c7300999fe2` validates the allocator-client role.
DRM HWC discovers `DSI-1`, chooses the generic MSM backend and attaches the
pipeline as primary display 0. SurfaceFlinger connects the physical display,
completes power mode ON and reaches boot-animation startup. Composer and
allocator remain available under enforcing, alongside GSI ADB.

SurfaceFlinger subsequently receives `execmem` denials and SIGSEGV/SEGV_ACCERR.
Its crash reports execution of non-executable memory at `[anon:swiftshader_jit]`,
called by the source `vulkan.pastel.so` DrawCall worker. BootAnimation also
receives `execmem` denial. Thus the renderer initializes, but its generated
shader code cannot run; a persistent Android frame or desktop is not claimed.
The separate backlight-class read denial leaves Android brightness control
unverified and does not explain this instruction fault.

The next engineering CPU-rendering profile adds JIT execution permission only
for `surfaceflinger` and `bootanim`, the two observed clients. These are real
per-domain execution exceptions, not a claim of unchanged security policy.
Enforcing and strict neverallow compilation remain required. No domain-wide or
system_server execmem exception is added. Remove the two exceptions when the
hardware renderer replaces this CPU profile. [Trial 52](../build/device/m3-display-52-2026-11-15.json).

The two-domain JIT policy passed the GSI's strict compiler with neverallow
checks enabled; compiled digest:
`2afd651ded35829e53678f56b2837dc7b4af970331cf64fecc424679b028191d`.
This compile did not load or weaken the running policy. Runtime validation of
the new per-domain permissions belongs to the next candidate.

### Trial 53: SurfaceFlinger stable; sustained corrupted physical output

Boot `540e191d-b8ec-4539-b53e-98f9760d3b19` validates the two JIT permissions.
SurfaceFlinger PID 2032, composer PID 2027 and allocator PID 2026 stay available
under enforcing. The active physical mode is 1080x2400, and BootAnimation submits
DEVICE-composed frames with an identity display transform. This is not measured
refresh-rate or correct-image validation: the operator explicitly reports
"目前屏幕稳定在花屏" (sustained corrupted output).

SystemServer separately crashes starting BatteryService because no IHealth
default instance is available. Launcher and boot completion have not passed.
The fixed 512 MiB test data filesystem is also nearly full; capacity must be
reassessed before desktop acceptance, without touching stock userdata.

The shell screenshot attempt returns zero but no image. Its captured minigbm
import failure follows inability to initialize the DRM driver, matching the
previously established shell DAC limitation. The next candidate adds a fixed
one-shot screenshot process with shell UID and supplementary graphics group.
It uses existing platform executables and shell SELinux permissions, has a
40-second service timeout, and only writes its capture and status under
`/data/local/tmp`. Adbd and DRM device modes are unchanged. This is intended to
separate composed-image corruption from downstream scanout corruption before
choosing a fix. No valid Android frame is claimed. [Trial 53](../build/device/m3-display-53-2026-11-15.json).

### Encoder/decoder DSC parameter mismatch found during trial 54 preparation

The imported OEM DCS `0x9e` packet programs the panel decoder with fixed
downstream rate-control values. ACK's `dsi_populate_dsc_params()` instead calls
`drm_dsc_setup_rc_params(..., DRM_DSC_1_1_PRE_SCR)` for the DPU encoder. At 8 bpc
and 8 bpp, the encoder table sets first_line_bpg_offset to 12; the panel's fixed
PPS byte 27 is 15. The fixed rate-control ranges also differ. Thus copying the
OEM packet byte-for-byte does not keep the 6.18 encoder and decoder consistent.

The prepared panel fix packs the already calculated host DSC configuration at
panel prepare. It retains the original DCS long-write type, vendor command
`0x9e` and 88-byte DSC 1.1 payload length. It rejects an unpopulated configuration
and logs the accepted PPS prefix (the kernel hex formatter limits it to 64 bytes). The generated OEM table remains unchanged for
comparison. This is a source-level mismatch and a candidate repair, not yet a
hardware-verified explanation of trial 53's corruption. Trial 54 still runs
kernel 27 and only adds the one-shot screenshot; the new kernel requires its
own build and handset validation.

The exact ACK helper functions and tables were built as a pure arithmetic
ARM64 probe using `scripts/build/build_dsc_reference.py` and run on the retained
trial 54 GSI. All source inputs and the executable were hash-checked. The first
88 bytes differ from the factory decoder PPS at 13 offsets, including initial
decode delay 526 versus 594 and first-line BPG offset 12 versus 15. This is
calculated configuration, not a register read. [Full comparison](../build/device/m3-dsc-pps-reference-2026-11-15.json).

### Trial 54: screenshot launch error; graphics services still stable

Boot `61647569-b8be-4d1b-a02e-3bfc0493492e` retains enforcing GSI ADB and all three
graphics services. The screenshot process failed before exec: the init child
SIGABRTs at uptime 77.231 seconds and produces no capture files. The pinned init
argument expander rejects the unescaped shell `$?` as property syntax and calls
LOG(FATAL). The next recipe uses `$$?`, which init expands to a literal `$?` for
the shell. The resulting command passes the GSI shell syntax check; runtime
capture is still unverified. No policy or DRM device-mode change is required.

Kernel build 28 did not compile: its dispatch incorrectly enabled both legacy
and source PON options. Build 29 corrects that to source PON only, matching the
accepted device configuration. Neither failed build nor the prepared PPS fix
was flashed in trial 54. Next: verify the newly built panel driver and capture
actual composed pixels on the same boot, then return to the missing Health HAL
desktop blocker. [Trial 54](../build/device/m3-display-54-2026-11-15.json).

### Trial 55: PPS correction accepted; physical corruption remains

Boot `22228212-45b7-4e4b-bc67-219da87e60a5` runs verified kernel build 29.
The panel logs a 64-byte accepted PPS prefix matching the pinned helper
calculation (the kernel hex formatter caps the requested dump). That is a
pre-Android command witness, not a complete hardware encoder register dump.
The operator explicitly reports **仍然花屏**. The DSC correction is therefore
not sufficient to establish correct physical output.

SurfaceFlinger, composer, allocator and GSI ADB remain alive under enforcing.
The corrected fixed capture runs as shell with supplementary graphics but
times out after 20 seconds and produces no PNG. Early SurfaceFlinger logs show
a captureDisplayById transaction lasting 28.425 seconds and a dead reply after
the client timeout. A bounded same-UID probe of a separate ordinary-shell
screencap child finds the main thread waiting on a libc++ future, with its
binder thread in the thread pool. It has not reached pixel locking at the
sampled point. Ordinary shell lacks the service's graphics group, so this
probe alone cannot validate buffer import. The child is reaped and the
diagnostic executable removed; no root, policy change or reboot is used.

Next: resolve capture completion and compare actual Android pixels with the
physical image before choosing another DSI change. The missing Health HAL
remains the separately recorded SystemServer/desktop blocker. No cold-start
or watchdog fault-injection test was run. [Trial 55](../build/device/m3-display-55-2026-11-15.json).

Follow-up callback logs for ordinary-shell PIDs 6235 and 6758 show
`GraphicBufferMapper importBuffer` failing with 5; the one-way callback is
discarded before the future is fulfilled. A 90-second ordinary-shell capture
still yields no bytes. This explains that diagnostic wait, not the physical
corruption, and does not duplicate the graphics-group service's credentials.
The next candidate gives that fixed service 90 seconds and captures to stdout,
avoiding screencap's filename-triggered media-scanner broadcast while
ActivityManager is unavailable. `debug.rmx.m3.capture=1` retries only this fixed
service without a reboot or USB change. The expanded command passes GSI `sh -n`.
Kernel 29, graphics payload, GSI, test seeds and policy stay unchanged.

The bounded `scripts/device_audit/capture_wait_probe.c` was built using NDK
28.2.13676358, `aarch64-linux-android35-clang -O2 -Wall -Wextra -Werror`.
It executes only `/system/bin/screencap -p`, samples that same-UID child's
threads after three seconds, then reaps it; a 15-second alarm bounds failure.
It is an on-host-invoked diagnostic, not installed as a privileged service.

### Trial 56: repeatable black screenshots, physical corruption persists

Boot `449ec599-2f61-4559-8cad-4ce57c722e4a` retains the same kernel 29,
graphics payload, GSI, board trees and scratch seeds. Only the fixed capture
recipe changes. The first capture succeeds after 37.22 seconds, and a
`debug.rmx.m3.capture=1` retry on the same boot succeeds after 1.56 seconds.
Both return zero and produce the same 15,580-byte PNG. Full PNG decoding gives
1080x2400 RGBA, all 2,592,000 pixels exactly `(0,0,0,255)`.

The operator again reports **仍然花屏**. These are CPU-composited screenshots,
not DPU readback, and black output does not establish correct nonblack
rendering. GSI BootAnimation stays alive and presents buffers; it logs no
animation archive and uses its fallback. Both fallback logo assets exist in
the actual framework-res.apk. The hardware acceptance remains failed.

Next: use BootAnimation's existing `/oem/media/bootanimation.zip` input for a
deterministic project diagnostic pattern, compare actual screenshot pixels
and physical output, then choose the next graphics/DSI fix. Kernel 29 and the
source graphics payload stay fixed for that comparison. Missing Health HAL
is still the separately recorded SystemServer blocker. No cold-start or
watchdog fault injection was run. [Trial 56](../build/device/m3-display-56-2026-11-15.json).

### Known-color BootAnimation input prepared for trial 57

The project generates a 1080x2400 static six-color pattern with a white border,
top band and asymmetric top-left marker. Two identical frames at 1 fps avoid
intentional flashing. The ZIP contains stored entries as required by the
pinned GSI BootAnimation parser. PNG decoding, primary/secondary color samples,
orientation markers and repeatable archive generation pass locally.

The verified read-only vendor subtree `/vendor/etc/rmx-m3-oem` is bound onto
the existing empty `/oem` at post-fs. It supplies the standard
`/oem/media/bootanimation.zip` input without modifying the GSI. OEM directory
and animation labels use existing platform BootAnimation read rules; the only
new rule permits vendor_init to mount that OEM directory. An attempted custom
vendor-file read was rejected by the Treble neverallow and removed. Strict
compilation now passes with neverallows enabled; no compiled policy is loaded
into the running trial 56. This temporary mount is an engineering diagnostic,
not a release partition layout or VTS file-context result. Remove it after
pixel isolation. Runtime loading and correct physical pixels remain untested.
[Input validation](../build/device/m3-bootpattern-input-2026-11-15.json).

The first local pattern package was rejected before any handset write: the
vendor builder normalized CRLF in every non-ELF file, corrupting the animation
archive. Only that new ZIP differed from the source inventory. The builder now
normalizes known text formats only, and the verifier uses the same rule for
baseline text inputs. Regression checks cover stored ZIP CRC/content, unknown
binary public-key bytes and existing init text normalization. The full image
readback/hash verification remains mandatory during the next build.

### Trial 57: archive validated, mount denied before rendering

Boot `e7debf6c-7e25-42f3-9c0d-818c8b9ff8ea` retains GSI ADB,
SurfaceFlinger, source composer and allocator under enforcing. Rebuilt vendor
archive bytes and ZIP CRC pass, followed by full candidate UFS readback.
However, at 64.487 seconds init is denied `oemfs:dir mounton` on `/oem`.
The grant prepared above targeted vendor_init incorrectly. The pinned init
builtin table marks mount as not running in the vendor subcontext, matching
the observed `u:r:init:s0` denial. No pattern archive loads; BootAnimation logs
`No animation file`. The capture succeeds in 37.13 seconds and is byte-identical
to trial 56's black PNG. No new physical observation was requested because
the intended comparison was blocked before rendering.

The next candidate replaces the ineffective grant with only
`(allow init oemfs (dir (mounton)))`. Strict compilation with neverallows and
on-device archive loading remain required. Kernel 29, graphics binaries,
GSI and scratch seeds stay fixed; DSC packet changes are deferred until
the known-color comparison. Missing Health HAL still blocks SystemServer.
No cold-start or watchdog fault injection is run.
[Trial 57](../build/device/m3-display-57-2026-11-15.json).

The corrected rule passes strict compilation on retained trial 57 with all
neverallows enabled. Compiled policy SHA-256:
`60c1de23837e7dc1789f9dc1aecb29da0f97d0c4d56c6f6e58887e60a288f22e`.
It was not loaded into the running device; trial 58 will validate startup.

### Trial 58: known CPU pixels, corrected physical mismatch

Boot `7d750f14-c07c-4145-b9c5-5305af9c83f1` runs the same kernel 29,
graphics payload, GSI and scratch seeds. Only the OEM mount permission is
corrected. Mountinfo shows the vendor subtree bound read-only at `/oem`;
BootAnimation explicitly loads the archive at 77.974 seconds and plays part0.
The fixed graphics-group capture completes in 36.91 seconds, producing a
16,038-byte 1080x2400 RGBA PNG. Its complete six-color pattern and orientation
markers are visible. Of 2,592,000 pixels, 2,584,196 match the source exactly;
the other 7,804 differ by at most 5/255 per channel, all near reference edges.
The small differences' origin is not established. This is CPU composition,
not a DPU scanout readback.

The operator first reports regular color bars, then visible black/white
markers, but explicitly corrects: **不对不对，和你截图的不一样！** The assistant's
premature display-pass statement was withdrawn. The current result is
**physical mismatch; full display acceptance NOT PASSED**, pending a more
specific description. Do not silently promote partial shape recognition to
matching output or desktop readiness. Health HAL work remains deferred.

The new read-only `collect_android_frame.py` verifies boot identity, completed
capture status, file size, full PNG decode and optional decoded-pixel reference.
Only one completed capture is counted here. A later host retry precondition
check rejected an empty service-state property before triggering anything;
the subsequent collector re-read the same file, not a second capture.

Next: use this loaded known pattern to isolate scanout/DSI differences.
The factory two-slices-per-packet setting and later upstream support are
source candidates, not an established root cause or applied fix. No cold-start
or watchdog fault injection is run. GSI ADB remains available.
[Trial 58](../build/device/m3-display-58-2026-11-15.json).

The subsequent original photograph (`70d6083bf9ea734b39275b504fe2ffd1d888bcd65e9cd16771b28fa465b556c4`)
confirms severe corruption: intact horizontal color/marker bands alternate
with dense noisy regions. This is now a confirmed physical failure, not a
pending visual comparison. Original image bytes stay in the local trial
record; the public JSON records its digest and observation. Photo-space red
band centers are about 242–251 pixels apart; perspective is not calibrated,
so no exact panel scanline period or DSC cause is claimed from that count.

### Next transport candidate: two DSC slices per packet

The locked factory `20607` RM19795 timing@0 source explicitly sets
`qcom,mdss-dsc-slice-per-pkt = <2>` (line 77); ACK 6.18 currently fixes this
at one slice per packet. Backport upstream `ffa88de8ddb64` (mode flag) and
`ce73a5db44e3` (MSM host support), preserving original authors and sign-offs.
The latter requires only two trailing context lines to match the older ACK
attach function; its added/removed code is unchanged. Enable the flag only
in the project RM19795 panel, whose two slices are initialized before attach.

For 540-byte chunks this changes packet count per line from two to one and
command word count from 541 to 1081. A bounded modeset witness reads back
compression and stream registers after their existing writes. The existing
clock patch, both upstream patches and trace patch apply together to the
pinned source. CI must compile them, and artifact import must verify all
three additional source digests. Source application is not hardware success.

Keep the trial 58 pattern and graphics payload fixed. No PPS, clock, DPU RC
table or Health HAL change is mixed into this candidate. The physical photo
supports investigating the transfer path, but does not prove this packet
mismatch is the cause. [Source check](../build/device/m3-dsc-packet-backport-2026-11-15.json).

### Trial 59: packet change applied, physical corruption unchanged

Kernel build 30 passed and its selected artifact members and source manifests
were verified. Boot `ec0f3713-797f-4339-95c8-8947213842ee` uses that kernel with
the same GSI, vendor, pattern and scratch seeds as trial 58. Full super readback
passed before the boot-only replacement; boot and paired DTBO readback passed.
Android 17 ADB, enforcing and graphics services are retained.

The pre-Android modeset trace at 33.377991 seconds reports:

```text
RMXDSC packet slices=2 per_pkt=2 chunk=540 clk_width=360 compression=0x39003901 compression2=0x21c stream=0x4390039 total=0x9600168
```

The pinned register XML decodes stream0 compression enabled, type `0x39`,
one packet per line, chunk 540, word count 1081 and stream dimensions
360 clocks by 2400 lines. This proves the intended packet programming occurred;
it is not a live Android DPU readback. The fixed capture takes 37.81 seconds
and produces the same 16,038-byte PNG and SHA-256 as trial 58.

The operator explicitly reports **实际显示没有变化，还是和之前发的照片一样**.
There is no new photograph for trial 59; the comparison refers to the saved
trial 58 photo. **Physical acceptance FAILED.** Two-slice packet support is
insufficient to fix the fault and is not established as its root cause.

Next: obtain actual DPU DSC, pixel-format and pitch programming before another
hardware configuration change. Keep the known pattern and defer Health HAL.
No cold-start or watchdog fault-injection test was run. The phone stays in GSI.
[Trial 59](../build/device/m3-display-59-2026-11-15.json) ·
[Kernel build](../build/device/m3-dsc-packet-kernel-build-2026-11-15.json).

### Trial 60 measurement candidate: existing kernel snapshot

The pinned MSM driver exposes read-only `dri/0/kms`, which takes the display
snapshot mutex, captures DSI and DPU with their runtime-PM references, and
copies atomic state. The DPU snapshot includes the DSC and SSPP register banks.
The running GSI shell has no mounted debugfs; no policy or shell privilege
change is needed. Extend the existing pre-policy native KMS probe to read
`kms`, `state` and `fb` after four advancing flips, before disabling its CRTC.
The read limits total 640 KiB, below the witness publication limit. The existing
15-second whole-probe timeout remains. Compilation with NDK 28 and
`-Wall -Wextra -Werror` passes. Runtime collection is pending.

This is a measurement-only ramdisk change: retain kernel 30 and the same
GSI/vendor/test seeds. It will describe native KMS, not prove the Android
scanout state or correct physical output. No visual improvement is expected
from adding this reader. [Source and build checks](../build/device/m3-display-snapshot-probe-2026-11-15.json).

### Trial 60 result: native configuration read back, Android comparison open

Boot `205712fa-efd4-4d0c-ab13-53913bd96b24` retains the exact kernel 30,
GSI/vendor/pattern, DTBO/effective tree and scratch seeds. Only the pre-policy
probe gains the reader. Full container, new boot and paired DTBO readbacks pass.
The reader finishes before Android with complete `kms` (152,976 bytes),
`state` (3,436) and `fb` (454) payloads. None hits its cap or reports a read
error. The native KMS probe exits zero and GSI ADB/graphics remain available.

Both `dsc_0` and `dsc_1` read back the calculated PPS parameters: 1080x2400,
540x48 slices, chunk 540, 8 bpc/8 bpp, delay 512/526, the buffer thresholds
and all 15 rate-control ranges. All decoded shared PPS fields match the
pinned-helper reference. Common mode is 3, initial lines 3 and last group 2.
This comparison does not read the panel's internal decoder registers.

Atomic state selects native framebuffer 91, XRGB8888, linear modifier, on
`sspp_0`. Its 4352-byte pitch equals the actual SSPP stride; source/output
dimensions are 1080x2400 and UBWC is off. DSI stream/compression values agree
with trial 59. These are native pre-Android measurements, **not evidence that
the later Android buffer uses the same pitch/offset/format**. Nonzero unused
register banks can contain stale state; active attribution uses atomic state.

A new Android CPU capture completes in 38.63 seconds and is byte-identical
to the published trial 59 PNG. No new physical observation was requested for
this measurement-only run. The last explicit operator report, trial 59,
remains unchanged corruption. No physical fix or desktop acceptance is claimed.

Next: capture the actual BootAnimation framebuffer/plane at Android's first
commit and compare its pitch, offset, format and synchronization with native
KMS and DPU readback. The SurfaceFlinger dump shows DEVICE composition; its
separate FramebufferSurface allocation is not a substitute for the directly
scanned BootAnimation buffer's metadata. Do not change PPS or clocks without
new evidence. Health HAL remains deferred; no cold-start or fault injection.
[Trial 60](../build/device/m3-display-60-2026-11-15.json).

### Trial 61 preparation: identical row-sensitive native and Android input

Follow the user's [November 16 diagnosis](M3_DISPLAY_DIAGNOSIS_2026-11-16.md).
Keep kernel 30, effective DTB/DTBO, source graphics libraries, GSI, DSC PPS,
clocks and scratch seed images fixed. Replace the diagnostic pattern with
`m3-row-grid-v2`: the same 1080x2400 RGB888 pixels produce the ramdisk input
and both BootAnimation PNG frames. A pixel-equality test independently decodes
the PNG payload and checks its CRCs, labels, horizontal rules and asymmetric
top/bottom. Native KMS explicitly converts RGB to XRGB using the returned
pitch and validates allocation bounds. Both native buffers contain this image.

After four flips and the existing native hardware snapshot, hold for 30 seconds
and then disable the CRTC and destroy buffers before Android handoff. Increase
the whole native-probe timeout from 15 to 50 seconds. The host's existing
180-second fallback is unchanged; attach the staged observer before reboot.
Do not leave the diagnostic gate waiting while building the candidate.

Add a separate static ARM64 read-only Android DRM metadata probe. It queries
active plane/FB bindings, GETFB2 format/modifier/pitch/offset, and plane properties
at two bounded samples. It records boot ID and CLOCK_BOOTTIME, rereads the
binding, and explicitly reports allocation length as unknown. Per-fd universal
and atomic caps expose properties only; there are no modeset, master, PRIME
or mapping operations. This does **not** yet capture Android DPU registers,
mapped addresses, acquire fences or allocation lifetime, and binding rereads
do not provide an atomic HWC-commit snapshot.

Run the fixed probe in its own SELinux domain and write only its vendor
diagnostic directory. Give shell read access to that output, without changing
ADB groups, DRM node modes, or enforcing. Strict policy compilation retains
neverallow checks. The initial draft targeting shell_data_file was rejected;
that policy was never loaded and is not used by the candidate.

Preparation is not a physical pass. Observe both native and Android screens;
retain their separate outcomes, actual scanout samples and CPU capture before
choosing the next hardware or buffer experiment. Health HAL remains deferred.
No cold-start or watchdog fault-injection test is part of this experiment.

### Trial 61 result: corruption reproduced before Android

Boot `fd45d4f7-18ad-48b0-b5f8-9a6c53c6cbd2` executes recipe `aa899de`.
All 17 old and 17 new super segments and both boot/DTBO readback pairs match.
Kernel 30, effective DTB/DTBO, GSI, graphics libraries and scratch seeds remain
unchanged. GSI ADB and SurfaceFlinger run under enforcing; the phone is retained
in GSI. Activity/window services and the AOSP desktop remain unavailable.

**Both physical phases FAIL.** The operator explicitly reports the native
pattern already contains errors and supplies a photograph during its hold.
It shows extensive noise with narrow regions retaining colors and row labels.
For Android, the operator first says the overall appearance is similar, then
clarifies: “仍然是花屏，但是花屏的内容有所变化”. Preserve that distinction:
the two outputs are both corrupted, not established as pixel-identical.

The original native photograph remains local; its SHA-256 and observation are
recorded publicly. Visible label pairs include 042/043, 048/049 and 054/055.
These three readable groups are 144 input rows apart, or three 48-row DSC slices.
This is a limited visual lead, not proof of a global corruption period or DSC
root cause. Native hold begins at uptime 37.661 s; Android handoff is 70.284 s.

| Measurement | Native KMS | Live Android |
| --- | --- | --- |
| Active binding | plane 41 / CRTC 89 / FB 91 | plane 41 / CRTC 89 / FB 95 |
| Dimensions | 1080x2400 | 1080x2400 |
| Format / modifier | XRGB8888 / linear | ABGR8888 / linear |
| Pitch / offset | 4352 / 0 | 4352 / 0 |
| Allocation | 10,444,800 bytes | unknown to this reader |
| DPU registers | active SSPP stride 4352, UBWC off; both DSC banks match reference shared PPS fields | not captured |

The Android probe completes two 1.5 ms samples at uptime 115.138 and 120.140 s,
with unchanged bindings on reread. Source and destination rectangles are full
frame; rotation raw value 1, alpha 65535 and blend mode raw value 2. A queried
IN_FENCE_FD of -1 is not evidence that HWC failed to supply a fence: this is not
a submission trace. No allocation/import lifetime or runtime DPU address claim.

The 37.08-second CPU capture has 2,535,779 / 2,592,000 exact reference pixels
(97.83%); remaining channel differences are at most 5/255. It still does not
represent the physical output. The independent DRM query succeeds under the
new policy. A later shell `ls` lacks directory getattr permission, but reading
the intended diagnostic file succeeds; no permission broadening is needed.

The failure can now be reproduced without Android HWC. Prioritize the shared
DPU fetch, DSC/pingpong/merge, DSI and panel path; retain Android format and
reconfiguration differences as comparisons, rather than claiming they are
excluded. Next correlate active routing and packet/row boundaries against the
OEM 20607 configuration before choosing one parameter to change. Keep the
kernel/PPS/clocks baseline until that evidence exists. Health HAL is deferred.

[Trial 61 evidence](../build/device/m3-display-61-2026-11-16.json) ·
[Android CPU capture](../build/device/m3-display-61-android-frame.png) ·
[Reference pattern](../build/device/m3-row-grid-v2.png).


## Trial 62: single DSC still reproduces corruption

Current goal remains correct physical output, then the AOSP desktop. Kernel
build 31 and the opt-in single-DSC boot passed the controlled routing checks:
only DSC0 / PP0 / INTF1 are enabled, DSC split/multiplex is off, and PPS, DSI
packets, reported DSI rates, GSI/vendor, board trees and volume seeds are fixed.
The operator reports unchanged corruption in both native and Android phases.
Dual-encoder merge is therefore not required to reproduce the symptom.

GSI ADB and SurfaceFlinger remain available under enforcing; the same boot was
retained. The next isolation should bypass memory fetching using a controlled
DPU-generated pattern, or capture the hardware output before compression. No
physical display or desktop pass is claimed. [Detailed result and next scope](M3_DSC_TOPOLOGY_ISOLATION.md#trial-62-result).

### Trial 64: complete PPS and bounded panel-state readback

On November 18, the native and Android outputs both remain corrupted according
to the operator. The complete 88-byte host PPS agrees with sampled DSC0
parameters, and the panel power read returns the expected `0x9c`. Vendor PPS
readability is not established: the 16-byte response is zero and is recorded
as uninterpretable, not as decoder contents. CCF MDP is 200 MHz and DSI bit
clock 421.632 MHz; comparison with the factory DT's 660 MHz still requires
stock runtime evidence before attributing a clock defect. The selected F.20
on/enable/off/PHY arrays and 16 timing/DSC scalars match the official Q source.

Kernel 33 succeeds, all 17 device super chunks and boot/DTBO readbacks verify,
only boot is programmed, and enforcing GSI ADB is retained for the same boot
after 196.985 seconds. A host session interruption and a rejected local
candidate-byte mismatch are documented separately; neither is a display
result and no unverified candidate bytes were programmed. Root cause and
AOSP desktop acceptance remain unresolved. [Trial 64 details](M3_PANEL_READBACK_2026-11-18.md#trial-64-result-physical-corruption-persists).


## Trials 65–66: original clocks and original PPS do not repair physical output

The reviewed trial 65 snapshot confirms 660/82.5/110 MHz CCF clocks with the
previous DSC configuration. The operator subsequently confirmed corruption.
Trial 66 additionally matches both the encoder and transmitted 88-byte PPS to
the original panel payload. All 32 setup checks pass, yet native output has
“没有改善” and Android has “一样花屏”. GSI ADB passed 196.625 seconds under
enforcing, with graphics and maintenance registered and activity/window absent.

F.20 was restored after trial 66 and its boot/DTBO, all 17 super chunks, both
LP slots, full phone-side super digest and boot completion verified. The next
candidate tests three PHY timing fields against the original panel table;
this remains a hypothesis. No new cold-start or watchdog fault injection is
included. Staged display still needs host release on every boot.
[Trial 66](../build/device/m3-display-66-2026-11-20.json) ·
[DSC comparison](M3_STOCK_DSC_2026-11-20.md) ·
[PHY candidate](M3_STOCK_PHY_2026-11-20.md).


## Trial 67 paused by user

Build 36, candidate packaging and full device readback passed. The user
requested pause at the native observation prompt, so the physical result is
unreported and no repair is claimed. Further capture and testing stopped;
F.20 was restored and fully verified to avoid leaving the per-boot host gate
installed. Work was paused at that checkpoint. [Record](../build/device/m3-display-67-paused-2026-11-20.json).

## Trial 67 reviewed: physical corruption unchanged

On November 21 the user reported no improvement in trial 67, without separate
native/Android phase descriptions. Offline review authenticates the saved
snapshot against the published pause digests and host gate UUID; all 43 PHY,
PPS, clock, route and fixed-input checks pass. This is configuration evidence,
not GSI stability acceptance. The original PHY changes alone did not repair
the display. The root cause remains open.

SM8250 research and a pinned-source audit identify a missing first-frame error
history: the current snapshot masks several error IRQs, and normal error
handling clears status before later samples. Core-clock/transfer budgeting
and runtime PLL reprogramming remain hypotheses. First-frame evidence is the
next priority; no new flash, restart or image version was produced during
this review. [Investigation](M3_DISPLAY_RESEARCH_2026-11-21.md) and
[review record](../build/device/m3-display-67-reviewed-2026-11-21.json).

## Trial 68: first-frame trace complete, physical corruption unchanged

Build 38 succeeds. The instrumentation-only candidate passes 20 input checks
and 43 runtime configuration comparisons with the preceding setup. The
operator reports unchanged corruption in both native and Android phases.
Enforcing GSI ADB remains available for the 195.203-second check;
SurfaceFlinger and maintenance exist, but activity/window and desktop
acceptance remain absent.

All 230 exported events and eight CPU loss counters validate. Twelve boundary
samples do not report decoded DSI errors; no actual PLL reprogramming occurs
inside the 42 DCS transactions. MDP is already at 200 MHz before the first
kickoff. This lowers the priority of command-triggered PLL reprogramming for
this native failure; bounded samples and unchanged interrupt masks do not
exclude every transient fault or prove correct physical output.

F.20 is restored with boot completion and both LP slots matching. The user's
single-backup policy is now the default: verified local originals are reused,
without routine stock partition readback or a phone-side full-super digest.
The receipt separates expected image digests from unperformed observations.
The next investigation verifies actual stock command-log coverage and then
panel setup/PPS/DSC ordering; no cold-start repeats were performed.
[Trial 68 evidence and next scope](M3_FIRST_FRAME_TRACE_2026-11-21.md#第-68-轮真机结果).
