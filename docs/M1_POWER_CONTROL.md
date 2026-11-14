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
