# RMX2072 UFS host and UniPro

Linux 6.18.32 on the F.20 handset bound `1d84000.ufs` to `ufshcd-qcom` with the native QMP PHY. The accepted boot completed UIC command `0x16` in 21.227 ms with result zero. A return probe on `ufshcd_link_startup` also reported zero. The UFS 3.0 device exposed six ordinary SCSI LUNs. Each matched the F.20 capacity and passed a 4 KiB read with its block device set read-only. The diagnostic ran entirely from RAM. See the [physical trial data and image hashes](../build/device/ufs-unipro-2026-11-09.json).

| Profile | UFS reference | Negotiated link | Observation |
| --- | --- | --- | --- |
| First G3 | 9.6 MHz reported by Linux | HS-G3 B, two lanes | Link startup succeeded. UIC errors followed. The first boot disconnected during a descriptor query. A second boot captured the completion trace. |
| Accepted G1 | 19.2 MHz | HS-G1 B, two lanes | All six disks read successfully. The idle sample reported HIBERN8 and device SLEEP. |
| G3 retest | 19.2 MHz | HS-G3 B, two lanes | Link startup succeeded again. UIC errors recurred and no SCSI disks appeared during the observation. |

The UFS profile supplies the SM8250 RPMh clock controller with a 38.4 MHz oscillator. Its divide-by-two CXO supplies the 19.2 MHz reference. The accepted profile pins the AXI and UniPro core clocks at 37.5 MHz. Five native interconnect providers serve the storage-to-DDR and CPU-to-UFS paths. The HBA attaches to the apps SMMU with stream IDs `0xe0` and `0x4e0`.

## Reproduce the accepted test

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

The accepted test covers warm link startup and short reads. Device reset GPIO 180, cold power-on, sustained I/O, inline encryption and Android mounts remain untested. HS-G3 currently fails during enumeration with the fixed clocks above. A comparison with the full SM8250 OPP table and corresponding RPMh power votes would test whether clock and voltage scaling contribute.
