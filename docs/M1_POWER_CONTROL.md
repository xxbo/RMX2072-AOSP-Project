# M1 power control investigation

Trial 28 did not pass disconnected power-key startup. The operator reported
no response to a 2–3-second power press, then confirmed that the handset only
reacted when USB was connected. That boot contained `androidboot.mode=charger`.
Shutdown completion was not independently observed while disconnected. These
observations do not yet distinguish incomplete shutdown from a PMIC wakeup
configuration problem. [Trial evidence](../build/device/m1-autonomous-boot-2026-11-14.json)

The current kernel contains PSCI and the SPMI bus/PMIC infrastructure, but its
recorded configuration does not enable `POWER_RESET_MSM`,
`POWER_RESET_QCOM_PON`, `INPUT_PM8941_PWRKEY` or `RTC_DRV_PM8XXX`.
The effective selected base tree plus OEM overlay 17 describes primary PON at
`/soc/qcom,spmi@c440000/qcom,pm8150@0/qcom,power-on@800`, with legacy
`qcom,qpnp-power-on`, `qcom,system-reset`, `qcom,pmicwd`, and power/resin
interrupts `<0 8 0 3>` and `<0 8 1 3>`. The PMIC children are introduced by
the OEM overlay; examining the base alone misses this dependency.

The official realme kernel's
[msm-poweroff.c](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source/blob/master/drivers/power/reset/msm-poweroff.c)
programs PON shutdown before deasserting PS_HOLD. Its
[qpnp-power-on.c](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source/blob/master/drivers/input/misc/qpnp-power-on.c)
configures the system-reset PMIC and any explicitly registered secondary PONs.
The inspected qpnp source has Git blob SHA
`ce995a5d22ca3875fa0c759c0b65bfa7ecf2fe49`.

In the pinned ACK revision, the
[pm8941 power-key driver](https://android.googlesource.com/kernel/common/+/ecdaacc9a0ee87eaf9544e1836d86bd9d590312e/drivers/input/misc/pm8941-pwrkey.c)
also installs a reboot notifier that programs PS_HOLD shutdown/reset type for
supported PMICs. The separate
[qcom PON driver](https://android.googlesource.com/kernel/common/+/ecdaacc9a0ee87eaf9544e1836d86bd9d590312e/drivers/power/reset/qcom-pon.c)
principally handles reboot-mode storage and child population. Enabling only
that option would not establish the complete shutdown sequence.

Next measurements: retain the previous console/pmsg without the old raw-memory
entry probe, inspect the actual poweroff tail, and compare a disconnected stock
shutdown/power-key start if needed. Before porting PMIC poweroff, verify SPMI
binding, register access, the effective IRQ provider and the primary/secondary
PON topology. No PMIC registers have been modified by this investigation and
no poweroff fix is claimed. Missing Linux key input support alone does not
prove why a fully powered-off handset fails to wake.

The trial 29 recovery console confirmed that `c440000.qcom,spmi` is deferred,
while the arbiter identifies hardware version v5. Its parent IRQ resolves to
PDC pin 1. The effective PDC node still has only `qcom,kona-pdc`; the pinned
[6.18 PDC driver](https://android.googlesource.com/kernel/common/+/ecdaacc9a0ee87eaf9544e1836d86bd9d590312e/drivers/irqchip/qcom-pdc.c)
registers `qcom,pdc`, and `CONFIG_QCOM_PDC=y` is already built in. This identifies
a missing binding before PMIC children can appear. A PDC-only correction must
be tested independently of the earlier combined TLMM/PDC probe. The short EDL
window has not been attributed to PMIC watchdog behavior without further
measurements.

## F.20 physical control

With USB disconnected, the operator shut down through F.20's power menu,
then held power for about 3 seconds and observed vibration/the realme logo
before reconnecting USB. ADB subsequently verified F.20/4.19.157, boot
completion and new boot `6783f265-27da-49aa-9e2c-286c62f18d69`; both reported
boot-reason properties were `shutdown,userrequested`. Thus disconnected
power-key startup works in the stock control. This does not prove that the
earlier 6.18 `reboot -p` completed its shutdown sequence.
[Operator and device evidence](../build/device/m1-f20-power-control-2026-11-14.json)

A PDC-only control is prepared with `rebuild_m1_usb_trial.py --autonomous-ufs
--pdc-only`. Before and after applying OEM overlay 17, its checker requires
that every node/property except PDC's compatible remains identical. It checks
the captured register ranges, GIC parent and SPMI PDC pin 1 (GIC SPI 481).
Synthetic negative tests reject changed TLMM, routing, IRQ or status. The
actual retained board tree also passed both checks. The subsequent trial 33 below records the physical result. This compatible
change does not supply the missing PON poweroff driver.
[Offline validation](../build/device/m1-pdc-only-preflight-2026-11-14.json)

The pinned upstream [PM8150 tree](https://android.googlesource.com/kernel/common/+/ecdaacc9a0ee87eaf9544e1836d86bd9d590312e/arch/arm64/boot/dts/qcom/pm8150.dtsi)
uses a pm8998-compatible PON parent at 0x800 and a pm8941-compatible power-key
child on SID 0, peripheral 8, IRQ 0. The power-key driver registers the notifier
that selects shutdown versus warm/hard reset; its mere presence in a DT source
is not evidence that it bound or programmed this handset. The next PDC-only
trial additionally publishes read-only deferred-probe, SPMI device/driver and
early power-log snapshots to scratch data, before policy installation. Missing
optional snapshot entries do not stop Android boot. No PON conversion or new
poweroff driver is included in that control.

## Separate PON/poweroff compile candidate

The optional `pon_power` workflow input adds `INPUT_PM8941_PWRKEY` and
`POWER_RESET_MSM`. A narrow patch lets the upstream pm8941 power-key driver
use the measured legacy primary PON node directly: Kona MTP, dtsi_no 20607,
SPMI SID 0, PON reg `<0x800 0x100>`, system-reset flag and the exact two
captured interrupt specifiers are required. Probe also requires GEN2_PRIMARY
subtype. Secondary/modem PON nodes are rejected. This avoids replacing the
original DTBO during M1; M2 removes the alias in favor of project source DTs.

The compatibility profile preserves firmware pull-up and hardware debounce
settings, reads the hardware debounce for software filtering, and uses the
existing upstream PS_HOLD notifier on explicit shutdown/restart. It does not
configure the PMIC watchdog or write reboot-reason spare registers. Its
legacy notifier runs after the board SCM EDL notifier, so the warm reset type
is selected before programming PON. The
upstream MSM poweroff driver maps the measured first PS_HOLD resource at
0xc264000 (4 bytes); the second resource at 0x1fd3000 remains the existing
EDL selector. This is a separate compile candidate, not included in trials
31/32 and not yet a hardware-verified shutdown fix. First qualify PDC/SPMI
with the existing kernel, then inspect the new driver binding and notifier
logs before repeating the physical disconnected start.

## Trial 33: PDC-only binding verified on the handset

The existing kernel (`fce98221...`) and original DTBO booted with only PDC's
compatible changed in the selected base tree. Boot
`78202cbf-6e86-46fd-bb95-24e2d731b27c` passed local ADB retention, enforcing,
verified UFS system/vendor, maintenance, a 193.891-second soak and the 1 MiB
hash-checked transfer. It remains running GSI.

SPMI no longer appears among deferred probes. Addresses 00, 01, 02, 03, 04,
05, 08, 09, 0a and 0b enumerate; eight bind pmic-spmi, including primary SID
00. SID 03 and 09 have no driver in the early snapshot. The primary PON and
PS_HOLD platform nodes still have no driver, as expected with the current
kernel configuration. This establishes the dependency needed for the separate
PON/poweroff candidate; it does not establish shutdown or disconnected start.
[Physical evidence](../build/device/m1-pdc-spmi-33-2026-11-14.json)

For the next physical shutdown, use `schedule_gsi_poweroff.py
--require-power-drivers`: it requires a same-boot snapshot, primary PMIC
binding, the primary pm8941 PON driver, MSM PS_HOLD binding and a successful
GEN2_PRIMARY revision/subtype read. A stale or unbound snapshot is rejected
before any shutdown is scheduled.

`fetch_current_kernel.py` downloads only the needed artifact members, checks
the successful pinned workflow/commit, source patch digests and dist SHA256SUMS
(including the decompressed Image), then replaces the current kernel inputs.
It does not retain a full archive or an old image version. Its verify-only
path was exercised against the existing successful kernel artifact and
reproduced the current Image hash without replacing inputs. Whole-archive
digest verification is explicitly not claimed for range downloads.
