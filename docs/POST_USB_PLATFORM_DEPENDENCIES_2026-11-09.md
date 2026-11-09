# Platform work after USB diagnostics

This is a read-only comparison of the captured effective vendor tree, the pinned ACK compiled SM8250 tree and the downloaded bootstrap configuration. It does not activate storage, change voltages or establish Android compatibility. The working USB profile keeps original DTBO and the native entry wrapper; it still uses `clk_ignore_unused`, `pd_ignore_unused` and permissive firmware dependency linking.

| Dependency | Captured legacy state | Pinned modern binding / next validation |
| --- | --- | --- |
| Hardware lock / SMEM | Runtime binds `qcom_hwspinlock` and `qcom-smem` | Keep this verified foundation; do not reintroduce the earlier handoff-only tree |
| Secure firmware / SMMU | SCM ready, apps SMMU probed, SID0 USB communicates | Preserve the post-OEM SID/mask validator and collect live fault/IRQ data for subsequent changes |
| Watchdog | `qcom,msm-watchdog` at `0x17c10000`; no runtime watchdog class device | Built `CONFIG_QCOM_WDT=y`; modern tree uses `qcom,apss-wdt-sm8250`, `qcom,kpss-wdt`, a sleep clock and SPI 0 edge-rising IRQ. Test adoption/restart behavior separately |
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

## Order of follow-up controls

1. Finish and archive the USB same-boot/transfer test, including burst limitations and stock recovery hashes.
2. Add the modern watchdog description as an isolated control; retain live USB logging and verify that firmware-started watchdog handling and recovery remain usable.
3. Prepare UFS host/PHY/RPMh supply mappings on the same OEM-preserving tree. Validate provider graph and IRQ/register boundaries in CI before physical probing.
4. Address production clock/power handling and the distinct three-bank TLMM provider. Do not infer suspend, thermal management or Android readiness from RAM-only USB operation.

Evidence and physical trial hashes: [USB comparison](../build/device/usb-staged-sid-comparison-2026-11-09.json), [soak record](../build/device/usb-soak-2026-11-09.json), [bring-up journal](INDEPENDENT_KERNEL_BRINGUP.md).
