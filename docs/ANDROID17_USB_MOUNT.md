# Android 17 over USB on RMX2072

Linux 6.18.32 mounted Google's CP3A.260905.010 ARM64 + GMS system image twice on the handset. The mounted build properties identified Android 17, API 37 and build 16176746. The handset computed SHA-256 hashes of `system/build.prop`, `system/etc/init/hw/init.rc` and `system/system_ext/etc/build.prop`. All matched files independently extracted from the original image. The GSI stayed on the workstation. See the [reference](../build/device/gsi17-mount-reference.json) and [hardware results](../build/device/gsi17-usb-mount-2026-11-10.json).

## Data path and observed limits

The host opens the 3,953,213,440-byte image read-only, checks its complete SHA-256 and verifies its embedded RSA vbmeta signature against the pinned signer and hashtree descriptor. Kernel reads reach the adapter through a read-only dm-user mapping of all 7,721,120 sectors. The adapter requests at most 4 KiB per USB ACM message and checks a CRC on the response before completing the bio. A separate dm-verity target authenticates the ext4 data blocks against the pinned SHA-256 root. Both boots also read the last 4 KiB of the backing image and matched the host's hash.

| Trial | Kernel observation | Host reads |
| --- | --- | ---: |
| Mount only | ext4 mounted read-only with journal replay and execution disabled. Three file hashes matched. | 85 requests, 348,160 bytes |
| Userspace | ext4 mounted read-only with execution enabled. GSI toybox reported the running 6.18.32 kernel and read the same build properties. | 1,011 requests, 4,141,056 bytes |

The userspace trial ran `/system/bin/toybox` through the image's `/system/bin/bootstrap/linker64` inside a chroot, with read-only proc and an explicit library search path. `linker64 --list /system/bin/init` returned zero and listed 31 libraries under `/system`. The linker reported that `/linkerconfig/ld.config.txt` had not been generated. The diagnostic init remained PID 1. The USB test did not start apexd, load F.20 vendor HALs or boot the Android framework.

F.20's system fstab entries name Q, R and S GSI public keys. All three key files in the F.20 reader boot ramdisk differ from this GSI's embedded signer. The diagnostic verified the specific downloaded image using its pinned identity. A first-stage integration needs an explicit trust path for that key and the stock vendor/odm chains. The FCM, VNDK and persistent storage constraints are documented in the [GSI preflight](GSI_PREFLIGHT_2026-11-06.md).

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
