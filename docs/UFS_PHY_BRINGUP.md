# RMX2072 QMP UFS PHY

## Diagnostic profile

The profile preserves the F.20 bootloader's original DTBO and uses the native ACK SM8250 QMP UFS driver. It adds a diagnostic bus and a PHY consumer alongside the downstream UFS nodes. The host driver's initcall is excluded, so it cannot submit UFS or SCSI commands. The GPIO 180 reset line is not requested by this test.

| Resource | Physical mapping |
| --- | --- |
| PHY registers | `0x01d87000`, 4 KiB; two lanes. The old ICE window is outside this mapping. |
| Reference and auxiliary clocks | RPMh CXO, GCC UFS PHY auxiliary clock and GCC UFS 1X reference gate, named `ref`, `ref_aux` and `qref`. |
| PHY supplies | PM8150 L5 at 880,000 µV for `vdda-phy`; PM8150 L9 at 1,200,000 µV for `vdda-pll`. |
| Power domain | GCC `UFS_PHY_GDSC` for the PHY and the diagnostic consumer. |
| Reset | The consumer pulses `GCC_UFS_PHY_BCR` with the delays used by the Qualcomm host. On SM8250 the QMP driver releases its PCS software reset during calibration. A production host also has its own reset-provider relationship to the PHY. |

The diagnostic consumer calls `phy_init`, selects HS-B with the G3 calibration parameters, calls `phy_power_on` and `phy_calibrate`, then calls `phy_power_off` and `phy_exit`. The native calibration programs the two lanes, starts the SerDes and polls bit 0 of the PCS ready register. A successful return tests internal PHY readiness. Host link startup and the gear negotiated with a storage device require a separate host trial. [Pinned ACK PHY](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/phy/qualcomm/phy-qcom-qmp-ufs.c) · [Pinned ACK host sequence](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/ufs/host/ufs-qcom.c)

## Reproduce

1. Build the platform bootstrap and the device-tree workflow. Verify the downloaded kernel, board patch, diagnostic consumer source and DT plugin against their artifact manifests.
2. Start from the verified watchdog control on this handset. Run `prepare_legacy_tree_patch.py --ufs-phy-control` with the original F.20 DTBO and the verified `rmx2072-ufs-phy.dtb`. The packager checks the original resource graph both before and after OEM overlay entry 17. Adding two phandles moves OEM-local IDs; every changed reference must resolve to its original target.
3. Build the RAM-only ramdisk with `build_diag_ramdisk.py --ufs-phy-cycle --trial-id ufs-phy-01 --return-to-edl-after 210` and the verified BusyBox, reboot helper and entry carrier. Insert it with `prepare_ramdisk_control.py`, then insert the verified Image and native entry probe with `prepare_kernel_control.py`. The diagnostic image is specific to the unlocked F.20 lab handset.
4. After the diagnostic ACM is configured, run the following commands from that shell. The bus binds explicitly, and each cycle binds and unbinds the test consumer. Save the stage return codes, kernel log, boot ID and UDC state.

```sh
/bin/ufs-phy-cycle preflight
/bin/ufs-phy-cycle probe
/bin/ufs-phy-cycle cycle
/bin/ufs-phy-cycle cycle
dmesg | grep 'PHY trial:'
```

Use the [existing EDL return and recovery procedure](RMX2072_EDL_AND_UFS.md) to restore the reader boot and verify original DTBO and stock Android after the trial.
