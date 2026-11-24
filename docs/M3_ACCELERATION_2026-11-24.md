# M3 native Adreno and 90 Hz bring-up

The user resumed implementation on November 24, targeting hardware rendering,
90 Hz and CPU/GPU frequency control. Trial 83's working display, input, gauge,
GSI and RAM test-volume seeds remain the baseline. Cold-start repeats are outside
this task. The phone remains on F.20 during build preparation.

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
in GitHub Actions; Turnip is not accepted until the successful artifact, ELF
architecture, dependencies and source/digest checks all pass.

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
