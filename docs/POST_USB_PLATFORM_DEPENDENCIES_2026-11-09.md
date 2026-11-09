# Platform work after USB diagnostics

This is a read-only comparison of the captured effective vendor tree, the pinned ACK compiled SM8250 tree and the downloaded bootstrap configuration. It does not activate storage, change voltages or establish Android compatibility. The working USB profile keeps original DTBO and the native entry wrapper; it still uses `clk_ignore_unused`, `pd_ignore_unused` and permissive firmware dependency linking.

| Dependency | Captured legacy state | Pinned modern binding / next validation |
| --- | --- | --- |
| Hardware lock / SMEM | Runtime binds `qcom_hwspinlock` and `qcom-smem` | Keep this verified foundation; do not reintroduce the earlier handoff-only tree |
| Secure firmware / SMMU | SCM ready, apps SMMU probed, SID0 USB communicates | Preserve the post-OEM SID/mask validator and collect live fault/IRQ data for subsequent changes |
| Watchdog | F.20 uses `msm_watchdog` at `0x17c10000`. The legacy binding on the 6.18 USB baseline exposed no watchdog class device. | The [SID0 watchdog control](INDEPENDENT_KERNEL_BRINGUP.md#apss-watchdog-on-the-paced-sid0-profile) registered watchdog0 with a sleep clock and SPI 0 edge-rising IRQ. Start, ping and stop passed on the handset. Firmware handoff with an active timer and deliberate expiry remain open. |
| UFS host | Enabled `qcom,ufshc`, but probe remains deferred; clocks reference the disabled old GCC provider | Native SM8250 compatible list, modern GCC clock IDs, `UFS_PHY_GDSC`, reset named `rst`, and a controller reset provider for its PHY |
| UFS PHY | `qcom,ufs-phy-qmp-v4`, clocks named `ref_clk_src`/`ref_aux_clk` | Built QMP-UFS driver; modern compatible is `qcom,sm8250-qmp-ufs-phy`, with `ref`/`ref_aux`/`qref`, PHY reset and shared power domain |
| GPIO / TLMM | `qcom,kona-pinctrl`, one `0xf000000`/16 MiB resource; GPIO consumers defer | Built SM8250 pinctrl driver expects three named resources. Do not change only the compatible string |
| Unrestricted USB throughput | Host ACM works; uncapped bursts had short responses without reboot | Keep raw burst failures separate from paced stability. A larger requested host queue alone did not fix them |

The modern TLMM resources are west `0x0f100000`, south `0x0f500000`, north `0x0f900000`, each 3 MiB. These are physical resource facts from the pinned compiled tree, not a tested replacement for the vendor pin states. Preserve OEM overlay symbols/targets while migrating the provider.

## UFS supplies and resource boundaries

The vendor UFS host's first MMIO resource (`0x01d84000`, 12 KiB) and SPI 265 agree with the pinned modern tree. The old second ICE resource belongs to a separate modern crypto dependency and must not be blindly treated as part of the host register block. The modern host exposes `#reset-cells = <1>`; the modern PHY reset refers back to that provider. Both host and PHY use GCC's UFS PHY power domain.

Captured regulator constraints are below. They are DT constraints/initial values, not newly measured live voltages or instructions to force a rail to a limit.

| Consumer | Vendor supply | Captured constraint |
| --- | --- | --- |
| UFS PHY `vdda-phy` | PM8150 L5 | 880,000 uV; already represented by the USB profile's modern L5 provider |
| UFS PHY `vdda-pll` | PM8150 L9 | 1,200,000 uV |
| Host `vcc` | PM8150 L17 | 2,496,000–3,008,000 uV; initial 2,496,000 |
| Host `vccq` / reference clock | PM8150 L6 | 1,200,000 uV |
| Host `vccq2` | PM8150 S4 | 1,800,000–1,920,000 uV; initial 1,800,000 |

The kernel already builds `SCSI_UFS_QCOM`, `PHY_QCOM_QMP_UFS`, `SCSI_UFS_CRYPTO` and `QCOM_INLINE_CRYPTO_ENGINE`. Built drivers do not remove the provider/binding/firmware dependencies above. Keep the first storage validation to controller/PHY probe, device identification and read-only block inspection; Android mounting and encryption remain later gates.

### RMX2072 UFS device reset

The [follow-up handset trials](RMX2072_EDL_AND_UFS.md#why-the-gpio-mask-matters) registered the isolated TLMM provider with GPIO 180 as its only valid line. The chip and line-info queries completed with USB still configured. The unmasked probe rebooted. Neither trial drove the reset pad.

The restored F.20 live tree maps `dev-reset-assert` and `dev-reset-deassert` on the UFS host to two TLMM pin states for `ufs_reset`. Both specify pull-down and 8 mA drive. Assert drives the pad low and deassert drives it high. Stock bound `ufshcd-qcom` at `1d84000.ufshc` and `ufs_qcom_phy_qmp_v4` at `1d87000.ufsphy_mem`.

The pinned ACK UFS driver acquires an optional GPIO named `reset` and toggles it with logical assert/deassert values. The SM8250 pinctrl driver assigns the dedicated reset **GPIO group 180** to the south tile, control offset `0xb8000`. This gives a candidate mapping of `reset-gpios = <&tlmm 180 GPIO_ACTIVE_LOW>` once the modern TLMM provider is functional. Verify that mapping with the original OEM overlay before enabling the host. The host's GCC block reset and the PHY reset supplied by the host have separate purposes. [UFS driver](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/ufs/host/ufs-qcom.c) · [SM8250 pinctrl](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/pinctrl/qcom/pinctrl-sm8250.c)

## Order of follow-up controls

1. Preserve the passed 606-second USB same-boot/transfer baseline, its burst limitations and verified stock recovery hashes.
2. Carry forward the executed watchdog control and original DTBO. Use a separately identified trial if testing deliberate watchdog expiry or adoption of a firmware-started timer.
3. Prepare UFS host/PHY/RPMh supply mappings on the same OEM-preserving tree. Validate provider graph and IRQ/register boundaries in CI before physical probing.
4. Address production clock/power handling and the distinct three-bank TLMM provider. Do not infer suspend, thermal management or Android readiness from RAM-only USB operation.

Evidence and physical trial hashes: [USB comparison](../build/device/usb-staged-sid-comparison-2026-11-09.json), [soak record](../build/device/usb-soak-2026-11-09.json), [bring-up journal](INDEPENDENT_KERNEL_BRINGUP.md).
