# M3 hardware status: responsiveness, Wi-Fi, audio and haptics

## Scope and evidence

This is a read-only audit requested on 2026-11-24 (Asia/Shanghai), against source
commit `626ae2e46becf110e58361c3921019c7daa88cfc` and the saved trial 83 logs/config.
The handset remains on **RMX2072_11_F.20 / 4.19.157-perf+**. Its current boot ID
is `a91a450d-f8e8-4ffb-a9b4-80446d8fc65f`, with ADB and boot completion confirmed.
No new GSI boot, firmware write, partition backup/readback, Wi-Fi scan, playback
or vibration test was performed. Stock sysfs bindings identify hardware paths;
they do not establish that the corresponding 6.18 drivers work.

The [machine-readable audit](../build/device/m3-hardware-status-2026-11-24.json)
contains source/config/log hashes and the stock observations. Trial 83's
[result](../build/device/m3-setup83-result-2026-11-23.json) and
[subsequent F.20 restore](../build/device/m3-setup83-f20-restore-2026-11-23.json)
remain the deployment history. This audit does not resume device testing.

## 1. Responsiveness: software rendering, performance controls incomplete

Trial 83 SurfaceFlinger reports the actual renderer as
`ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (LLVM 16.0.0) (0x0000C0DE)), SwiftShader driver-5.0.0)`.
The project [vendor properties](../device/realme/bladerunner_48m/m3-vendor/vendor.prop)
select ANGLE/SwiftShader and linear minigbm buffers. The accepted display path
therefore scans out correct pixels, but Android rendering still runs on the CPU.
This is a substantial, evidenced performance limitation. A 60 Hz display mode
does not prove 60 rendered frames per second or low input latency.

The candidate config disables `CONFIG_ARM_QCOM_CPUFREQ_HW`,
`CONFIG_ARM_QCOM_CPUFREQ_NVMEM` and `CONFIG_QCOM_TSENS`. The source
[Power HAL](../device/realme/bladerunner_48m/m3-power/service.cpp) advertises no
mode, boost or hint-session support. Stock exposes three `qcom-cpufreq-hw`
policies with `schedutil`; these stock frequencies must not be reported as GSI
measurements. No GSI frame-time or CPU-frequency trace was collected in this audit,
so the relative contribution of rendering, scheduling and input remains unmeasured.

Next implementation path: enable and verify the Adreno 650/GMU kernel path,
including power, clocks, firmware, IOMMU and buffer synchronization; integrate
source graphics userspace, then prove an Adreno renderer and GPU submissions in
Android. [Mesa Freedreno/Turnip](https://docs.mesa3d.org/drivers/freedreno.html)
provides the relevant open-source Adreno graphics stack; upstream support is not
board acceptance. Wire CPU/GPU frequency control, bandwidth and thermal feedback
before tuning boosts. Measure frame times and touch-to-frame latency on the same
UI workload. Preserve the trial 69 display/DSC fix throughout.

## 2. Wi-Fi: Android service enabled, radio path not ported

Trial 82 enabled the framework Wi-Fi service so setup could open its network page.
That was not a successful Wi-Fi scan. The trial 83 kernel config disables
`CONFIG_CFG80211`, `CONFIG_WLAN_VENDOR_ATH` and `CONFIG_QRTR`; the required wireless
stack is not present in this candidate.

Fresh F.20 sysfs reads bind `wlan0` to PCI endpoint `0000:01:00.0`,
vendor/device **17cb:1101**, through `cnss_pci`. This identifies QCA6390 using
the [Linux 6.18 ath11k PCI table](https://github.com/torvalds/linux/blob/v6.18/drivers/net/wireless/ath/ath11k/pci.c).
The pinned OEM board 20607 DTS independently declares `qcom,cnss-qca6390`.
The modem's separate `17cb:0306` MHI endpoint must not be confused with WLAN.

The source-driver candidate is ath11k PCIe; upstream lists
[QCA6390 support](https://wireless.docs.kernel.org/en/latest/en/users/drivers/ath11k.html).
Board work still includes PCIe power/reset and interrupts, MHI/QMI/QRTR,
compatible firmware and board/calibration data, cfg80211/mac80211, and regulatory
configuration. Android then needs working wificond/nl80211 and supplicant
integration with correct permissions and policy. Follow the
[AOSP Wi-Fi HAL contract](https://source.android.com/docs/core/connect/wifi-hal);
do not require a hostapd or every optional Vendor HAL feature merely to accept a
station scan. Do not try to load the stock 4.19 `wlan.ko` into 6.18.

Acceptance: real scan results, association and DHCP, then traffic over WLAN with
ADB connectivity retained. None of these has passed on this GSI candidate.

## 3. Audio and vibration: physical functions remain unaccepted

The source [audio service](../device/realme/bladerunner_48m/m3-audio/service.cpp)
provides Core/Config/Effect endpoints to let AudioService start, but returns empty
audio ports, routes and microphones. Trial 83 logs explicitly report
`RMX Audio getAudioPorts: 0, PCM backend unavailable`. `CONFIG_SND_SOC_QCOM` and
`CONFIG_QCOM_Q6V5_ADSP` are disabled. Volume UI operation does not demonstrate sound.

F.20 exposes `kona-mtp-snd-card` and PCM playback/capture endpoints. Its two speaker
amplifier devices at I2C `4-0034` and `4-0035` bind to `tfa98xx`. Porting requires
the ADSP/Q6 and ASoC path, board codec/amplifier routing and calibration, then real
PCM-backed HAL streams. Speaker, microphone and earpiece tests remain open.
The exact main codec configuration needs a separate dependency audit.

F.20's vibrator binds to **`aw8697_haptic` at I2C `7-005a`**, on controller
`a8c000.i2c`; `/sys/class/leds/vibrator` resolves to that device. The project board
source has no AW8697 port or device-specific vibrator HAL implementation. A GSI
`VibratorInfo` warning alone neither identifies a working HAL nor proves a motor
transaction. Next steps are the board bus/reset/IRQ and controller driver,
waveform/calibration handling as required, and an honest Android vibrator HAL.
Accept it only after a real short pulse and touch-feedback test, including stop
behavior. No vibration test was run during this audit.

## Recommended next target

Prioritize GPU rendering and CPU/thermal foundations to improve the already
working display/input experience, then WLAN, followed by physical audio and
haptics. Each subsystem needs its own hardware acceptance evidence. Setup completion
and screen-off/on USB continuity remain separate known gaps from trial 83.
No further cold-start rehearsal is part of this recommendation.
