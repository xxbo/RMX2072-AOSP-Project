#!/bin/busybox sh
# Called once while PID 1 is stopped after its verified vendor mount.
set -eu
root=/proc/1/root
store=/run/m1-scratch
mkdir "$store"
mount -t tmpfs -o size=640m,mode=0700 tmpfs "$store"
for name in data metadata; do
    case "$name" in data) index=0 ;; metadata) index=1 ;; esac
    sys=/sys/class/block/loop$index
    [ "$(readlink -f "$sys")" = "/sys/devices/virtual/block/loop$index" ]
    [ ! -e "$sys/loop/backing_file" ]
    dev=$(cat "$sys/dev")
    [ "$dev" = "7:$index" ]
    node="$store/$name-loop"
    mknod "$node" b 7 "$index"
    gzip -dc "/$name.ext4.gz" > "$store/$name.ext4"
    [ "$(sha256sum "$store/$name.ext4" | cut -d' ' -f1)" = "$(cat "/$name.ext4.sha256")" ]
    losetup "$node" "$store/$name.ext4"
    [ "$(cat "$sys/loop/backing_file")" = "$store/$name.ext4" ]
    [ "$(cat "$sys/ro")" = 0 ]
    /bin/first-stage-witness scratch-mount "$name"
    awk -v dev="$dev" -v target="/$name" '$3==dev && $5==target && $6 ~ /^rw(,|$)/ && / - ext4 / {
        print "M1EVENT scratch_mount=" target " device=" dev " flags=" $6 " fs=ext4"; ok=1
    } END {exit !ok}' /proc/1/mountinfo > /dev/ttyGS0
    echo "M1EVENT scratch_backing=/$name file=$(cat "$sys/loop/backing_file")" > /dev/ttyGS0
done

# File offsets of exported AArch64 functions in the pinned CP3A.260905.010 GSI.
# Read only Android log calls tagged keystore2 and binder registrations by that process.
log=$root/system/lib64/liblog.so
binder=$root/system/lib64/libbinder_ndk.so
[ "$(sha256sum "$log" | cut -d' ' -f1)" = 8dab885114a41c63e2c4451dfb59ec745610418faeead26c7607173eaf57e8c4 ]
[ "$(sha256sum "$binder" | cut -d' ' -f1)" = 5ba4c4cf25919c5c6b6a30f7ff3e0c7db879f3e63206996569709b9c9fbc13a1 ]
t=/sys/kernel/debug/tracing
events=$t/instances/m1reads/events/m1ks
printf '%s\n' "p:m1ks/ks_buf $log:0x9d50 tag=+0(%x2):string msg=+0(%x3):string" \
    "p:m1ks/ks_log $log:0x9e5c tag=+0(%x1):string msg=+0(%x2):string" \
    "p:m1ks/ks_add $binder:0x24640 task=\$comm name=+0(%x1):string" \
    "r:m1ks/ks_added $binder:0x24640 task=\$comm rc=\$retval:s32" >> "$t/uprobe_events"
for name in ks_buf ks_log; do
    echo 'tag == "keystore2" || tag == "RMXKeymaster"' > "$events/$name/filter"
done
for name in ks_add ks_added; do
    echo 'task == "keystore2"' > "$events/$name/filter"
done
echo 1 > "$events/enable"
echo 'M1EVENT keystore_trace=armed' > /dev/ttyGS0

apps=/sys/module/rmx2072_keymaster_lookup/parameters/apps
if [ -r "$apps" ]; then
    printf '%s\n' "p:m1ks/km_print $log:0xa1cc tag=+0(%x1):string fmt=+0(%x2):string" >> "$t/uprobe_events"
    echo 'tag == "KeyMasterHalDevice" || tag == "KeymasterUtils" || tag == "QSEECOMAPI"' > "$events/km_print/filter"
    echo 1 > "$events/km_print/enable"
    # Init starts the reference ELF under its stock basename. Capture only
    # that task's stderr and pathname lookups, before Android logd is available.
    printf '%s\n' 'p:m1ks/km_open do_sys_openat2 task=$comm path=+u0($arg2):ustring' \
        'p:m1ks/km_stderr ksys_write task=$comm fd=$arg1:u32 msg=+u0($arg2):ustring' \
        'p:m1ks/km_stderrv do_writev task=$comm fd=$arg1:u32 msg=+u0(+u0($arg2)):ustring' >> "$t/kprobe_events"
    echo 'task == "android.hardwar" && (path == "/dev/qseecom" || path == "/dev/ion" || path == "/dev/hwbinder" || path ~ "/dev/dma_heap/*")' > "$events/km_open/filter"
    echo 1 > "$events/km_open/enable"
    km=$root/vendor/lib64/libkeymasterdeviceutils.so
    if [ -f "$km" ]; then
        [ "$(sha256sum "$km" | cut -d' ' -f1)" = e7b223728a88d76eec8b615eb4c1a1e9eb857bd4b20f9a5f762a5a60766f0603 ]
        # The two sites following property_get read its stack buffer. Record
        # only the initial value and enable a one-shot for the first retry.
        printf '%s\n' "p:m1ks/km_listener $km:0x2410 value=+0(\$stack):string" \
            "p:m1ks/km_listener_retry $km:0x2450 value=+0(\$stack):string" \
            "p:m1ks/km_start_ta $km:0x2480 app=+0(%x2):string" >> "$t/uprobe_events"
        echo 1 > "$events/km_listener/enable"
        echo 'disable_event:m1ks:km_listener_retry:1' > "$events/km_listener_retry/trigger"
        echo 1 > "$events/km_listener_retry/enable"
        echo 1 > "$events/km_start_ta/enable"
    fi
    for name in km_stderr km_stderrv; do
        echo 'task == "android.hardwar" && fd == 2 && (msg ~ "*not found*" || msg ~ "*cannot locate*" || msg ~ "*not accessible*")' > "$events/$name/filter"
        echo 1 > "$events/$name/enable"
    done
    if result=$(cat "$apps"); then
        echo "M1EVENT qsee_lookup $result" > /dev/ttyGS0
    else
        echo "M1EVENT qsee_lookup_read_failed=$?" > /dev/ttyGS0
    fi
    version=${apps%/*}/version_info
    for listener in time cancel; do
        node=/sys/module/qcom_scm/parameters/listener_${listener}_lifetime
        if [ -r "$node" ]; then
            if result=$(cat "$node"); then
                echo "M1EVENT qsee_listener_lifetime $result" > /dev/ttyGS0
            else
                echo "M1EVENT qsee_listener_lifetime_read_failed $listener $?" > /dev/ttyGS0
            fi
        fi
    done
    if [ -r "$version" ]; then
        if result=$(cat "$version"); then
            echo "M1EVENT keymaster_version $result" > /dev/ttyGS0
        else
            echo "M1EVENT keymaster_version_read_failed=$?" > /dev/ttyGS0
        fi
    fi
fi
