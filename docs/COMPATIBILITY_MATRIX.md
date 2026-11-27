# Compatibility and Validation Matrix

Status values: **Unknown**, **Source-reviewed**, **Build-tested**, **Boot-tested**, **Hardware-tested**, **Blocked**.

Driver-specific source evidence and proposed migration dispositions are tracked in [DRIVER_MIGRATION_MATRIX.md](./DRIVER_MIGRATION_MATRIX.md); shared prerequisites and sequencing are in [DRIVER_DEPENDENCY_MAP.md](./DRIVER_DEPENDENCY_MAP.md). Most entries remain source-reviewed. NQ-NCI strict DDK and CRC validation passed in run 42226214281; module loading remains untested. The [development plan](../plan.md) defines target-system acceptance. The table also includes hardware results recorded on the bring-up branches.

Current acceptance: [November 27 hardware record](M3_HARDWARE_2026-11-27.md).
Trial 90 supplies the accepted Adreno/90 Hz baseline and November 25 bounded
GPU load/idle result. Trial 98 adds bounded CPU frequency-response and thermal
readout evidence. Trial 99 enumerates QCA6390. Trial 100 adds boot firmware,
reaches a QMI target response and retains GSI after 195.609 seconds of same-boot
ADB checks. Trial 101 adds the original F.20 board ELF and registers phy0/wlan0;
GSI is retained. `board_id=0xff` remains unqualified as an exact board identity.
Trial 102 installs the mainline RRO, but the GSI supplicant's constructor uses
SVE and faults on this non-SVE handset before binder registration. Source vendor
AIDL supplicant ARMv8-A build work is pending; scan, connection and RF/calibration
acceptance remain open.
Historical cold-start results apply only to their named builds.

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
| Graphics userspace | Source Turnip/minigbm/DRM HWC3 with GSI ANGLE | Hardware rendering and physical interaction passed | Trial 89 operator confirmed normal, smoother UI; trial 90 verifies automatic Adreno/90 Hz settings. Sustained 90 FPS remains unmeasured. [Trial 90](../build/device/m3-performance-90.json) |
| Device-specific modules | Built for the project kernel | Per driver | Record module load and hardware results by subsystem. |

## Hardware test matrix

| Feature | Status | Test evidence / notes |
| --- | --- | --- |
| Boot / reboot | Trial 83 framework boot completed; current unattended restart open | Trial 35 passed a historical disconnected headless start. Current display candidate has a host-gated test entry and screen-off/on USB gap; do not transfer old acceptance to it. [Trial 83](../build/device/m3-setup83-result-2026-11-23.json) |
| Display / brightness / refresh rate | Correct physical output; 1080x2400 at 90 Hz | Trial 69 fixes DSC corruption. Trial 90 verifies 90 Hz defaults; brightness-range and sustained frame-rate acceptance remain open. [Trial 90](../build/device/m3-performance-90.json) |
| Touch / gestures | Physical tap and scroll passed | Trial 80 Goodix touch opens the language list and scrolls without reported offset/jumps; direct input, 1080 x 2400 range. Quantitative latency remains unmeasured. [Trial 80](../build/device/m3-input80-result-2026-11-23.json) |
| USB / ADB / MTP | Authenticated ADB after disconnected startup passed | Trial 35 passed exact 6.18/API 37/enforcing/PID 1/UFS identity, soak and 1 MiB transfer after power-key startup without USB. The older trial 28 failure remains recorded separately. MTP remains untested. [Trial 35](../build/device/m1-disconnected-start-35-2026-11-14.json) |
| UFS | Warm HS-G3 reads and cold verified GSI mounts hardware-tested | Earlier direct reads established two-lane HS-G3 and six LUNs. Trial 35's disconnected start verified and mounted both the GSI and project vendor from internal super. [G3 reads](../build/device/ufs-g3-2026-11-10.json) · [Verified mounts](M1_UFS_FIRST_STAGE.md) |
| Encrypted userdata | Open | Writable RAM-backed ext4 data and metadata passed write and fsync checks. Persistent encrypted UFS userdata across reboot remains untested. [Scratch volumes](M1_UFS_FIRST_STAGE.md#writable-data-and-metadata-trial) |
| SIM / calls / SMS / mobile data | Target path not ported | Stock external modem 17cb:0306 exposes MHI/QMI/IPCR and reports DSDS, LOADED/ABSENT. No target network-service acceptance. [Inventory](../build/device/m3-f20-subsystems-2026-11-26.json) |
| Wi-Fi | Native phy0/wlan0 registered; GSI supplicant ISA incompatibility blocks scan | Trial 102 retains GSI/ADB and enables the RRO. Its matching mainline executable hits SVE INDEX at 0x2cf584 (SIGILL) before binder registration; all eight CPU feature lists lack SVE. Trial 103 removes the failed RRO and retains native wlan0, Enforcing GSI and ADB without that crash loop. Source vendor AIDL ARMv8-A replacement build and physical integration are pending. Scan/association/DHCP/traffic and RF/calibration remain untested. [WLAN result](../build/device/m3-wifi-102-2026-11-27.json) |
| Bluetooth | Unknown | |
| NFC | Unknown | |
| GPS / location | Target GNSS path not ported | GNSS transport/HAL and real location fix remain open; no location coordinates collected. |
| Speakers / microphones / earpiece | AudioService boots; no PCM backend | Source audio HAL returns empty ports/routes/microphones. Qualcomm ASoC/ADSP disabled; stock speaker amps bind tfa98xx. No physical playback/capture acceptance. [Audit](M3_HARDWARE_STATUS_2026-11-24.md) |
| Vibration / haptics | Stock binding identified; project hardware path not ported | F.20 binds aw8697_haptic at I2C 7-005a. No project AW8697 port or device-specific vibrator HAL implementation found. [Audit](M3_HARDWARE_STATUS_2026-11-24.md) |
| Camera (front/rear/video) | Unknown | |
| Fingerprint | Stock Goodix path identified; GSI HAL absent | Requires secure matching/auth tokens and optical illumination, not only a control node. [Evidence](M3_HARDWARE_2026-11-25.md) |
| Sensors | Stock HAL models inventoried; target not ported | bmi26x acceleration/gyro, mmc5603x compass, stk33502 light/proximity; stock SLPI is online. Names are HAL reports, not direct chip-ID reads. [Inventory](../build/device/m3-f20-subsystems-2026-11-26.json) |
| Battery telemetry / charging | Real gauge passed; charging integration open | Trial 81 reads BQ28Z610 and matches Android capacity, voltage and temperature without overrides. Charging/fast-charging acceptance does not follow from a working gauge. [Trial 81](../build/device/m3-battery81-result-2026-11-23.json) |
| CPU frequency / scheduling | Short pinned load/recovery frequency observation passed; scheduling open | Trial 98 reaches 1804.8/2419.2/2841.6 MHz on the three CPU policies and samples lower values after each load, with unchanged schedutil/bounds. Background work/ADB sampling remain active; this is not idle residency or EAS placement acceptance. [CPU result](../build/device/m3-cpu-thermal-98-2026-11-26.json) |
| Thermal / sustained performance | Kernel sensors/cooling associations visible; Android Thermal HAL absent | Trial 98 reads TSENS and gauge under enforcing; no thermal trip is induced. GPU bounded transfer load passes 305 -> 587 -> 305 MHz. Thermal mitigation, scheduling/frame times and sustained performance remain open. [Thermal result](../build/device/m3-cpu-thermal-98-2026-11-26.json) · [GPU result](../build/device/m3-gpu-dvfs-2026-11-25.json) |
| Widevine / DRM | Unknown | |
| OTA / recovery / rollback | Prepared-host automatic recovery passed on the cold-start kernel | Trial 35 expired the cold-start boot's lease, correlated its journal and 29-second pretimeout, disabled the recovery watchdog and autonomously entered EDL at 176.094 seconds. The waiting host restored F.20 and verified all original bytes and boot completion. No physical keys or host reboot command were used. Unattended long EDL hold and OTA remain open. [Trial 35 recovery](../build/device/m1-autonomous-recovery-35-2026-11-14.json) |

## Test record template
For each test, record date/device build, kernel commit/config, system/vendor fingerprints, exact steps, expected and observed behavior, logs and result.
