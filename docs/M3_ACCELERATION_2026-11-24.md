# M3 native Adreno and 90 Hz bring-up

The user resumed implementation on November 24, targeting hardware rendering,
90 Hz and CPU/GPU frequency control. Trial 83's working display, input, gauge,
GSI and RAM test-volume seeds remain the baseline. Cold-start repeats are outside
this task. The phone was on F.20 during build preparation; the first trial result is recorded below.

## Source and build checks

The [performance kernel build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/45389486854)
passed at `ead1ec19987eeb6b640374a8995709d11290aa34`. It enables native EPSS
CPUfreq, schedutil, TSENS and cooling support alongside the existing MSM driver.
The board's native GPU/GMU/GPUCC/SMMU nodes use pinned ACK SM8250 resources;
the effective OEM overlay passes UFS, USB, display, input, gauge and performance
resource checks. Native Adreno appears before the disabled legacy KGSL node,
which matters because ACK's component lookup only examines the first match.

F.20 reports `Adreno650v3`, but its effective DT chip ID is `0x06050002`.
The native compatible is therefore `qcom,adreno-650.2`. The six GPU OPPs are
305, 400, 441.6, 490, 525 and 587 MHz, capped at the measured stock maximum.
The board-specific secure ZAP reservation is retained at `0x8e21a000`.
[GPU firmware provenance](../build/device/m3-gpu-firmware-2026-11-24.json)
accounts for 88,576 bytes read once from F.20. These are explicit retained
peripheral-firmware dependencies, not Android HAL binaries.

The panel's 90 Hz command table is generated from the pinned official board
source. It retains the accepted standard PPS/DSC and 660 MHz transfer clock.
`panel_samsung_rm19795.refresh_rate=90` selects one 90 Hz mode for that boot;
dynamic 60/90 Hz switching is not implemented. The native probe now accepts
both modes and calculates observed vblank frequency from event counters and
timestamps. A mode declaration alone is not a 90 FPS result.

The new userspace route is retained source ANGLE EGL/GLES over source Turnip
Vulkan and native MSM DRM. Mesa is pinned to the Android 17 source commit in
[the build lock](../build/m3-turnip-source.json). Cross-build fixes are recorded
in GitHub Actions. [Build 45394293633](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/45394293633)
passed; its artifact digest, ARM64 ELF, SONAME and dependencies are verified.
The existing source-built `libcutils.so` and `libhardware.so` supply its Android
vendor dependencies. No new shared libdrm or C++ runtime is introduced.

The exact acceleration policy passed strict Android 17 `secilc` compilation
on the restored F.20 runtime, without loading policy or changing enforcing.
The acceleration profile removes the two SwiftShader-specific `execmem`
exceptions. [Policy proof](../build/device/m3-performance-policy-2026-11-24.json)
and [preflight result](../build/device/m3-performance-preflight-2026-11-24.json)
are build evidence only.

## Device acceptance still required

1. Bind native Adreno/GMU, load the inventoried firmware, and submit a Vulkan
   transfer with fence completion and CPU readback. The probe rejects software
   devices and checks all 1 MiB of GPU-written data.
2. Confirm SurfaceFlinger and application rendering identify Adreno, with no
   GPU/SMMU faults or service restart loop; retain GSI only with working ADB.
3. Measure 90 Hz vblank and Android presentation timestamps, then exercise the
   same Launcher/Settings scroll workload and report missed-frame distribution.
4. Observe CPU policies 0/4/7, schedutil frequency transitions, GPU devfreq and
   temperatures under load and after idle. Do not use fixed maximum clocks as
   a substitute for working control.

CPU capacity descriptions distinguish little from big cores. The initial
CPUfreq path uses the hardware LUT; CPU/L3 bandwidth control and Android Power
HAL hints still need measurement and integration. The initial TSENS cooling
trips are conservative bring-up values (80 C passive, 100 C critical), not a
completed factory thermal-policy port. Sustained smooth operation remains
unaccepted until hardware and frame-time evidence exists.


## Trial 84: early provider lifetime failure

[Device record](../build/device/m3-performance-84.json): candidate boot, DTBO and
all 17 super chunks passed readback. The native display stage was not reached.
Recovered pstore identifies a fatal `tsens_probe+0x17c/0x544` fault at 28 seconds,
after the userspace display gate populated TSENS. The pinned ACK implements
`init_common()` in `.init.text` (`drivers/thermal/qcom/tsens.c:889`), but the
TSENS v2 ops table retains a pointer to it. Creating this built-in sensor only
after `free_initmem()` is invalid. Pstore has ECC damage; the intact PC, fault
and panic lines are retained as evidence and raw logs are hashed.

The live stream separately shows Adreno SMMU clock lookup failing with `-110`
before GPUCC is registered, plus boot-state clock warnings. Those warnings are
not proof of the panic cause. The next DT moves EPSS, TSENS and GPUCC into normal
boot population, and verifies that the applied overlay puts staged SMMU before
GMU and Adreno. It keeps the exact kernel, firmware, signed vendor, GSI, 90 Hz
selection and display electrical configuration. No GPU/90 Hz success is claimed.

F.20 was restored automatically and passed ADB boot-completion and both LP-slot
checks. The original recovery copy was reused; stock partitions were not read
back again. Next target: reach native modeset, then prove an Adreno transaction
and Android rendering before measuring interactive frame times.


## Trial 85: native GPU binds; two explicit blockers

[Device record](../build/device/m3-performance-85.json): the TSENS fault did not
recur. Adreno SMMU registered, GMU/GPU joined IOMMU groups 15/16, native Adreno
6.5.0.2 bound and MSM DRM registered minor 0. CPU frequency transitions were
not captured, so binding progress is not DVFS acceptance.

The native KMS open then rejected F.20 SQE version 0.93. The pinned driver
requires at least 0.95. Independently, modeset returned `RMXPHY stock-timing
rejected ret=-22`: the project stock-link predicate only accepted 60 Hz, so the
90 Hz mode used the calculated link rate instead of 660 MHz. The unchanged PHY
guard correctly rejected that inconsistent request. Both modes use the same
660 MHz clock and PHY bytes in official source timing@0/timing@1. The patch now
admits exactly 60 or 90 Hz with all existing panel/DSC/format checks retained.
The complete DSI host patch stack applies to the pinned ACK source.

The next candidate uses only the upstream A650 SQE 1.12 update, retaining the
five original GMU/board-ZAP files. [Firmware source lock](../build/m3-gpu-firmware-source.json)
pins Linux firmware commit `599764611a8ac213c6aa6dad17c941c2f46b53cb`, Git blob and
SHA-256 digests, and carries its license/notice. The firmware loader's existing
minimum-version check remains intact. The original one-time acquisition record
is preserved separately. No repeated stock firmware read was needed.

[Replacement kernel build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/45402072797)
was dispatched from `bc15e0d23abe83e7112ff6d9cc4b03c0aaf0db14`. Device result is
pending. Pre-modeset CPU/thermal values will also be streamed to the independent
serial logger, so a display failure cannot hide those observations.

Trial 85 did not reach Android ADB or a valid physical pattern. F.20 was restored
and passed boot completion plus both LP-slot checks, without another full stock
readback. The goal remains native GPU submission, 90 Hz physical scanout and
measured interactive frame times on the same GSI/test volumes.


## Trial 86: normal native pattern, blocked Android handoff

[Device record](../build/device/m3-performance-86.json): the user confirmed the
native pattern is normal with the 90 Hz mode selected. The SQE version rejection
and 660 MHz PHY guard failure did not recur. GMU firmware v2.1.8 loaded. The
physical refresh measurement remains unavailable because the pre-init log was
not recovered; this is not a 90 FPS acceptance result.

Pre-modeset serial evidence reports CPU policies 0/4/7 using native
`qcom-cpufreq-hw` and `schedutil`, with maxima 1804800/2419200/2841600 kHz.
TSENS reported 39.1/38.4/36.4 C and the battery 32.3 C. These are startup
snapshots, not measured load/idle frequency transitions.

The native pattern ended, but Android ADB never appeared. The last streamed
message is `mdss_runtime_suspend` at 67.05 s; this alone does not identify the
blocking call. The existing recovery timer returned the phone to EDL and F.20
was restored and verified by boot completion/LP metadata. The original recovery
copy was reused without a full stock readback.

The next trial retains this kernel, firmware, vendor, GSI, test-volume seeds and
display configuration. It adds handoff stage markers and a same-boot read-only
serial snapshot of logs and task stacks if ADB has not arrived after 90 seconds.
The goal is to locate and fix the handoff block, then prove hardware submission
and interactive frame timing.


## Trial 87: the handoff script exits before Android

[Device record](../build/device/m3-performance-87.json): same kernel, firmware,
vendor, GSI, volumes and panel settings as trial 86. Native probe returned at
67.07 s, clock capture at 67.13 s and device snapshot at 67.68 s. The serial
diagnostic recovered `DRMTEST exit=0`; neither the probe nor the handoff script
was still running. No blocked D-state task was reported.

The performance packer had removed `tp_printk` and `tp_printk_stop_on_boot` to
reduce console noise and fit the header. This violates `ufs-init-trace.sh`'s
existing precondition. In the pinned ACK's `kernel/trace/trace.c`, the trace
iterator is allocated at boot only when requested; without it the sysctl
handler silently resets `tracepoint_printk` to zero. The shell's readback check
then exits under `set -e`, before starting the Android init witness. The next
candidate restores both parameters and removes optional console/DRM verbosity,
retaining the accepted display flags within 501 command-line bytes. Preflight
now checks for both required trace parameters, and a future failed readback
prints an explicit error. On-device confirmation is still pending.

The recovered four flips were spaced one second apart. Their sequence-derived
rates were about 7/s; these are not physical panel-rate or Android FPS results.
The updated probe uses 61 continuous flips and reports both presentation and
vblank-counter rates over 60 intervals. Its parser still rejects stale events
and now rejects incomplete continuous captures. ARM64 compilation and the five
KMS evidence tests passed. This measurement change does not alter electrical
parameters or the fixed image pattern.

F.20 was restored with boot completion and both LP metadata slots verified.
No full original-partition readback was repeated. Next target: execute Android
init, establish real Adreno submissions, then collect interactive frame times.


## Trial 88: native 90 Hz scanout and Android handoff, GPU enumeration blocked

[Device record](../build/device/m3-performance-88.json): restoring the two trace
boot parameters fixed the handoff regression on the handset. Android first-stage
mounted verified system/vendor, second-stage init ran, and enforcing GSI ADB was
retained in the same boot. The 60 continuous native KMS intervals took 670250 us,
about 89.518 scanout completions per second. This does not measure GPU rendering
or Android UI FPS. The physical pattern was confirmed normal in trial 86; no
additional physical observation was requested in trial 88.

SurfaceFlinger aborts during ANGLE Vulkan initialization (-3); the transfer probe
returns before choosing a physical device, so GPU submission remains unproved.
The log records SurfaceFlinger denied read on `/dev/dri`, whose directory label
is `device` although both nodes use `gpu_device`. DRM platform identity also
inherits a display-only sysfs label and shell identity reads are denied.

The next candidate labels the directory `gpu_device`, labels only the DRM
controller identity subtree `sysfs_gpu`, and allows GPU clients to traverse its
display parent. It retains enforcing and uses Android's existing GPU client read
rules; no broad device access or sysfs write permission is added. Strict policy
compilation passed on the retained GSI with neverallow checks enabled. The GPU
probe now prints the physical-device count, including enumeration failure.

Current goal: obtain a real Adreno submission and stable hardware-rendered
SurfaceFlinger, then measure interactive frames and load/idle clock transitions.


## Trial 89: Adreno submission, window-path diagnosis and visible desktop

[Device record](../build/device/m3-performance-89.json): the DRM labels fixed
enumeration. The enforced GSI reports one Turnip Adreno 650 (`0x06050002`), and
the transfer test submitted to the GPU, waited for its fence, and verified all
1 MiB on the CPU. SurfaceFlinger reports ANGLE GLES over Turnip Vulkan 1.3.346.

The first physical result was **white**, while internal screenshots were black.
Launcher, SystemUI and boot animation crashed in RenderThread at driver offset
`0x9fbc98`, reading address `0x70`. The caller is Android's AcquireNextImageKHR,
which invokes BindImageMemory2 with null memory plus VkNativeBufferANDROID for
a deferred swapchain. The pinned [Turnip image binding implementation](https://android.googlesource.com/platform/external/mesa3d/+/875160ed32cc5bc32777fa04870a0a57ed38c987/src/freedreno/vulkan/tu_image.cc)
has an explicit unimplemented Android null-memory branch. The null dereference
observed in the binary matches its subsequent access to `mem->iova`.

Setting `debug.angle.feature_overrides_disabled=swapchainDeferredMemoryAllocation`
uses ANGLE's supported upfront-allocation path and stopped that crash on the
same boot. A full Launcher wallpaper and icons appeared; the user confirmed
normal physical output and clearly more responsive scrolling. This is a narrow
window-allocation compatibility setting, not a complete implementation of
native Vulkan deferred binding. Hardware rendering remains active.

The generic GSI's 60 Hz render ceiling selected 45 Hz on the physical 90 Hz mode.
Temporary `peak_refresh_rate=90` and `min_refresh_rate=90` selected 90 Hz and an
11111111 ns scheduling period. The most recent Launcher layer had 63 valid
present timestamps; 60/62 positive intervals were below 13 ms, with median
11.074 ms. This small recent window does not prove sustained 90 FPS. Cumulative
Launcher stats include startup/first-use work: 1105 frames, 89 janky (8.05%),
p50 11 ms, p90 30 ms and p99 77 ms.

A bounded 90-second frequency trace observed multiple CPU OPPs on all three
clusters (policy 0: 691200-1804800, policy 4: 710400-2419200, policy 7:
844800-2841600 kHz). Trace controls were restored. GPU sysfs reads were denied
and no generic devfreq transition was recorded; dynamic GPU clocks remain to
be established. No fixed maximum-frequency setting was applied.

The next vendor candidate persists the tested ANGLE compatibility property and
uses a source RRO for default/peak refresh 90 Hz, retaining ColorFade/input
behavior. Read-only GPU devfreq labeling enables direct observation without
grants to change clocks/governors. Kernel, GSI and test-volume seeds stay fixed.
The Android 17 layer-list parser also now removes RequestedLayerState wrappers
before requesting per-layer presentation history; the unmodified wrapper gave
an empty sample list and was not valid frame evidence.
