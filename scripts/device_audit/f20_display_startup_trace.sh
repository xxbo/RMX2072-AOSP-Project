#!/system/bin/sh
# RMX2072 M3 one-shot stock clock capture. No display/register settings changed.
set -e
prefix=/data/local/tmp/rmx-m3-f20-startup
trace=/sys/kernel/tracing/instances/rmx_m3_f20_startup
if [ "${1:-}" = finish ]; then
    sleep 45
    echo 0 > "$trace/tracing_on"
    cat "$trace/trace" > "$prefix-trace.txt"
    for f in "$trace"/per_cpu/cpu*/stats; do
        echo "$f"
        cat "$f"
    done > "$prefix-stats.txt"
    echo 0 > "$trace/events/enable"
    rmdir "$trace" || echo 'Trace disabled; instance removal deferred until reboot'
    cat /proc/sys/kernel/random/boot_id > "$prefix-done.txt"
    exit 0
fi
test ! -e "$prefix-start.txt" || exit 0
mkdir "$trace"
echo 0 > "$trace/tracing_on"
echo 256 > "$trace/buffer_size_kb"
for event in clk_set_rate clk_set_rate_complete clk_set_parent clk_set_parent_complete; do
    printf '%s\n' 'name ~ "*dsi*" || name ~ "disp_*" || name ~ "gcc_disp_*"' > "$trace/events/clk/$event/filter"
    echo 1 > "$trace/events/clk/$event/enable"
done
cat /proc/sys/kernel/random/boot_id > "$prefix-start.txt"
cat /proc/uptime >> "$prefix-start.txt"
echo 1 > "$trace/tracing_on"
/system/bin/sh "$0" finish </dev/null > "$prefix-finish.log" 2>&1 &
exit 0
