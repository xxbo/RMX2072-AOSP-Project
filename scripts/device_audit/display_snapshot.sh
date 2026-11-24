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
    case "$d" in *ae00000*|*ae01000*|*ae94000*|*ae94400*|*af00000*|*f100000*|*1740000*|*88e7000*|*3d00000*|*3d6a000*|*3d90000*|*3da0000*|*18591000*|*c263000*|*c265000*)
        echo "DEVICE=$d DRIVER=$(readlink "$d/driver")" ;;
    esac
done
for p in /sys/devices/system/cpu/cpufreq/policy* /sys/class/devfreq/* /sys/class/thermal/thermal_zone*; do
    [ -d "$p" ] || continue
    echo "PERFORMANCE_PATH=$p TARGET=$(readlink -f "$p")"
    for f in scaling_driver scaling_governor scaling_cur_freq scaling_min_freq scaling_max_freq scaling_available_frequencies governor cur_freq available_frequencies min_freq max_freq type temp; do
        [ ! -r "$p/$f" ] || { echo "FIELD=$f"; cat "$p/$f"; }
    done
done
echo DEFERRED
cat /sys/kernel/debug/devices_deferred
echo DISPLAY_LOG
dmesg | grep -iE 'drm|dpu|dsi|mdss|display|rm19795|dispcc|refgen|pinctrl|rpmhpd|mmcx|smmu.*fault|adreno|gmu|gpu|cpufreq|tsens|thermal|firmware' | tail -220
