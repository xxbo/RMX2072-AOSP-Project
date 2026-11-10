# RMX2072 UFS host and UniPro

Linux 6.18.32 on the F.20 handset bound `1d84000.ufs` to `ufshcd-qcom` with the native QMP PHY. The initial G1 boot completed UIC command `0x16` in 21.227 ms with result zero. A return probe on `ufshcd_link_startup` also reported zero. The UFS 3.0 device exposed six ordinary SCSI LUNs. Each matched the F.20 capacity and passed a 4 KiB read with its block device set read-only. The diagnostic ran entirely from RAM. See the [G1 trial data and image hashes](../build/device/ufs-unipro-2026-11-09.json).

| Profile | UFS reference | Negotiated link | Observation |
| --- | --- | --- | --- |
| First G3 | 9.6 MHz reported by Linux | HS-G3 B, two lanes | Link startup succeeded. UIC errors followed. The first boot disconnected during a descriptor query. A second boot captured the completion trace. |
| Accepted G1 | 19.2 MHz | HS-G1 B, two lanes | All six disks read successfully. The idle sample reported HIBERN8 and device SLEEP. |
| G3 retest | 19.2 MHz | HS-G3 B, two lanes | Link startup succeeded again. UIC errors recurred and no SCSI disks appeared during the observation. |
| G3 with 300 MHz available | 19.2 MHz | HS-G3 B, two lanes | Both warm boots enumerated all six LUNs and completed direct reads at 300 MHz. |

The UFS profile supplies the SM8250 RPMh clock controller with a 38.4 MHz oscillator. Its divide-by-two CXO supplies the 19.2 MHz reference. Five native interconnect providers serve the storage-to-DDR and CPU-to-UFS paths. The HBA attaches to the apps SMMU with stream IDs `0xe0` and `0x4e0`.

## Reproduce the G1 fallback

1. Compile `rmx2072-ufs-host.dts` using the pinned kernel headers. Apply the DT overlay with `prepare_legacy_tree_patch.py --ufs-host-control` to the known watchdog baseline and original F.20 DTBO. The packager verifies the graph before and after OEM entry 17. The legacy host keeps its original OEM symbol and receives a parked compatible string.
2. Build the diagnostic ramdisk with `--ufs-host-test --trial-id ufs-host-03 --gadget-bind-delay 20 --return-to-edl-after 260` and the existing verified BusyBox, reboot helper and entry carrier. Use the same kernel Image as the PHY trial. The packaged boot SHA-256 is recorded in the linked data.
3. After ACM is configured, run each stage and capture its result. Arm tracing before populating the host. Wait for the SCSI scan after `start` and issue descriptor queries once disks appear.

```sh
/bin/ufs-host-test preflight
/bin/ufs-host-test fabric
/bin/ufs-host-test phy
/bin/ufs-host-test arm
/bin/ufs-host-test start
/bin/ufs-host-test trace
/bin/ufs-host-test info
/bin/ufs-host-test disks
/bin/ufs-host-test descriptor
```

4. Use `usb_edl_return.py --mode command --trial ufs-host-03` with its output path to request EDL over ACM. All three physical profiles returned to Qualcomm 9008 without the volume keys. Firehose verified the complete F.20 logging-reader boot and stock DTBO after restoration. Android reported F.20, kernel 4.19.157-perf+ and completed boot.

## G3 read and wake validation

F.20 reported both 37.5 MHz and 300 MHz in its UFS devfreq transition history. Comparing the effective project base with the failed 19.2 MHz G3 control found one changed property. The two maximum rates in `freq-table-hz` increased from 37.5 to 300 MHz for AXI and the UniPro core. The two rates were tested together. The trials preserved the PHY, core Image, regulator wiring, reference clock and original OEM DTBO. See the [physical measurements and hashes](../build/device/ufs-g3-2026-11-10.json).

Use `rmx2072-ufs-host-g3.dts`, `prepare_legacy_tree_patch.py --ufs-host-g3-control` and `build_diag_ramdisk.py --ufs-host-g3-test`. For the recorded second boot, the trial ID is `ufs-host-g3-02`, ACM bind delay is 20 seconds and EDL timeout is 260 seconds. Use the same verified tools, watchdog source image and kernel as the G1 profile. After ACM connects, run the following from the diagnostic shell.

```sh
/bin/ufs-host-test preflight
/bin/ufs-host-test fabric
/bin/ufs-host-test phy
/bin/ufs-host-test arm
/bin/ufs-g3-test arm-g3
/bin/ufs-host-test start
/bin/ufs-host-test trace
# Wait for all six SCSI disks.
/bin/ufs-host-test disks
/bin/ufs-host-test descriptor
/bin/ufs-g3-test read-g3
/bin/ufs-g3-test wake
/bin/ufs-g3-test gpt
```

The read stage temporarily holds the high clock state and checks gear, lane count and Rate B. Two 1 MiB direct reads on each LUN and a further 64 MiB direct read on LUN 0 produced the expected sector-count increases in both boots. The stage restores clock scaling and runtime PM. On the second boot, three additional direct reads started with the link reporting HIBERN8 and returned matching data. Each experiment recorded zero calls to `ufshcd_update_evt_hist` in its trace window.

Five GPT labels matched F.20 in partition number, starting sector and length. Through the running 6.18 block devices, the complete `boot` hash matched the packaged diagnostic and the complete `dtbo` hash matched the original. Both trials returned to 9008 through ACM and restored the F.20 logging-reader boot. Device reset GPIO 180, cold power-on, additional RPMh voltage votes, inline encryption, Android mounts and long-duration I/O remain untested.
