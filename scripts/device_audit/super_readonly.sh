#!/bin/busybox sh
# RMX2072 F.20 single-super read-only diagnostic, run from the G3 RAM shell.
set -eu
case "$(uname -r):$(cat /trial-id)" in 6.18.*:ufs-host-g3-super-*|6.18.*:ufs-host-g3-gsi17-*) ;; *) exit 2 ;; esac
[ "$(cat /sys/class/udc/*/state)" = configured ]
[ "$(od -An -tx1 /sys/firmware/devicetree/base/oplus,dtsi_no | xargs)" = '00 00 50 7f' ]
bin=/bin/lp
runlp() {
    tool=$1
    shift
    "$bin/ld-musl-aarch64.so.1" --library-path "$bin" "$bin/$tool" "$@"
}
dm() { runlp dmsetup --noudevsync --noudevrules "$@"; }
base=/run/rmx-super
mkdir -p "$base"
part=/sys/class/block/sda10
[ "$(sed -n 's/^PARTNAME=//p' "$part/uevent")" = super ]
case "$(readlink -f "$part")" in */1d84000.ufs/*) ;; *) exit 1 ;; esac
[ "$(cat "$part/size")" = 17317888 ]
backing=$(cat "$part/dev")
super=$base/super
[ -b "$super" ] || mknod "$super" b "${backing%:*}" "${backing#*:}"
blockdev --setro "$super"
[ "$(cat "$part/ro")" = 1 ]

case "$1" in
metadata)
    # F.20 reserves 4 KiB, two 4 KiB geometry blocks and four 64 KiB slot copies.
    dd if="$super" of="$base/prefix" bs=4096 count=67
    [ "$(wc -c < "$base/prefix")" -eq 274432 ]
    sha256sum "$base/prefix"
    for slot in 0 1; do
        runlp lpdump --slot="$slot" "$super" > "$base/dump-$slot"
        grep -qx 'Metadata version: 10.0' "$base/dump-$slot"
        grep -qx 'Metadata max size: 65536 bytes' "$base/dump-$slot"
        grep -qx 'Metadata slot count: 2' "$base/dump-$slot"
        awk -v capacity="$(cat "$part/size")" '
            /^Partition table:/ {table=1; next}
            /^Super partition layout:|^Block device table:/ {table=0}
            !table {next}
            $1=="Name:" {
                name=$2
                if (name !~ /^[A-Za-z0-9_.-]+$/ || seen[name]++) exit 1
                next_sector=0; reading=0; next
            }
            $1=="Extents:" {reading=1; next}
            /^-+$/ {reading=0; next}
            reading && NF {
                if (NF!=6 || $1 !~ /^[0-9]+$/ || $2!=".." || $3 !~ /^[0-9]+$/ ||
                    $4!="linear" || $5!="super" || $6 !~ /^[0-9]+$/ || name=="" ||
                    $1+0!=next_sector || $3+0<$1+0 || $6+0<2048 || $6+$3-$1+1>capacity) exit 1
                printf "%s %.0f %.0f %.0f\n", name, $1, $3-$1+1, $6
                next_sector=$3+1
            }
        ' "$base/dump-$slot" > "$base/table-$slot.tmp"
        [ -s "$base/table-$slot.tmp" ]
        mv "$base/table-$slot.tmp" "$base/table-$slot"
        echo "slot=$slot"
        cat "$base/table-$slot"
    done
    ;;
map|verity|combined)
    # The F.20 reference must select slot 0 before this stage is invoked.
    [ -s "$base/table-0" ]
    [ -r /sys/class/misc/device-mapper/dev ]
    mkdir -p /dev/mapper
    ctl=$(cat /sys/class/misc/device-mapper/dev)
    [ -c /dev/mapper/control ] || mknod /dev/mapper/control c "${ctl%:*}" "${ctl#*:}"
    dm version
    names='system vendor product'
    if [ "$1" = combined ]; then
        names='vendor odm system'
        digest=$(sha256sum "$base/prefix")
        [ "${digest%% *}" = "$(cat /verity-profile/lp-prefix)" ]
    fi
    device() {
        for d in /sys/class/block/dm-*; do
            [ -f "$d/dm/name" ] || continue
            if [ "$(cat "$d/dm/name")" = "rmx-lp-$1" ]; then echo "$d"; return 0; fi
        done
        return 1
    }
    for n in $names; do
        if device "$n"; then echo "Mapping already exists: $n" >&2; exit 1; fi
    done
    mkdir "$base/map-lock"
    cleanup() {
        status=$?
        trap - EXIT
        for n in $names; do
            if device "$n" >/dev/null; then dm remove "rmx-lp-$n" || status=1; fi
            if device "$n" >/dev/null; then status=1; fi
        done
        rmdir "$base/map-lock" || status=1
        echo "cleanup_status=$status"
        exit "$status"
    }
    trap cleanup EXIT
    trap 'exit 1' HUP INT TERM
    for n in $names; do
        table=$(awk -v name="$n" -v dev="$backing" '$1==name {print $2, $3, "linear", dev, $4}' "$base/table-0")
        [ -n "$table" ]
        dm create "rmx-lp-$n" --readonly --table "$table"
        d=$(device "$n")
        [ "$(cat "$d/ro")" = 1 ]
        expected=$(echo "$table" | awk '{s+=$2} END {printf "%.0f", s}')
        [ "$(cat "$d/size")" = "$expected" ]
        actual=$(dm table "rmx-lp-$n")
        [ "$actual" = "$table" ]
        echo "mapped=$n sectors=$expected ro=1"
        echo "$actual"
        nums=$(cat "$d/dev")
        node="$base/read-$n"
        [ ! -e "$node" ] || rm -f "$node"
        mknod "$node" b "${nums%:*}" "${nums#*:}"
        if [ "$1" = combined ]; then continue; fi
        if [ "$1" = verity ]; then
            /bin/verity-readonly "$n" "$node" "$nums"
        else
            sha256sum "$node"
        fi
        rm -f "$node"
    done
    if [ "$1" = combined ]; then
        /bin/verity-readonly vendor "$base/read-vendor" "$(cat "$(device vendor)/dev")" combined
        rm -f "$base/read-vendor" "$base/read-odm" "$base/read-system"
    fi
    ;;
*) exit 2 ;;
esac
