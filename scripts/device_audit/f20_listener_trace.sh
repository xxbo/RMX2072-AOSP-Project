#!/system/bin/sh
# Run as root on F.20. Print only SCM function IDs, result codes and listener IDs.
set -eu
control=/data/local/tmp/rmx2072-f20-hmac-control
if [ "$#" -gt 0 ]; then
    test "$#" = 1
    test "$1" = --hmac-control
    test "$(sha256sum "$control" | cut -d' ' -f1)" = 71844d2532aefc295bbfb248b4c6b294c83b9cbda7ce4a01fd2368d9ed86d63f
fi
test "$(getprop ro.build.display.id)" = RMX2072_11_F.20
test "$(getprop sys.boot_completed)" = 1
test "$(getprop vendor.sys.listeners.registered)" = true
hal=$(pidof android.hardware.keymaster@4.0-service-qti)
daemon=$(pidof qseecomd)
boot=$(cat /proc/sys/kernel/random/boot_id)
alias_name="rmx2072_m1_listener_${boot}_$$"
# F.20 sometimes keeps a disabled tracing instance busy until reboot.
# Reuse the singleton and serialize captures with a private directory lock.
dir=/sys/kernel/tracing/instances/rmx2072_keymaster
lock=/data/local/tmp/rmx2072-keymaster-trace.lock
umask 077
mkdir "$lock"
trap 'rmdir "$lock"' EXIT
key_created=0
cleanup() {
    echo 0 > "$dir/tracing_on"
    echo 0 > "$dir/events/scm/enable"
    if [ "$key_created" = 1 ]; then
        keystore_cli_v2 delete --name="$alias_name" >/dev/null
    fi
    : > "$dir/set_event_pid"
    : > "$dir/trace"
    rmdir "$dir" 2>/dev/null || test "$(cat "$dir/events/enable")" = 0
    rmdir "$lock"
}
if [ -d "$dir" ]; then
    test "$(cat "$dir/tracing_on")" = 0
    test "$(cat "$dir/events/enable")" = 0
else
    mkdir "$dir"
fi
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
echo 0 > "$dir/tracing_on"
printf 'BOOT %s HAL %s DAEMON %s\n' "$boot" "$hal" "$daemon"
logcat -b all -d --pid="$daemon" -v brief | sed -n 's/.*): \(.*\): Started (Listener ID = \([0-9]*\)).*/LISTENER \2 \1/p'
for task in "/proc/$hal/task/"*; do
    tid=${task##*/}
    printf 'TID %s\n' "$tid"
    echo "$tid" >> "$dir/set_event_pid"
done
echo 1 > "$dir/events/scm/enable"

sample() {
    phase=$1
    shift
    : > "$dir/trace"
    echo 1 > "$dir/tracing_on"
    rc=0
    "$@" >/dev/null 2>&1 || rc=$?
    echo 0 > "$dir/tracing_on"
    printf 'PHASE %s %d\n' "$phase" "$rc"
    awk '/scm_call_start: func id=/ {
        sub(/^.*scm_call_start: func id=/, ""); sub(/ .*/, ""); print "START", $0
    } /scm_call_end: ret:/ {
        sub(/^.*scm_call_end: ret: /, ""); gsub(/,/, "");
        if ($1 == "0x1" || $1 == "0x2") print "END", $1, $2, $3;
        else print "END", $1
    }' "$dir/trace"
    for stats in "$dir"/per_cpu/cpu*/stats; do
        awk '/^(overrun|dropped events):/ && $NF != 0 { print "LOST", $0; exit 1 }' "$stats"
    done
    return "$rc"
}
sample idle sleep 1
worker_start=$(date +%s)
if [ "$#" = 1 ]; then
    sample hmac_parameters env LD_LIBRARY_PATH=/vendor/lib64:/apex/com.android.vndk.v30/lib64 "$control"
else
    key_created=1
    sample generate keystore_cli_v2 generate --seclevel=tee --name="$alias_name"
    sample characteristics keystore_cli_v2 get-chars --name="$alias_name"
    sample sign_verify keystore_cli_v2 sign-verify --name="$alias_name"
    sample delete keystore_cli_v2 delete --name="$alias_name"
    key_created=0
fi
logcat -b all -d --pid="$daemon" -v epoch -s DrmLibTime:D QC-time-services:D |
    awk -v start="$worker_start" '$1 >= start {
        if (/command id, time_cmd_id = [0-9]+$/) print "TIME_COMMAND", $NF
        if (/time_get_modem_time$/) print "TIME_SOURCE modem"
        if (/time_getutcsec returns 0,/) print "TIME_RESULT 0"
    }'
test "$boot" = "$(cat /proc/sys/kernel/random/boot_id)"
test "$hal" = "$(pidof android.hardware.keymaster@4.0-service-qti)"
test "$daemon" = "$(pidof qseecomd)"
service check android.security.maintenance
