# RMX2072 diagnostic recovery and UFS bring-up

## Software return to EDL

On the unlocked F.20 handset, stock Android's `adb reboot edl` enumerated USB `05c6:9008`. The host completed Sahara, read boot and DTBO, then reset back into F.20 without programming a partition.

The diagnostic ramdisk sends `RESTART2("edl")` either through its independent timer or through `/bin/reboot-edl edl` on the live ACM shell. The pinned ACK SCM driver normally clears its download-mode setting at shutdown. The F.20-family source translates the specific EDL command into Qualcomm's emergency-download request. The captured F.20 tree contains the named TCSR resource and has no emergency-download IMEM cookie node. The board patch requests a warm reboot and issues the emergency request in SCM shutdown, after clients have shut down. The normal shutdown path still applies to ordinary reboot and poweroff. The board match requires the Kona MTP root, OEM selector 20607 and the SM8250 SCM node. [Vendor restart implementation](https://github.com/realme-kernel-opensource/realme_GTneo2-X50pro-GTMasterExploratory-AndroidS-kernel-source/blob/4e5ec4aeeb781851b0fe6c268d9ba69953166fda/drivers/power/reset/msm-poweroff.c#L256-L281) · [ACK SCM](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/firmware/qcom/qcom_scm.c)

With one diagnostic ACM attached and pyserial installed, these commands exercise separate return paths. Use a new output filename for each run.

```sh
python scripts/device_audit/usb_edl_return.py --mode timer --output timer-return.json
python scripts/device_audit/usb_edl_return.py --mode command --output command-return.json
```

Timer mode identifies the board and waits for the ramdisk deadline. Command mode verifies the live 6.18 shell, board selector and configured UDC before requesting EDL. Both require the diagnostic ACM to disappear and a new 9008 port to enumerate. A Firehose programmer and device-specific recovery images are separate from this observer. The timer depends on PID 1 having run and on enough kernel functionality to schedule a reboot. A failure before that point can still need hardware recovery.

The platform bootstrap applies the tracked SCM patch to the pinned ACK checkout and publishes its digest with the kernel artifact. Verify the artifact and `dist/Image` against the build manifest. Use `build_diag_ramdisk.py --return-to-edl-after SECONDS` to set the timer, `prepare_ramdisk_control.py` to insert that ramdisk in a known boot image, then `prepare_kernel_control.py` with the verified Image and the reviewed entry probe. The kernel packager retains the template's complete DTB bundle, ramdisk and command line. Both trial images use original F.20 DTBO.

## UFS dependencies on this board

1. **Reset pad.** Preserve the original OEM pin states and phandles. Migrate the interrupt wake supplier to the SM8250 PDC binding and the TLMM provider to its west, south and north register banks. The upstream pinctrl driver assigns GPIO group 180 to the UFS reset pad. Its candidate consumer polarity is active-low. The read-only probe calls the GPIO chip-info and line-info ioctls. It never requests a line or sets a GPIO level.
2. **Power and clocks.** The F.20 regulator sysfs reported L5 at 880,000 µV, L6 and L9 at 1,200,000 µV, L17 at 2,504,000 µV and S4 at 1,800,000 µV. These samples describe one stock boot. Reconcile the host/PHY supply phandles, GCC UFS clocks, shared `UFS_PHY_GDSC`, host reset and PHY reset provider against the ACK binding.
3. **Controller and PHY.** OEM overlay entry 17 fragment 61 restores the downstream PHY compatible, L5, L9 and status. Fragment 62 restores the host's supply references and status. The TLMM-only control checks that both UFS nodes remain identical to their respective baselines before and after OEM application. It excludes `ufs_qcom_pltform_init` and `qmp_ufs_driver_init` only for this boot. A storage-capable profile must resolve those OEM fixups, the two DMA streams and both interconnect paths before attempting enumeration. The first storage test should identify the device and inspect block metadata with filesystems unmounted.
4. **Android and peripherals.** After reproducible storage access, progress through display and touch, Android first-stage mounts, AVB/device-mapper and file-based encryption compatibility. Charging, thermal management, suspend/resume, GPU, remote processors, audio, radios and camera require their own board and firmware checks. The RAM-only shell does not validate these paths.
