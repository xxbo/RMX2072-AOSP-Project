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
if [ -d /sys/bus/platform/devices/1c00000.pcie ]; then
    echo "M3WLAN snapshot=begin boot_id=$(cat /proc/sys/kernel/random/boot_id) uptime=$(cut -d ' ' -f 1 /proc/uptime)"
    # Read provider state before Android policy restricts debugfs. No GPIO,
    # regulator, clock, rescan or power-management writes are performed here.
    for p in /sys/kernel/debug/regulator/regulator_summary /sys/kernel/debug/clk/clk_summary /sys/kernel/debug/gpio; do
        echo "M3WLAN path=$p"
        cat "$p"
    done
    for p in /sys/kernel/debug/pinctrl/*f100000*/pinmux-pins /sys/kernel/debug/pinctrl/*f100000*/pinconf-pins; do
        [ -r "$p" ] || continue
        echo "M3WLAN path=$p"
        grep -E 'pin (20|21|79|80|81) |gpio(20|21|79|80|81)([^0-9]|$)' "$p"
    done
    for p in /sys/bus/pci/devices/*; do
        [ -d "$p" ] || continue
        echo "M3WLAN pci=$p driver=$(readlink "$p/driver")"
        for f in vendor device current_link_speed current_link_width power/runtime_status power/control; do
            echo "M3WLAN field=$f"
            cat "$p/$f"
        done
        # Standard PCI config space only; never read raw MMIO/PHY registers.
        od -Ax -tx4 -N256 "$p/config"
    done
    for p in /sys/bus/platform/drivers/pwrseq-qcom_wcn /sys/bus/platform/drivers/pci-pwrctrl-pwrseq /sys/bus/pwrseq/devices; do
        echo "M3WLAN path=$p"
        ls -l "$p"
    done
    echo "M3WLAN snapshot=end"
fi
echo DISPLAY_LOG
dmesg | grep -iE 'drm|dpu|dsi|mdss|display|rm19795|dispcc|refgen|pinctrl|rpmhpd|mmcx|smmu.*fault|adreno|gmu|gpu|cpufreq|tsens|thermal|firmware' | tail -220
