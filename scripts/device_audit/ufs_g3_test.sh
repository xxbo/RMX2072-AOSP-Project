#!/bin/busybox sh
# Run after ufs-host-test preflight on the staged G3 profile.
set -eu
case "$(uname -r):$(cat /trial-id)" in 6.18.*:ufs-host-g3-*) ;; *) exit 2 ;; esac
of=/sys/firmware/devicetree/base
host="$of/soc/ufs-host-lab/ufs@1d84000"
trace=/sys/kernel/debug/tracing
hba=/sys/bus/platform/devices/1d84000.ufs
[ "$(od -An -tx1 "$of/oplus,dtsi_no" | xargs)" = '00 00 50 7f' ]
[ "$(od -An -tx1 "$host/limit-hs-gear" | xargs)" = '00 00 00 03' ]
[ "$(cat /sys/class/udc/*/state)" = configured ]
case "$1" in
arm-g3)
    # Keep the error stream separate so it cannot evict LINKSTARTUP records.
    g3="$trace/instances/rmxg3"
    mkdir -p "$g3"
    echo 'p:rmxg3/hba_event ufshcd_update_evt_hist id=%x1:u32 value=%x2:x32' >> "$trace/kprobe_events"
    echo 1 > "$g3/events/rmxg3/hba_event/enable"
    echo 1 > "$g3/events/ufs/ufshcd_clk_scaling/enable"
    echo 1 > "$g3/events/ufs/ufshcd_runtime_suspend/enable"
    echo 1 > "$g3/events/ufs/ufshcd_runtime_resume/enable"
    echo 1 > "$g3/tracing_on"
    ;;
read-g3)
    scale=$(cat "$hba/clkscale_enable")
    pm=$(cat "$hba/power/control")
    trap 'echo "$scale" > "$hba/clkscale_enable"; echo "$pm" > "$hba/power/control"' EXIT
    echo on > "$hba/power/control"
    # This driver moves to its highest clock and gear when scaling is disabled.
    echo 0 > "$hba/clkscale_enable"
    [ "$(cat "$hba/power_info/gear")" = HS_GEAR3 ]
    [ "$(cat "$hba/power_info/lane")" = 2 ]
    [ "$(cat "$hba/power_info/rate")" = HS_RATE_B ]
    for clk in gcc_ufs_phy_axi_clk gcc_ufs_phy_unipro_core_clk; do
        hz=$(awk -v clk="$clk" '$1 == clk {print $5}' /sys/kernel/debug/clk/clk_summary)
        echo "$clk=$hz"
        [ "$hz" = 300000000 ]
    done
    for pass in 1 2; do
        for name in sda sdb sdc sdd sde sdf; do
            disk=/sys/class/block/$name
            node=/run/ufs-ro-$name
            [ -b "$node" ] && [ "$(cat "$disk/ro")" = 1 ]
            before=$(awk '{print $3}' "$disk/stat")
            dd if="$node" of=/dev/null iflag=direct bs=65536 skip=16 count=16
            after=$(awk '{print $3}' "$disk/stat")
            delta=$((after-before))
            [ "$delta" -ge 2048 ]
            echo "pass=$pass disk=$name read_sectors=$delta"
        done
    done
    before=$(awk '{print $3}' /sys/class/block/sda/stat)
    dd if=/run/ufs-ro-sda of=/dev/null iflag=direct bs=131072 skip=32 count=512
    after=$(awk '{print $3}' /sys/class/block/sda/stat)
    delta=$((after-before))
    [ "$delta" -ge 131072 ]
    echo "bulk_disk=sda read_sectors=$delta gear=$(cat "$hba/power_info/gear")"
    ;;
wake)
    [ "$(cat "$hba/power/control")" = auto ]
    [ "$(cat /sys/class/block/sda/ro)" = 1 ]
    for pass in 1 2 3; do
        for tick in 1 2 3 4 5 6 7 8 9 10; do
            state=$(cat "$hba/power_info/link_state")
            [ "$state" = HIBERN8 ] && break
            sleep 1
        done
        [ "$state" = HIBERN8 ]
        before=$(awk '{print $3}' /sys/class/block/sda/stat)
        sample=/run/ufs-wake-$pass
        dd if=/run/ufs-ro-sda of="$sample" bs=65536 skip=64 count=16 iflag=direct
        [ "$(wc -c < "$sample")" -eq 1048576 ]
        after=$(awk '{print $3}' /sys/class/block/sda/stat)
        [ "$((after-before))" -ge 2048 ]
        [ "$pass" = 1 ] || cmp -s /run/ufs-wake-1 "$sample"
        echo "wake=$pass previous=$state sectors=$((after-before)) bytes=1048576"
    done
    ;;
gpt)
    count=0
    for p in /sys/class/block/sd*; do
        [ -f "$p/partition" ] || continue
        label=$(sed -n 's/^PARTNAME=//p' "$p/uevent")
        case "$label" in boot|dtbo|metadata|super|userdata) ;; *) continue ;; esac
        case "$(readlink -f "$p")" in */1d84000.ufs/*) ;; *) exit 1 ;; esac
        name=$(basename "$p")
        echo "gpt=$label node=$name start=$(cat "$p/start") sectors=$(cat "$p/size")"
        count=$((count+1))
        case "$label" in
        boot|dtbo)
            devnums=$(cat "$p/dev")
            node=/run/ufs-part-$label
            [ -b "$node" ] || mknod "$node" b "${devnums%:*}" "${devnums#*:}"
            blockdev --setro "$node"
            [ "$(cat "$p/ro")" = 1 ]
            sha256sum "$node"
            ;;
        esac
    done
    [ "$count" = 5 ]
    ;;
*) exit 2 ;;
esac
