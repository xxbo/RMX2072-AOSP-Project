# Compatibility and Validation Matrix

Status values: **Unknown**, **Source-reviewed**, **Build-tested**, **Boot-tested**, **Hardware-tested**, **Blocked**.

Driver-specific source evidence and proposed migration dispositions are tracked in [DRIVER_MIGRATION_MATRIX.md](./DRIVER_MIGRATION_MATRIX.md); shared prerequisites and sequencing are in [DRIVER_DEPENDENCY_MAP.md](./DRIVER_DEPENDENCY_MAP.md). Most entries remain source-reviewed. NQ-NCI strict DDK and CRC validation passed in run 42226214281; module loading remains untested. The [development plan](../plan.md) defines target-system acceptance. The table also includes hardware results recorded on the bring-up branches.

Current M3 hardware audit: [2026-11-24 responsiveness, Wi-Fi, audio and haptics](M3_HARDWARE_STATUS_2026-11-24.md). Historical cold-start/recovery results below apply to their named kernels, not automatically to trial 83. The phone was restored to F.20 after trial 83 and remains there during this read-only audit.

## Platform layers

| Layer | Candidate | Status | Evidence required |
| --- | --- | --- | --- |
| Android framework | Android 17 | Boot completed; standalone Launcher rendered | Trial 83 starts Launcher and captures complete wallpaper/icons. Physical Launcher/app-drawer confirmation was paused; setup skip still loops and provisioning remains incomplete. [Trial 83](../build/device/m3-setup83-result-2026-11-23.json) |
| System image | Android 17 QPR1 ARM64 + GMS, CP3A.260905.010 | API 37 enforcing; framework boot completed | Same GSI through trial 83; source vendor/kernel integration enables setup and standalone Launcher. Completing setup and daily-use hardware acceptance remain open. Historical disconnected headless start belongs to trial 35. [Trial 83](../build/device/m3-setup83-result-2026-11-23.json) |
| Vendor image | Signed project-built RMX2072 ext4 | Boot-tested on internal UFS | First-stage init verified and mounted vendor. Under enforcing, PID 1 imported the configured zygote scripts and vold read the complete vendor fstab. Full VINTF compatibility remains open. [Vendor service trial](../build/device/m1-ufs-first-stage-vendor-services-2026-11-13.json) |
| TEE / Keymaster | Source-built device HAL and 6.18 transport | Hardware information, HMAC parameters and fixed listener transaction verified | Trial 25 generated/deleted a temporary key through TIME listener continuation, then returned hardware information and HMAC parameters to GSI keystore2 on the same boot. Maintenance registered and vdc earlyBootEnded exited 0. HAL shared-secret computation/key generation and boot-level key storage remain incomplete. The resident `keymaster64` is factory secure firmware. [Trial 25](../build/device/m1-ufs-keymaster-transport-2026-11-14.json) |
| Stock vendor/ODM comparison | F.20 | Diagnostic comparison | Strict compile with the GSI reported 299 neverallow conflicts across 262 locations. Target vendor acceptance uses the project image. [Comparison](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/gsi17-init-policy-2026-11-11.json) |
| Legacy control | Realme F.20 4.19.157 | Stock boot-tested | Logging-reader Android restored and booted. [Recovery scope](DEVICE_BASELINE_2026-11-06.md) |
| Community kernel | SM8250-Common 4.19.325 | Build-tested | [Legacy build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866) |
| ACK/GKI | Android 17 6.18.32 generic ARM64 | Generic distribution build-tested | [Kleaf build](GKI_618_BUILD.md) |
| Platform kernel | 6.18.32 with source-built board DTB/DTBO | M3 display, touch and battery tested | Trial 83 reuses the trial 81 kernel and board trees; unattended restart is not accepted for this host-gated candidate. [Trial 83](../build/device/m3-setup83-result-2026-11-23.json) |
| Board DTB/DTBO | Source-built RMX2072 trees | M2 boot verified; M3 physical display/input verified | Trial 36 reached GSI with source trees/init. Trial 69 fixed physical corruption; trial 80 verified touch; trial 81 added real battery telemetry. No repeat cold-start qualification is requested. [Display](../build/device/m3-display-69-2026-11-21.json) · [Input](../build/device/m3-input80-result-2026-11-23.json) |
| Graphics userspace | Source SwiftShader / minigbm / DRM HWC3; GSI ANGLE selected | Correct physical output; CPU rendering | Trial 69 operator confirmed complete native and Android patterns without noise. Trial 83 SurfaceFlinger still uses SwiftShader; Adreno acceleration and frame/input latency acceptance remain open. [Hardware audit](M3_HARDWARE_STATUS_2026-11-24.md) |
| Device-specific modules | Built for the project kernel | Per driver | Record module load and hardware results by subsystem. |

## Hardware test matrix

| Feature | Status | Test evidence / notes |
| --- | --- | --- |
| Boot / reboot | Trial 83 framework boot completed; current unattended restart open | Trial 35 passed a historical disconnected headless start. Current display candidate has a host-gated test entry and screen-off/on USB gap; do not transfer old acceptance to it. [Trial 83](../build/device/m3-setup83-result-2026-11-23.json) |
| Display / brightness / refresh rate | Native and Android patterns physically confirmed | Trial 69 fixed corruption, confirmed by operator in both stages. Trial 83 selects 60 Hz; rendered frame rate and brightness-range acceptance remain open. [Trial 69](../build/device/m3-display-69-2026-11-21.json) |
| Touch / gestures | Physical tap and scroll passed | Trial 80 Goodix touch opens the language list and scrolls without reported offset/jumps; direct input, 1080 x 2400 range. Quantitative latency remains unmeasured. [Trial 80](../build/device/m3-input80-result-2026-11-23.json) |
| USB / ADB / MTP | Authenticated ADB after disconnected startup passed | Trial 35 passed exact 6.18/API 37/enforcing/PID 1/UFS identity, soak and 1 MiB transfer after power-key startup without USB. The older trial 28 failure remains recorded separately. MTP remains untested. [Trial 35](../build/device/m1-disconnected-start-35-2026-11-14.json) |
| UFS | Warm HS-G3 reads and cold verified GSI mounts hardware-tested | Earlier direct reads established two-lane HS-G3 and six LUNs. Trial 35's disconnected start verified and mounted both the GSI and project vendor from internal super. [G3 reads](../build/device/ufs-g3-2026-11-10.json) · [Verified mounts](M1_UFS_FIRST_STAGE.md) |
| Encrypted userdata | Open | Writable RAM-backed ext4 data and metadata passed write and fsync checks. Persistent encrypted UFS userdata across reboot remains untested. [Scratch volumes](M1_UFS_FIRST_STAGE.md#writable-data-and-metadata-trial) |
| SIM / calls / SMS / mobile data | Unknown | |
| Wi-Fi | Framework service only; physical WLAN not ported | Candidate disables cfg80211/Atheros wireless stack. Fresh F.20 binding identifies QCA6390, PCI 17cb:1101; no GSI scan/association/traffic acceptance. [Audit](M3_HARDWARE_STATUS_2026-11-24.md) |
| Bluetooth | Unknown | |
| NFC | Unknown | |
| GPS / location | Unknown | |
| Speakers / microphones / earpiece | AudioService boots; no PCM backend | Source audio HAL returns empty ports/routes/microphones. Qualcomm ASoC/ADSP disabled; stock speaker amps bind tfa98xx. No physical playback/capture acceptance. [Audit](M3_HARDWARE_STATUS_2026-11-24.md) |
| Vibration / haptics | Stock binding identified; project hardware path not ported | F.20 binds aw8697_haptic at I2C 7-005a. No project AW8697 port or device-specific vibrator HAL implementation found. [Audit](M3_HARDWARE_STATUS_2026-11-24.md) |
| Camera (front/rear/video) | Unknown | |
| Fingerprint | Unknown | |
| Sensors | Unknown | |
| Battery telemetry / charging | Real gauge passed; charging integration open | Trial 81 reads BQ28Z610 and matches Android capacity, voltage and temperature without overrides. Charging/fast-charging acceptance does not follow from a working gauge. [Trial 81](../build/device/m3-battery81-result-2026-11-23.json) |
| Thermal / sustained performance | Incomplete | Candidate disables QCOM CPUfreq HW and TSENS; Power HAL implements no boosts/hint sessions. GPU rendering and quantitative performance acceptance remain open. [Audit](M3_HARDWARE_STATUS_2026-11-24.md) |
| Widevine / DRM | Unknown | |
| OTA / recovery / rollback | Prepared-host automatic recovery passed on the cold-start kernel | Trial 35 expired the cold-start boot's lease, correlated its journal and 29-second pretimeout, disabled the recovery watchdog and autonomously entered EDL at 176.094 seconds. The waiting host restored F.20 and verified all original bytes and boot completion. No physical keys or host reboot command were used. Unattended long EDL hold and OTA remain open. [Trial 35 recovery](../build/device/m1-autonomous-recovery-35-2026-11-14.json) |

## Test record template
For each test, record date/device build, kernel commit/config, system/vendor fingerprints, exact steps, expected and observed behavior, logs and result.
