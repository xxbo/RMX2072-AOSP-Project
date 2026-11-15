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
overlay; USB/UFS/PDC/PON resource checks remain required. The GPU is not enabled
by this first display overlay. Any display bridge or firmware handoff dependency
still needs physical qualification; successful compilation does not establish it.

The static KMS probe uses DRM ioctls and driver-allocated dumb buffers. It finds
a connected physical DSI connector with the expected mode, sets a colored test
pattern and waits for four actual page-flip events. It releases DRM master and
buffers before Android starts. It never writes guessed framebuffer addresses or
storage. The initramfs publishes its result and display probe/deferred-driver
logs into the existing scratch `/data` for ADB. A KMS return of success alone
is not recorded as operator-confirmed screen output.

## Graphics implementation

The bounded Android 17 source product builds ANGLE EGL/GLES, SwiftShader Vulkan,
minigbm configured for MSM and the generic DRM HWC3 service. Composer uses mapper
metadata rather than a downstream SDM/KGSL backend. These are native ARM64
libraries and HALs for the actual device. Initial CPU rendering is an explicit
intermediate dependency; this does not claim Adreno 650 support. The GSI itself,
source first-stage init and writable test-volume seeds stay fixed.

## Stage acceptance

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
