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
    filter='name == "dsi0vco_clk" || name == "disp_cc_mdss_byte0_clk" || name == "disp_cc_mdss_pclk0_clk" || name == "disp_cc_mdss_byte0_clk_src" || name == "disp_cc_mdss_pclk0_clk_src"'
    for event in clk_prepare clk_unprepare clk_enable clk_disable clk_set_rate clk_set_parent; do
        echo "$filter" > "$trace/events/clk/$event/filter"
        echo 1 > "$trace/events/clk/$event/enable"
    done
    echo "stacktrace:16 if $filter" > "$trace/events/clk/clk_prepare/trigger"
    echo 1 > "$trace/tracing_on"
    echo 'M3CLKTRACE armed=1 buffer_kb_per_cpu=64 stack_limit=16'
    ;;
end)
    [ -d "$trace" ] || { echo 'M3CLKTRACE unavailable'; exit 0; }
    echo 0 > "$trace/tracing_on"
    echo 0 > "$trace/events/enable"
    echo 'M3CLKTRACE begin'
    # The ring is bounded; cap the published text as well.
    head -n 1200 "$trace/trace"
    echo 'M3CLKTRACE end'
    ;;
*) exit 2 ;;
esac
