#!/bin/busybox sh
# Pre-policy, read-only hardware evidence; published to the existing scratch /data.
echo "M3DISPLAY boot_id=$(cat /proc/sys/kernel/random/boot_id)"
echo "M3DISPLAY kernel=$(uname -r)"
for p in /sys/class/drm/* /sys/class/backlight/*; do
    [ -e "$p" ] || continue
    echo "PATH=$p TARGET=$(readlink -f "$p")"
    for f in dev status enabled modes brightness max_brightness actual_brightness; do
        [ ! -r "$p/$f" ] || { echo "FIELD=$f"; cat "$p/$f"; }
    done
done
for d in /sys/bus/platform/devices/*; do
    case "$d" in *ae00000*|*ae01000*|*ae94000*|*ae94400*|*af00000*|*f100000*|*1740000*|*88e7000*)
        echo "DEVICE=$d DRIVER=$(readlink "$d/driver")" ;;
    esac
done
echo DEFERRED
cat /sys/kernel/debug/devices_deferred
echo DISPLAY_LOG
dmesg | grep -iE 'drm|dpu|dsi|mdss|display|rm19795|dispcc|refgen|pinctrl|rpmhpd|mmcx|smmu.*fault' | tail -180
