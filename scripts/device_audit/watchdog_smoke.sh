#!/bin/busybox sh
# Run manually in the RAM-only SID0 diagnostic shell, after confirming an idle
# watchdog and WDOG_NO_WAY_OUT clear. Leave PID 1 and its recovery timer alone.
set -eu
[ "${1:-}" = "--exercise" ] || exit 2
case "$(uname -r)" in 6.18.*) ;; *) exit 2 ;; esac
driver=$(readlink /sys/bus/platform/devices/17c10000.qcom,wdt/driver)
[ "${driver##*/}" = qcom_wdt ]
wd=/sys/class/watchdog/watchdog0
case "$(readlink -f "$wd/device")" in */17c10000.qcom,wdt) ;; *) exit 2 ;; esac
dev=$(cat "$wd/dev")
dir=$(mktemp -d /run/watchdog-smoke.XXXXXX)
node=$dir/watchdog
opened=0
cleanup() {
    if [ "$opened" = 1 ]; then
        printf V >&3
        exec 3>&-
    fi
    rm -f "$node"
    rmdir "$dir"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
mknod "$node" c "${dev%:*}" "${dev#*:}"
exec 3>"$node"
opened=1
for i in 1 2 3; do
    printf K >&3
    sleep 2
done
# The last write requests magic close and sends the final keepalive.
printf V >&3
exec 3>&-
opened=0
echo 'Watchdog keepalives and magic close completed'
