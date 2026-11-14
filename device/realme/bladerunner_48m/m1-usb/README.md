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
   150 seconds while waiting for the authenticated host.
3. The host checks API 37, the exact kernel, boot ID, enforcing, PID 1, UFS mounts
   and running adbd/guardian. A matching `keep` starts a 45-second renewable
   lease. Loss of the host during this phase expires the lease.
4. After a 190-second ADB soak, `retain` commits continuous watchdog feeding.
   The guardian also enforces at least 180 seconds since the first ACK.
5. A failed trial or an explicit matching `rollback` stops feeding. The hardware
   reset boots the diagnostic ramdisk; the attached host collects pstore, enters
   EDL and restores the verified original boot/super. Original userdata is not
   mounted or formatted. Retained operation still uses volatile data/metadata.

The pinned KPSS watchdog limits its counter to 0xFFFFF ticks; with the measured
32764 Hz clock its maximum timeout is 32 seconds. Trial 26 rejected the initial
120-second request before policy installation. Both owners now request 30
seconds; long host windows are implemented by periodic feeding.

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
