# M1 power control investigation

Trial 28 did not pass disconnected power-key startup. The operator reported
no response to a 2–3-second power press, then confirmed that the handset only
reacted when USB was connected. That boot contained `androidboot.mode=charger`.
Shutdown completion was not independently observed while disconnected. These
observations do not yet distinguish incomplete shutdown from a PMIC wakeup
configuration problem. [Trial evidence](../build/device/m1-autonomous-boot-2026-11-14.json)

The kernel used through trial 33 contains PSCI and the SPMI bus/PMIC infrastructure, but its
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
reproduced the then-current Image hash without replacing inputs. Whole-archive
digest verification is explicitly not claimed for range downloads.

## Trial 34: primary PON read, Android blocked by damaged prior journal

The optional PON build succeeded at source commit
`f511744555230f4632f7fd3c60f510ddd2e023f1`
([Actions run 43602623668](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/43602623668)).
Its checked Image hash is `dc41c03c967543000bd6ecafdf529c14b14174a4470ca463f3e387a6e0c64092`.
The host verified the old boot, original DTBO and all 17 unchanged candidate
super chunks, then updated only boot and read it back.

New boot `3f1921b1-d7c3-4be6-8d9f-5acd8da6d0c5` reached diagnostics. At
0.788894 seconds the driver reported primary PON revision 1, subtype 4 and
preserved pull/debounce. At 1.017985 seconds autonomous startup reported
`previous=unreadable` and selected recovery before attempting Android. The
saved prior pmsg belongs to retained trial 33, with 38 corrected bytes and
32 unrecoverable ECC blocks. Its later damaged markers correctly prevent
accepting an older valid retained record. The corruption source is unresolved.

The host observer captured evidence and explicitly requested EDL. Full F.20
restoration passed all 17 super chunk readbacks, boot/DTBO readbacks, both LP
slots, the Android-side full super digest and boot completion (boot
`5d65f047-1413-4b84-b779-3b0449ed5431`). This is not another automatic
watchdog recovery pass. GSI acceptance, PS_HOLD binding
and disconnected power-key startup were not tested on this boot. Retry this
same kernel from the stock baseline without relaxing the journal parser.
[Trial 34 evidence](../build/device/m1-pon-journal-rejection-34-2026-11-14.json)

## Trial 35: primary PON and PS_HOLD bound in Android

The same `dc41c03c...` kernel was retried from the verified F.20 baseline.
Boot `17f1c747-bf6f-4d94-a92f-059090ed9aea` reported `previous_guard=none`
and autonomously entered Android 17. Its same-boot power snapshot passed
`check_power_ready`: primary SID 0 binds pmic-spmi, the primary PON binds
pm8941-pwrkey with revision 1/subtype 4, and c264000.restart binds msm-restart.
The secondary/modem PON nodes remain unbound as intended by the narrow alias.

Local adbd readiness retained the guard before host acceptance. Enforcing,
verified UFS system/vendor and the maintenance service remain available.
The 193.781-second same-boot soak and 1 MiB hash-checked ADB transfer passed.
This verifies driver binding in GSI; physical disconnected shutdown and
power-key startup were subsequently tested below.
[Trial 35 evidence](../build/device/m1-pon-gsi-35-2026-11-14.json)

### Disconnected power-key start passed on trial 35

The driver-gated helper scheduled Android `reboot -p` with a 75-second delay.
USB disappeared before the deadline. After the deadline plus 25 seconds,
the operator pressed power with USB still disconnected and reported the
realme logo. USB remained absent for more than 90 seconds after that reply.

Reconnection immediately exposed GSI ADB with new boot
`9e7b6ff1-f413-4f79-a0df-d91d0c3f9de9`. Measured uptime places kernel startup
after the shutdown window, within the operator's power-key interval, and at
least 138.771 seconds before ADB reappeared. The guard had already retained
locally through adbd; enforcing, UFS mounts, primary PON/PS_HOLD binding,
the subsequent same-boot soak and 1 MiB transfer passed. The previous console
and pmsg were absent after this power cycle, so no shutdown notifier log is
claimed. This passes the operator-controlled disconnected-start test.

Watchdog-triggered recovery was then repeated on this changed kernel, below.
[Disconnected-start evidence](../build/device/m1-disconnected-start-35-2026-11-14.json)

### Same-kernel automatic recovery passed

The cold-start boot's injected lease expired at 44.062 seconds; ADB disappeared
at 74.500 seconds. Recovery boot `73c4dbc8-f290-4e6c-9da6-ec1b2ea54db8`
matched its expired journal and the 29-second pretimeout interval. Its helper
disabled qcom_wdt at uptime 30.98, then the phone autonomously entered EDL at
176.094 seconds. The prepared host captured Sahara without keys or any host
reboot command.

F.20 restoration passed all 17 super chunk readbacks, boot/DTBO readbacks,
both LP slots, the full Android-side super digest and boot completion (boot
`42805cb0-d7c6-49c8-95ad-62d1abfa15b4`). This qualifies the complete prepared-host
recovery on the same `dc41c03c...` kernel used for disconnected startup. It
does not qualify an unattended 45-second EDL hold or restoration without a
computer. The identical candidate is then reinstalled for continued GSI work.
[Recovery evidence](../build/device/m1-autonomous-recovery-35-2026-11-14.json)

### Final state: identical GSI candidate retained

After the recovery rehearsal, the exact same boot (`8abbd8ff...`), kernel,
system/vendor container and scratch seeds were reinstalled and independently
read back. New boot `2e26c4dd-3cab-41a9-8396-7912c0a0ffac` again passed
local retention, enforcing/API 37/PID 1/UFS identity, primary PON/PS_HOLD
binding, maintenance, a 193.687-second soak and the 1 MiB transfer. The phone
was left running this GSI; no further fault was injected into this final boot.
Only the original recovery set and current candidate image versions remain.
[Final retained GSI](../build/device/m1-gsi-retained-35-2026-11-14.json)
