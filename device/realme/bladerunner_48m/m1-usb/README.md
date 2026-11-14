# M1 authenticated USB trial

This optional engineering vendor profile uses the GSI's adbd and generic USB
property rules. It creates `g1` and `ffs.adb`, mounts FunctionFS, and releases
the diagnostic `rmxdiag` UDC before binding ADB. The measured controller is
`a600000.usb`. The test uses Google-compatible ADB USB identification and MS OS
WinUSB descriptors; it is not a shipping USB identity allocation.

`rmx-m1-guard.c` builds both the init service and its small control entry point.
The init service owns `/dev/watchdog`; the control entry point runs through
Android's existing `vendor_shell` transition. The socket accepts only UID 2000
and commands containing the current kernel boot ID. It grants no root shell,
UFS write access or reboot capability. The GSI's neverallow checks remain on.

The host public key is added only to the live copy of the same scratch data
seed, with `adb_keys_file` labels. Neither the private key nor the public key
contents belong in Git. The GSI retains `ro.adb.secure=1` and `ro.debuggable=0`.

## Watchdog sequence

1. Before policy installation, the witness arms the watchdog for 30 seconds,
   cancels the old diagnostic return timer, then releases its descriptor without
   magic close. The watchdog remains armed until Android reopens it.
2. The init service opens the watchdog and sets 30 seconds. It feeds for at most
   150 seconds while waiting for local ADB readiness or an authenticated host test.
   With no host lease, 30 continuous seconds of `adbd=running` and configured
   ADB changes the guard to `retained` locally. This does not prove an authenticated
   USB session; the later host acceptance remains separate. Retained mode stops
   feeding if local USB readiness is lost for 30 seconds. Cable absence alone
   does not change the configured USB state.
3. The host checks API 37, the exact kernel, boot ID, enforcing, PID 1, UFS mounts
   and running adbd plus a responding guardian. Autonomous acceptance first waits for local retention
   without sending keep commands. Production GSI shell cannot
   read the vendor init service property or `sysfs_dm`; use the independently
   captured same-boot UFS witness and matching live mounts in that case. Never
   accept a conflicting graph, mismatched boot, mapper or verity chain.
   A matching `keep` starts a 45-second renewable
   lease. Loss of the host during this phase expires the lease.
4. After a 190-second ADB soak and hash-checked scratch-volume file transfer,
   `retain` commits continuous watchdog feeding.
   The guardian also enforces at least 180 seconds since the first ACK.
5. A failed trial or an explicit matching `rollback` stops feeding. The hardware
   reset boots the recovery path; it exposes diagnostic pstore for 90 seconds
   and then enters EDL itself. The attached host restores the verified original boot/super. Original userdata is not
   mounted or formatted. Retained operation still uses volatile data/metadata.

The pinned KPSS watchdog limits its counter to 0xFFFFF ticks; with the measured
32764 Hz clock its maximum timeout is 32 seconds. Trial 26 rejected the initial
120-second request before policy installation. Both owners now request 30
seconds; long host windows are implemented by periodic feeding.

Trial 27 passed authenticated shell access, a 192.563-second lease soak,
1 MiB push/pull verification and wrong-boot command rejection. It remains in
GSI with state `retained`. The file smoke was run separately before and after
retention on that boot; future runs perform it inside the retention gate.
The host validator was corrected during this trial for production-GSI access
restrictions. Trial 26 validated pre-policy failure recovery; missing-ACK and
expired-lease fault injection for the new guard has not yet been run. See
[the actual trial records](../../../../build/device/m1-gsi-adb-2026-11-14.json).

## Rebuild and run

Use `scripts/build/rebuild_m1_usb_trial.py --workspace WORK --ndk NDK
--adb-public-key HOST_PUBLIC_KEY --trial ufs-host-g3-gsi17-firststage-ufs-NN`.
On Windows, make OpenSSL available on PATH and set MKE2FS_CONFIG to the Android
platform-tools mke2fs.conf. Inputs must already match the pinned kernel, GSI,
original recovery set and scratch seeds. The script replaces only the current
candidate outputs; partition images and signing keys stay outside the checkout.

Run `scripts/device_audit/run_ufs_trial.py --workspace WORK --trial
ufs-host-g3-gsi17-firststage-ufs-NN --retain-gsi`. This first verifies and writes
the candidate, reads it back independently, and retains GSI only after the
same-boot authentication and watchdog soak. For an explicit later return, use
ADB to execute `/vendor/bin/hw/rmx-m1-control --rollback CURRENT_BOOT_ID`, then
use the existing recovery runner in `--restore-only` mode after EDL is ready.

The USB layout follows the AOSP FunctionFS/configfs integration in
[Google gs201](https://android.googlesource.com/device/google/gs201/+/5875d29f/conf/init.gs201.usb.rc).
Its actual service and permission requirements are checked against the pinned
CP3A.260905.010 GSI. This is a warm, USB-attached engineering test, not M1 cold
boot acceptance or M2 factory-tree independence.

## Autonomous startup candidate

`rebuild_m1_usb_trial.py --autonomous-ufs` packages a startup path that invokes
the existing verified UFS first-stage handoff itself. It does not require an
enumerated diagnostic gadget. Early evidence is buffered in RAM and copied
to `/data/local/tmp/rmx-m1-boot.txt` on the same disposable data seed before
policy installation. ADB can retrieve it without initiating the handoff.
The optional temporary-key TIME probe is skipped because this profile has no
verified RTC; no host time or invented timestamp is supplied.

Trial 28 exposed a collision between the old native-entry probe and the pmsg
journal. The autonomous packer now uses the non-writing alignment wrapper and
skips entry-carry; the kernel and selected DTB are unchanged. A bounded binary
parser rejects damaged last records instead of silently accepting an empty
grep result. Previous console/pmsg are also copied onto scratch data for ADB
inspection. These fixes require a new hardware reset qualification.

The supervisor and guard write boot-bound state markers into reserved-RAM
pmsg. On a subsequent boot, a pending/failed attempt selects a diagnostic
capture window and then EDL rather than retrying Android indefinitely. A
retained marker permits normal startup. This is reserved-RAM recovery state,
not a persistent UFS boot counter. The hardware power-off/cold-start behavior
still requires physical measurement.

An authenticated `--expire-lease CURRENT_BOOT_ID` command changes a retained
guard back to a 45-second lease for deliberate host-loss fault injection.
Without a renewal, feeding stops and the 30-second hardware watchdog expires.
Trial 27's earlier stop-feeding injection already recorded a kernel pretimeout,
a new diagnostic boot and verified F.20 recovery; that test needed a repeated
host EDL request. The observer now flushes and drains that serial request.
[Watchdog control evidence](../../../../build/device/m1-watchdog-expiry-2026-11-14.json)

Use `--reuse-super` only when system and signed vendor are unchanged. The
builder checks their manifests, hashes and every existing candidate chunk
before reusing them for a ramdisk-only change.

## Complete fault recovery qualification

Trial 29 reached EDL autonomously, but EDL disappeared before a late-started
restore runner could capture Sahara. The complete recovery was therefore not
accepted; a manual ADB EDL request allowed the waiting runner to restore F.20.
The recovered original super, boot, DTBO, both LP slots and boot completion
were fully verified.

The next candidate tests explicit AP-watchdog disarming only in the recovery
ramdisk. Trial 30 passed its 194-second GSI check, but pre-injection inspection
found that WATCHDOG_SYSFS is disabled; its state/nowayout file checks could
never pass, so no fault was injected. Trial 31 checks the exact AP device and
GETSUPPORT identity/options, then requires SETOPTIONS(DISABLECARD) success.
The ioctl enforces nowayout itself. Recovery waits another 60 seconds without
feeding before EDL; the observer captures the boot-bound disarm result.
It does not change the failed Android guard's stop-feeding behavior.
The pinned qcom-wdt driver adopts running firmware watchdogs and has no
shutdown callback; whether that explains the transient EDL needs measurement.

Before injecting expiry, start the restore runner with `--restore-only` and
`--recovery-gate PATH` and wait for its `recovery-ready.json`. Run the fault
observer with the same gate, `--edl-hold-seconds 45` and
`--require-watchdog-disarm`. Only after continuous
EDL observation does it atomically release the prepared restore runner.
Require the independent original readbacks and F.20 boot verification too.
A fault or vanished EDL does not release the gate; inspect the device and
record any explicit manual recovery separately. Use fresh trial record paths.

For a ramdisk/kernel-only update from retained GSI, use
`run_ufs_trial.py --retain-gsi --boot-only-from PREVIOUS_RECORD`. It requires
identical super and scratch manifests, a completed 190-second previous soak
and live same-boot acceptance. EDL verifies the previous boot, original DTBO
and every candidate super chunk before programming only boot. The new boot
and unchanged DTBO are read back before startup. Failure restores the verified
original recovery set. This avoids rewriting an unchanged system/vendor.

Trial 31 exposed another recovery-only precondition: diagnostic `/dev` is
tmpfs and no ueventd creates watchdog0. Android's device node does not imply
that the next diagnostic boot has it. The helper now reads the exact class
device number, creates a character node only when absent, rejects a mismatched
or symlink node, and uses the same checked disable ioctl. Manually creating
the node in trial 31 proved GETSUPPORT/DISABLECARD success, but EDL still
disappeared. That intervention is not automatic-recovery acceptance.

For complete recovery with a prepared computer, trial 32 uses
`--capture-next-edl --require-watchdog-disarm --edl-hold-seconds 0`. After
correlating the expired boot, recovery boot, 29-second kernel pretimeout and
disarm result, the observer releases the restore runner to wait for the next
EDL enumeration. It never requests reboot. Full original readbacks and F.20
boot are still mandatory. This tests immediate automatic capture; it does not
claim that unattended EDL remains stable for 45 seconds or that F.20 can
restore without a computer. The longer EDL hold remains a separate failed
check.
