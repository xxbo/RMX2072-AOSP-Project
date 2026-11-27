# M3 application rendering: trial 77

Current goal: physical AOSP Launcher on the project ACK 6.18 kernel, Android 17
GSI and source vendor. The trial reaches a real Android welcome screen, not the
Launcher desktop. Recovery work below follows an actual USB loss; it is not a
repeat cold-start or watchdog-injection qualification.

## Reproduced mapper failure and bounded correction

Trial 76 initialized the synthetic password with a real TEE import and reached
GSI boot completion, but applications repeatedly logged `Driver is uninitialized`,
failed hardware-buffer imports and aborted in HWUI with no drawable surface.
The mapper runs inside the application UID. The project's `/dev/dri/renderD128`
was 0660 system:graphics, which excluded ordinary application UIDs.

The exact pinned [minigbm driver](https://android.googlesource.com/platform/external/minigbm/+/ce79bbee67b3e2ea7abb110e1415e9ceceaa6471/cros_gralloc/cros_gralloc_driver.cc)
opens render nodes O_RDWR before trying primary nodes. The actual GSI policy
already grants appdomain through gpu_sphal_domain access to gpu_device. Trial 77
changes only render-node DAC to 0666. Primary DRM nodes remain 0660, the device
label remains gpu_device and enforcing stays enabled. There is no SELinux change.

All 36 local checks passed. Kernel, DT, PPS/display flags, graphics libraries,
Keymaster/audio/health/power HALs, GSI and both RAM test seeds are identical to
trial 76. The old candidate and new candidate each passed full container
verification; no new full read of original F.20 partitions was performed.

## Handset result

Boot `5b62d1b7-66fd-4041-94a3-3e142b2b2dd5` reached API 37, enforcing and
`sys.boot_completed=1`. The collected post-start logs no longer contain the
previous mapper initialization/no-surface failures. SystemUI and SetupWizard
created windows. `screencap` returned this actual 1080x2400 frame:

![Trial 77 GSI welcome screen](assets/m3-trial77-welcome.png)

The operator subsequently confirmed the physical phone was still on the welcome
page after ADB disappeared. This is application-screen progress. It does not
establish Launcher acceptance, touch, Adreno acceleration or real audio output.
Audio Core/Config/Effect and AudioService register, but there are still no PCM
routes and AudioService reports NO_INIT for some route/volume operations.
The early AES self-test still returns -49; no roundtrip/tamper pass is claimed.

An explicit QuickstepLauncher start returned OK but the focused window remained
SetupWizard. A follow-up command read both setup flags as 0, then attempted to
set device_provisioned and user_setup_complete to 1. ADB and all observed USB
interfaces disappeared before either post-write value was read back. The exact
completed writes are unknown. The host's retention check failed; there is no
trial-77 gsi-stable acceptance. The last visible welcome frame alone cannot
prove that every component remained responsive.

USB/provisioning interaction is a hypothesis, not an established root cause.
The saved log shows AdbService first disabling USB ADB at systemReady, then
enabling it later. The vendor profile only sets sys.usb.config at APEX activation
and boot. The next investigation must stream logs continuously across the
transition and compare actual adb_enabled, development_settings_enabled,
persist.sys.usb.config, sys.usb.config/state and gadget state before any setup
write. Do not repeat the failed multi-write command blindly.

Both power+volume-up and a three-button hold reportedly had no effect. With
the battery connector already exposed, the operator disconnected USB and the
battery connector, then reconnected the battery and USB while holding both
volume keys. The host detected 9008 on COM6 and restored the existing verified
F.20 super, boot and DTBO. The restore runner exited successfully: stock ADB,
RMX2072_11_F.20, sys.boot_completed=1 and both LP slots matched the saved stock
metadata. Stock boot UUID is 98ff2915-30ed-4531-8469-e207976552cc.
The operator confirmed normal stock display with no repeated reboot.

Recovery reused the sole original backup and checked successful write
acknowledgements, boot identity and LP metadata. No new full stock partition
readback or on-device full-super hash was performed. Original userdata was not
written. The pre-disconnection logs and welcome screenshot were saved on the
host; no crash cause is inferred from RAM state lost during the battery reset.

## Separate screen-transition issue

Trial 76 later crashed system_server in SwiftShader JIT after an execmem denial
while PowerManager handled a screen transition. The platform neverallow remains
intact. For trial 77 a temporary RAM-data setting `svc power stayon true` was
confirmed as 15 with mStayOn=true. An early automatic attempt ran before
Settings/Input were ready and failed; the collector is now gated on those
services and boot completion and requires the actual result.

The signed GSI framework-res.apk contains bool/config_displayColorFadeDisabled,
currently false. Pinned AOSP DisplayPowerController checks that resource before
constructing ColorFade. A source vendor overlay is a bounded follow-up for this
CPU-rendering profile; it has not been built or tested, and no execmem exception
for system_server is proposed.

Current objective after recovery: retain authenticated GSI ADB through first-run
setup, show the physical Launcher, then remove the screen-transition crash.
The accepted panel configuration stays fixed.

[Input comparison](../build/device/m3-render77-preflight-2026-11-22.json) ·
[Result and evidence hashes](../build/device/m3-render77-result-2026-11-22.json)
