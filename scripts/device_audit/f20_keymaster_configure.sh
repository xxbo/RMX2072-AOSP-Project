#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Restart the verified F.20 Keymaster HAL once and capture CONFIGURE metadata.
# Run as root and retain stdout privately for the normalized device record.
set -eu
t=/sys/kernel/tracing
g=rmx2072_configure_fields
d=$t/instances/$g
stock=/vendor/lib64/libqtikeymaster4.so
api=/vendor/lib64/libQSEEComAPI.so
test "$(getprop ro.build.display.id)" = RMX2072_11_F.20
test "$(getprop sys.boot_completed)" = 1
test "$(sha256sum "$stock" | cut -d' ' -f1)" = 8fb4d8c7ad198c49379400ff52beb6fe6f1482ca53220b27192e4faacb4311d1
test "$(sha256sum "$api" | cut -d' ' -f1)" = f5274283690c77730166d928ba55507d171e8c6f40af6195ce2500f43423e27c
test ! -d "$t/events/$g"
test ! -d "$d"
mkdir "$d"
clean() {
 echo 0 > "$d/tracing_on"
 echo 0 > "$d/events/scm/enable"
 for n in configure configured sizes payload; do
  if [ -e "$d/events/$g/$n/enable" ]; then echo 0 > "$d/events/$g/$n/enable"; echo "-:$g/$n" >> "$t/uprobe_events"; fi
 done
 : > "$d/trace"
 rmdir "$d" 2>/dev/null || true
}
trap clean EXIT
echo 0 > "$d/tracing_on"
echo 256 > "$d/buffer_size_kb"
echo "p:$g/configure $stock:0x14074" >> "$t/uprobe_events"
echo "r:$g/configured $stock:0x14074 rc=\$retval:s32" >> "$t/uprobe_events"
echo "p:$g/sizes $api:0x68dc method=+0(%x1):u32 request=%x2:u32 response=%x4:u32" >> "$t/uprobe_events"
echo "p:$g/payload $stock:0x141ac method=+0(%x1):u32 offset=+4(%x1):u32 count=+8(%x1):u32 tag0=+12(%x1):u32 value0=+16(%x1):u32 tag1=+24(%x1):u32 value1=+28(%x1):u32 tag2=+36(%x1):u32 value2=+40(%x1):u32" >> "$t/uprobe_events"
echo 1 > "$d/events/scm/enable"
echo 1 > "$d/events/$g/enable"
: > "$d/trace"
old=$(pidof android.hardware.keymaster@4.0-service-qti)
cat /proc/sys/kernel/random/boot_id
echo "old_pid=$old"
echo 1 > "$d/tracing_on"
setprop ctl.restart keymaster-4-0
sleep 3
echo 0 > "$d/tracing_on"
new=$(pidof android.hardware.keymaster@4.0-service-qti)
test -n "$new" && test "$new" != "$old"
test "$(getprop init.svc.keymaster-4-0)" = running
echo "new_pid=$new"
cat "$d/trace"
for stats in "$d"/per_cpu/cpu*/stats; do awk '/^(overrun|dropped events):/ && $NF != 0 {exit 1}' "$stats"; done
