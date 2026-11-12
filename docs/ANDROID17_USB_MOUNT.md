# Android 17 over USB on RMX2072

## Project vendor and PID 1 policy setup

Two physical boots on 6.18.32 switched the root to the CP3A.260905.010 GSI and mounted the project vendor at `/vendor`. First-stage init issued both read-only ext4 mounts. The observed `MS_MOVE` from `/system` to `/` returned zero. PID 1 then executed the GSI's `/system/bin/init selinux_setup`; its SHA-256 matched the executable extracted from the pinned GSI. Its mount table showed `254:1` (USB-backed dm-verity) at `/` and `7:0` (RAM-backed loop0) at `/vendor`. The mounted vendor fstab matched the ramdisk copy. See the [two handset records and F.20 recovery readbacks](../build/device/gsi17-project-vendor-2026-11-11.json).

The first run exposed a missing vendor genfs version. Init selected 202404 and skipped that optional CIL. The revised vendor selects 202604, which the GSI supplies, and uses the same version spelling in its VINTF manifest. On the second run init logged `Opening SELinux policy` at 36.944 s, selected `plat_sepolicy_genfs_202604.cil` at 37.463 s and logged `Loading SELinux policy` at 47.711 s. The observer stopped the process at the opening of the kernel load interface. A separate invocation of the GSI's compiler read the mounted policy inputs with neverallow checking enabled, returned zero and produced the policy digest in the hardware record. Kernel installation, enforcing mode, second-stage init, VINTF compatibility and Android ADB remain untested.

The [vendor source](../device/realme/bladerunner_48m/m1-vendor) contains the USB fixture fstab, board init and ueventd configuration, a device manifest and split SELinux inputs. It declares no HAL instances. The 2 MiB image is identified by content hash and embedded in the test ramdisk. It has no vendor AVB signature. The GSI uses the existing pinned signer and dm-verity path.

On Linux, `python scripts/build/build_m1_vendor.py --output PRIVATE/vendor` uses e2fsprogs to create the filesystem, check it and read back its files and SELinux labels. Set `PRIVATE` to a directory outside the checkout. CI compares two builds byte-for-byte. Add `--project-vendor PRIVATE/vendor` to the first-stage ramdisk build described below and run the host with `--project-vendor-report PRIVATE/vendor/vendor.json` in place of `--first-stage`.

### Host package and record replay

The Windows packaging helper accepts the two private input-cache roots used for these trials. The current work cache supplies the G3 headers, DT runtime DLLs, watchdog control boot, 6.18 Image and provenance, APK cache, USB reader, first-stage init and observer. The prior cache supplies libfdt/dtc, static control tools and the entry probe; the F.20 DTBO comes from its sibling recovery kit. Supply a new private output directory. Replaying vendor trial 02 with its inputs reproduced the full boot partition image SHA-256 `afbb119e162333dfbf40f27dccb76c48f830c5e25184ac3382a4dfedfe8060d6`. The final CI vendor image also matched the 2 MiB image used on that handset boot. [CI run](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/43045844770)

```powershell
$trial = 'ufs-host-g3-gsi17-firststage-vendor-02'
./scripts/build/build_m1_trial.ps1 -Trial $trial -WorkDirectory $workCache -PriorWorkDirectory $priorCache -NdkDirectory $ndk -ProjectVendor $vendorDir -OutputDirectory $newPrivateOutput
```

During a scheduled handset trial, `observe_gsi17.py` runs the GSI server, writes the USB transcript and requests software EDL for the local restore harness. For an offline replay after restoration, `record_m1_vendor.py` checks the saved transcript, vendor image, software-return report and full boot/DTBO readbacks at four points. It reads the F.20 display ID, completion flag and boot ID from a three-line capture and writes one trial entry to a new JSON file. Review the entry for the milestone record. The two archived timelines use the workstation's Asia/Shanghai clock.

```powershell
python scripts/device_audit/observe_gsi17.py --image $gsi --trial $trial --project-vendor-report "$vendorDir/vendor.json" --output "$workCache/$trial-live"
python scripts/device_audit/record_m1_vendor.py --work $workCache --trial $trial --vendor-dir $vendorDir --restored $restoredText --image-build-run 43044877414 --output $newTrialJson
```

## M1 first-stage handoff on November 11

On the physical RMX2072, Android 17 first-stage `/init` ran as global PID 1 on Linux 6.18.32. Its first mount was a tmpfs on `/dev`. Its first partition mount attached the USB-backed CP3A.260905.010 GSI to `/system`. Both syscalls returned zero. The observer stopped PID 1 on return from the partition mount and read its executable and mount table through the diagnostic namespace. See the [trial evidence, hashes and separate F.20 recovery](../build/device/gsi17-first-stage-2026-11-11.json).

```text
exec_pid=1 path=/init staged_inode_match=1
mount_pid=1 source=tmpfs target=/dev fs=tmpfs flags=0x2 rc=0
mount_pid=1 source=/dev/block/dm-1 target=/system fs=ext4 flags=0x1 rc=0
pid1_mountinfo=47 38 254:1 / /system ro,relatime - ext4 /dev/block/dm-1 ro,norecovery
```

The static first-stage executable came from the first cpio archive in Google's API 37 ARM64 emulator ramdisk, build CE2A.260420.051.A3. The SDK package and GSI have separate build identities. The host verified the GSI signature, signer and hashtree descriptor before serving it. The diagnostic created the dm-verity target and supplied its block device to the board fstab. Android created its own device nodes and issued the mount. All six internal UFS LUNs and their partitions were read-only. This checkpoint used the stock-derived G3 device tree and a USB host. The later [project vendor trials](#project-vendor-and-pid-1-policy-setup) added the vendor mount. Second-stage init and a disconnected UFS boot remain open.

To reproduce, extract `init` from the first legacy-LZ4 cpio in `arm64-v8a/ramdisk.img` and verify the [pinned ramdisk and ELF](../build/device/android17-first-stage-source.json). Compile the observer with `scripts/build/build_gsi_usb_reader.py --ndk <ndk> --first-stage-witness --output <observer>`. Add `--android-first-stage <init> --first-stage-witness <observer>` to the G3 USB reader ramdisk build, select a `ufs-host-g3-gsi17-firststage-*` trial ID and enable the EDL timer. Use `serve_gsi_usb.py --first-stage` with the pinned GSI. After the transcript is saved, the existing `usb_edl_return.py --mode command` procedure returns the phone to the restore harness.

## Earlier USB mount trials

Linux 6.18.32 mounted Google's CP3A.260905.010 ARM64 + GMS system image twice on the handset. The mounted build properties identified Android 17, API 37 and build 16176746. The handset computed SHA-256 hashes of `system/build.prop`, `system/etc/init/hw/init.rc` and `system/system_ext/etc/build.prop`. All matched files independently extracted from the original image. The GSI stayed on the workstation. See the [reference](../build/device/gsi17-mount-reference.json) and [hardware results](../build/device/gsi17-usb-mount-2026-11-10.json).

## Data path and observed limits

The host opens the 3,953,213,440-byte image read-only, checks its complete SHA-256 and verifies its embedded RSA vbmeta signature against the pinned signer and hashtree descriptor. Kernel reads reach the adapter through a read-only dm-user mapping of all 7,721,120 sectors. The adapter requests at most 4 KiB per USB ACM message and checks a CRC on the response before completing the bio. A separate dm-verity target authenticates the ext4 data blocks against the pinned SHA-256 root. Both boots also read the last 4 KiB of the backing image and matched the host's hash.

| Trial | Kernel observation | Host reads |
| --- | --- | ---: |
| Mount only | ext4 mounted read-only with journal replay and execution disabled. Three file hashes matched. | 85 requests, 348,160 bytes |
| Userspace | ext4 mounted read-only with execution enabled. GSI toybox reported the running 6.18.32 kernel and read the same build properties. | 1,011 requests, 4,141,056 bytes |

The userspace trial ran `/system/bin/toybox` through the image's `/system/bin/bootstrap/linker64` inside a chroot, with read-only proc and an explicit library search path. `linker64 --list /system/bin/init` returned zero and listed 31 libraries under `/system`. The linker reported that `/linkerconfig/ld.config.txt` had not been generated. The diagnostic init remained PID 1. The USB test did not start apexd, load F.20 vendor HALs or boot the Android framework.

F.20's system fstab entries name Q, R and S GSI public keys. All three key files in the F.20 reader boot ramdisk differ from this GSI's embedded signer. The diagnostic verified the specific downloaded image using its pinned identity. The combined stock comparison used the F.20 vendor/ODM chains. The target needs explicit trust paths for the selected GSI and the project-built vendor. The FCM, VNDK and persistent storage constraints are documented in the [GSI preflight](GSI_PREFLIGHT_2026-11-06.md).

## Replay

1. Obtain the exact [selected Google GSI](../build/gsi.json) and keep the extracted raw `system.img` outside the checkout. The diagnostic boot contains the reference hashes. The separate image supplies the filesystem bytes.
2. Run `python scripts/build/build_gsi_usb_reader.py --ndk PATH_TO_NDK --output PRIVATE/gsi-usb-reader`. The physical build used Android NDK 28.2.13676358 with API 21 and static zlib. Prepare the pinned dmsetup runtime as in the [super diagnostic](SUPER_READONLY.md#replay).
3. Reuse the verified G3 kernel and G3 DT overlay. Build the ramdisk with the existing BusyBox, EDL helper, entry carrier, `--ufs-host-g3-test --super-tools-apks PRIVATE_APK_CACHE --gsi-usb-reader PRIVATE/gsi-usb-reader`. For the accepted image, use `--trial-id ufs-host-g3-gsi17-02 --gadget-bind-delay 20 --return-to-edl-after 360`.
4. With the established F.20 backup and 9008 restoration harness in place, boot the diagnostic. On the workstation use Python 3.11 or later with pyserial and cryptography:

```sh
python scripts/device_audit/serve_gsi_usb.py --image PRIVATE/system.img \
    --trial ufs-host-g3-gsi17-02 --output PRIVATE/new-run --userspace
```

   Omitting `--userspace` selects the noexec mount-only probe. The host requires one matching ACM and verifies the board, kernel and trial before starting the mount. `result.json` records served byte counts and `mount.txt` records the handset's mount result, file hashes, linker output where applicable and cleanup status.

5. Return through `usb_edl_return.py --mode command` with the current trial ID and use the recovery harness to restore F.20. Both trials verified the complete candidate boot and original DTBO at each Firehose stage. Android came back on 4.19.157-perf+. Its LP metadata, active linear tables and three logical-device hashes matched the previous F.20 baseline.

## Combined system, vendor and ODM

The combined diagnostic starts the UFS host on the running 6.18 kernel. It checks the F.20 LP prefix, reads the three physical vbmeta partitions and creates read-only linear and verity devices. The GSI supplies the root filesystem over USB. Its `/vendor` and `/odm` mountpoints receive the F.20 EROFS mounts. The stock system is mounted elsewhere in the diagnostic so it can supply the original F.20 platform mapping for a comparison.

F.20's ODM fstab entries use `/vendor/etc/oplus_avb.pubkey`. Its active logical ODM has its own signed AVB footer covering 928,215,040 data bytes. The ODM descriptor in top-level F.20 vbmeta describes a different size and root. The workstation verified the embedded RSA signature against the actual vendor key and compared the whole verity table to the one used by the F.20 kernel. The handset checked the vendor key, the complete footer and metadata pages, the whole verified ODM device hash and its mounted file samples. See the [ODM reference](../build/device/f20-odm-verity-reference.json).

To replay on the project handset, verify the connected F.20 first with `python scripts/device_audit/check_verity.py verify-odm --serial SERIAL --reference build/device/f20-odm-verity-reference.json`. Build the additional ARM64 launcher with `python scripts/build/build_gsi_usb_reader.py --ndk PATH_TO_NDK --init-probe --output PRIVATE/gsi-init-probe`. Add `--f20-verity --gsi-init-probe PRIVATE/gsi-init-probe` to the original ramdisk build, using `--trial-id ufs-host-g3-gsi17-06 --return-to-edl-after 410`. Run the USB host with `--combined`.

The probe invokes the original GSI `/system/bin/init selinux_setup` as UID/GID 65534 inside the combined root. The diagnostic remains PID 1. A private RAM-backed `/dev` holds the init log and temporary outputs. The child has read-only proc, no mapper control and no mounted SELinux filesystem. To let this UID execute the GSI's root-only compiler, the replay binds a byte-identical, executable RAM copy over `/system/bin/secilc`. The second invocation also adds the two F.20 platform mapping files in a read-only RAM directory. These are temporary mount changes for comparing the compiler inputs.

Both invocations saw different platform policy IDs in the GSI and the ODM precompiled policy. With the original GSI mapping directory, init's compiler exited 255 opening `/system/etc/selinux/mapping/30.0.cil`. The second invocation used F.20's `30.0.cil` and `30.0.compat.cil` in addition to the original GSI files. Init reached `Loading SELinux policy` and its load call failed with ENOENT in the isolated root. The original diagnostic kernel policy remained in effect.

An independent compiler invocation included the GSI platform, system_ext and product policies, the two stock platform mappings and F.20's vendor versioned public and vendor policies. It kept neverallow checking enabled. The two compile modes answer different questions. Init's boot compiler and its precompiled-policy selection are described in [AOSP init's SELinux implementation](https://android.googlesource.com/platform/system/core/+/refs/heads/main/init/selinux.cpp).

The independent compile exited 255 with 299 neverallow reports across 262 distinct reported rule locations. Of the 299 reports, 92 point to the F.20 versioned public CIL and 207 point to platform policy sources. The first conflicting allow is attributed to F.20's versioned public CIL in 188 reports. The archived index includes examples involving vold Binder calls, gsid service lookup and apexd metadata access. A single rule or attribute change may affect several reports. See the [hardware evidence and complete location index](../build/device/gsi17-init-policy-2026-11-11.json).

The first trial identified the root-only compiler permission. The next isolated a missing file_contexts output sink in the test environment. A third trial reached policy loading, but its truncated console excerpt ran into the cleanup marker. The accepted fourth trial supplied a private null character device for file_contexts, recorded a compact conflict index and verified the complete USB transcript against its on-device SHA-256. All four boots returned to 9008 by software and restored the full F.20 logging boot and original DTBO. Android completed startup after each recovery.

Commit `e8f276a` contains the ramdisk sources used for the accepted image. Its published index records the first conflicting allow's source location. Later ramdisks also print the generated CIL location for that allow.

The diagnostic mounted the filesystems before running init. Init also logged missing mapper control for `system_ext` and `product`. The experiment used the GSI's bundled system_ext and product contents. Actual first-stage discovery of F.20 partitions, loading and enforcing the combined policy on the kernel, second-stage init, APEX and framework startup still require separate evidence.
