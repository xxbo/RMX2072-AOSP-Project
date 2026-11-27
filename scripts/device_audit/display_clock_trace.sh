#!/bin/busybox sh
# Trace native CCF calls in one bounded, display-only instance. No clock writes.
set -eu
[ -f /m3-display-staged ]
trace=/sys/kernel/debug/tracing/instances/rmx_m3_clk
case "$1" in
begin)
    # Never erase a trace from a previous invocation on this boot.
    [ ! -e "$trace" ]
    mkdir "$trace"
    echo 0 > "$trace/tracing_on"
    echo 64 > "$trace/buffer_size_kb"
    if [ -f /m3-first-frame-trace ]; then
        # Keep the earliest records, with loss counters proving completeness.
        # One bounded instance; no stack printing in the first-frame experiment.
        echo 256 > "$trace/buffer_size_kb"
        echo mono > "$trace/trace_clock"
        echo 0 > "$trace/options/overwrite"
        for event in rmx_dsi_sample rmx_display_step; do
            [ -e "$trace/events/rmx2072_display/$event/enable" ]
            echo 1 > "$trace/events/rmx2072_display/$event/enable"
        done
        echo "M3FF armed=1 boot=$(cat /proc/sys/kernel/random/boot_id) buffer_kb_per_cpu=256 overwrite=0 clock=mono"
    fi
    filter='name == "dsi0vco_clk" || name == "disp_cc_mdss_byte0_clk" || name == "disp_cc_mdss_pclk0_clk" || name == "disp_cc_mdss_byte0_clk_src" || name == "disp_cc_mdss_pclk0_clk_src"'
    if [ -f /m3-first-frame-trace ]; then
        filter="$filter || name == \"disp_cc_mdss_mdp_clk\" || name == \"disp_cc_mdss_mdp_clk_src\""
    fi
    for event in clk_prepare clk_unprepare clk_enable clk_disable clk_set_rate clk_set_parent; do
        echo "$filter" > "$trace/events/clk/$event/filter"
        echo 1 > "$trace/events/clk/$event/enable"
    done
    if [ ! -f /m3-first-frame-trace ]; then
        echo "stacktrace:16 if $filter" > "$trace/events/clk/clk_prepare/trigger"
    fi
    echo 1 > "$trace/tracing_on"
    if [ -f /m3-first-frame-trace ]; then
        echo 'M3CLKTRACE armed=1 buffer_kb_per_cpu=256 stack_limit=0'
    else
        echo 'M3CLKTRACE armed=1 buffer_kb_per_cpu=64 stack_limit=16'
    fi
    ;;
end)
    [ -d "$trace" ] || { echo 'M3CLKTRACE unavailable'; exit 0; }
    echo 0 > "$trace/tracing_on"
    echo 0 > "$trace/events/enable"
    echo 'M3CLKTRACE begin'
    # The ring is bounded; cap the published text as well.
    if [ -f /m3-first-frame-trace ]; then
        # 2 MiB binary storage on the eight-CPU device. Read the full frozen
        # text; do not silently truncate and misclassify absent error events.
        cat "$trace/trace"
        for stats in "$trace"/per_cpu/cpu*/stats; do
            echo "M3FF stats=$stats"
            cat "$stats"
        done
        echo "M3FF complete boot=$(cat /proc/sys/kernel/random/boot_id)"
    else
        head -n 1200 "$trace/trace"
    fi
    echo 'M3CLKTRACE end'
    ;;
*) exit 2 ;;
esac
