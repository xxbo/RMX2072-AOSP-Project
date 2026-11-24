#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT="$ROOT/artifacts/m3-turnip"
SRC="${RUNNER_TEMP:?}/rmx2072-turnip"
export PATH="$RUNNER_TEMP/mesa-tools/bin:$PATH"
mkdir -p "$OUT" "$SRC"
read -r PIN NDK_VERSION API < <(python3 - "$ROOT/build/m3-turnip-source.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]));print(d['commit'], d['ndk'], d['api'])
PY
)
NDK="$ANDROID_HOME/ndk/$NDK_VERSION/toolchains/llvm/prebuilt/linux-x86_64/bin"
test -x "$NDK/aarch64-linux-android${API}-clang"
git -C "$SRC" init
git -C "$SRC" remote add origin https://android.googlesource.com/platform/external/mesa3d
git -C "$SRC" fetch --depth=1 origin "$PIN"
git -C "$SRC" checkout --detach FETCH_HEAD
test "$(git -C "$SRC" rev-parse HEAD)" = "$PIN"
cat > "$OUT/android-aarch64.ini" <<EOF
[binaries]
c = '$NDK/aarch64-linux-android${API}-clang'
cpp = ['$NDK/aarch64-linux-android${API}-clang++', '-static-libstdc++']
ar = '$NDK/llvm-ar'
strip = '$NDK/llvm-strip'
pkg-config = '/usr/bin/pkg-config'
[host_machine]
system = 'android'
cpu_family = 'aarch64'
cpu = 'armv8-a'
endian = 'little'
[properties]
needs_exe_wrapper = true
[built-in options]
pkg_config_libdir = []
EOF
# Static libdrm avoids introducing a second libdrm.so ABI beside the accepted
# AOSP minigbm/composer library. Its archive is checksum-pinned by Mesa's wrap.
meson setup "$SRC/out" "$SRC" --cross-file "$OUT/android-aarch64.ini" \
  --buildtype=release -Dplatforms=android -Dplatform-sdk-version="$API" \
  -Dandroid-stub=true -Dandroid-libbacktrace=disabled -Dandroid-libperfetto=disabled \
  -Degl=disabled -Dglx=disabled -Dopengl=false -Dgles1=disabled -Dgles2=disabled \
  -Dgallium-drivers= -Dvulkan-drivers=freedreno -Dfreedreno-kmds=msm \
  -Dllvm=disabled -Dzstd=disabled -Dbuild-tests=false -Dprefer_static=true \
  -Dallow-fallback-for=libdrm -Dlibdrm:default_library=static \
  2>&1 | tee "$OUT/configure.log"
meson compile -C "$SRC/out" -j 2 2>&1 | tee "$OUT/build.log"
mkdir -p "$OUT/vendor/lib64/hw"
DRIVER="$OUT/vendor/lib64/hw/vulkan.freedreno.so"
cp "$SRC/out/src/freedreno/vulkan/libvulkan_freedreno.so" "$DRIVER"
patchelf --set-soname vulkan.freedreno.so "$DRIVER"
"$NDK/llvm-strip" --strip-unneeded "$DRIVER"
"$NDK/llvm-readelf" --file-header --dynamic "$DRIVER" > "$OUT/driver-elf.txt"
if grep -q 'Shared library: \[libdrm.so' "$OUT/driver-elf.txt"; then
  echo 'Unexpected shared libdrm dependency' >&2; exit 1
fi
cp "$ROOT/build/m3-turnip-source.json" "$OUT/source.json"
git -C "$ROOT" rev-parse HEAD > "$OUT/project-commit.txt"
find "$SRC/subprojects" -maxdepth 2 -name '*.wrap' -print0 | sort -z | xargs -0 -r sha256sum > "$OUT/subprojects.sha256"
tar -C "$OUT/vendor" -czf "$OUT/turnip-vendor.tar.gz" .
sha256sum "$DRIVER" "$OUT/turnip-vendor.tar.gz" > "$OUT/SHA256SUMS"
printf '%s\n' 'Source-built Turnip for Android ARM64 and MSM DRM. Hardware validation NOT RUN.' > "$OUT/STATUS.txt"
