#!/usr/bin/env bash
# Build upstream AIDL V5 supplicant for the project's non-SVE ARMv8-A target.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_DIR="${RUNNER_TEMP:?}/rmx2072-m2-aosp"
ARTIFACT_DIR="$ROOT_DIR/artifacts/m3-wifi"
PHASE=${1:-all}
case "$PHASE" in prepare|build|all) ;; *) exit 2 ;; esac
mkdir -p "$ARTIFACT_DIR"
if [[ "$PHASE" != build ]]; then
  bash "$ROOT_DIR/scripts/build/build_m3_graphics.sh" prepare
  python3 - "$SOURCE_DIR" "$ROOT_DIR/artifacts/m3-graphics/selected.upstream.xml" <<'PY'
import copy
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
workspace = Path(sys.argv[1])
manifest_path = workspace/'.repo/manifests/rmx2072-minimal.xml'
manifest = ET.parse(manifest_path)
upstream = {p.get('path', p.get('name')): p for p in ET.parse(sys.argv[2]).findall('project')}
selected = {p.get('path', p.get('name')) for p in manifest.findall('project')}
paths = ['external/wpa_supplicant_8', 'external/libnl', 'system/security']
for path in paths:
    if path not in selected:
        node = copy.deepcopy(upstream[path])
        node.attrib.pop('groups', None)
        manifest.getroot().append(node)
ET.indent(manifest)
manifest.write(manifest_path, encoding='utf-8', xml_declaration=True)
subprocess.run(['repo', 'sync', '-c', '-j2', '--no-tags', '--no-clone-bundle', *paths],
               cwd=workspace, check=True)
PY
  # Keep the real keystore engine and its AIDL declarations, not the unrelated
  # Rust keystore server or synthetic replacements for missing native modules.
  git -C "$SOURCE_DIR/system/security" sparse-checkout set --no-cone \
    /Android.bp /NOTICE /keystore-engine/ /keystore2/aidl/
  git -C "$SOURCE_DIR/system/security" sparse-checkout list > "$ARTIFACT_DIR/security-sparse.txt"
  test "$(git -C "$SOURCE_DIR/external/wpa_supplicant_8" rev-parse HEAD)" = 3396e8b8365817b3a24b78b534b04bb9dcea330a
  cp "$ROOT_DIR/artifacts/m3-graphics/selected"*.xml "$ARTIFACT_DIR/"
  cp "$SOURCE_DIR/.repo/manifests/rmx2072-minimal.xml" "$ARTIFACT_DIR/selected.xml"
  cp "$ROOT_DIR/artifacts/m3-graphics/hardwarebuffer-source.json" "$ARTIFACT_DIR/"
  cp "$ROOT_DIR/device/realme/bladerunner_48m/m3-wifi/WifiBoardConfig.mk" "$SOURCE_DIR/device/realme/rmx2072_m3/"
  printf '\ninclude device/realme/rmx2072_m3/WifiBoardConfig.mk\n' >> "$SOURCE_DIR/device/realme/rmx2072_m3/BoardConfig.mk"
fi
if [[ "$PHASE" == prepare ]]; then exit 0; fi
cd "$SOURCE_DIR"
python3 - <<'PY'
from pathlib import Path
p = Path('external/libdisplay-info/Android.bp')
text = p.read_text()
anchor = '        "//external/drm_hwcomposer:__subpackages__",\n'
entry = '        "//device/realme/rmx2072_m3",\n'
if text.count(anchor) != 1:
    raise ValueError('Pinned libdisplay_info visibility changed')
if entry not in text:
    p.write_text(text.replace(anchor, anchor + entry))
board = Path('device/realme/rmx2072_m3/BoardConfig.mk').read_text()
assert 'TARGET_ARCH_VARIANT := armv8-a' in board
assert 'TARGET_CPU_VARIANT := generic' in board
PY
export ALLOW_MISSING_DEPENDENCIES=true SOONG_UI_NINJA_ARGS=-v
export M3_RECIPE_ROOT="$ROOT_DIR" M3_ARTIFACT_DIR="$ARTIFACT_DIR"
for attempt in $(seq 1 12); do
  set +e
  bash -c 'set -eo pipefail
    source build/envsetup.sh
    lunch rmx2072_m3_graphics-aosp_current-user
    target=wpa_supplicant
    m --skip-ninja "$target"
    python3 "$M3_RECIPE_ROOT/scripts/build/check_m2_ninja_deps.py" \
      --output "$M3_ARTIFACT_DIR/target-dependencies.json" \
      --graph out/combined-rmx2072_m3_graphics.ninja --targets "$target"
    m -j2 "$target"' 2>&1 | tee "$ARTIFACT_DIR/build-$attempt.log"
  result=${PIPESTATUS[0]}
  set -e
  if [[ "$result" == 0 ]]; then break; fi
  python3 "$ROOT_DIR/scripts/build/complete_m2_workspace.py" \
    --workspace "$SOURCE_DIR" --upstream "$ARTIFACT_DIR/selected.upstream.xml" \
    --log "$ARTIFACT_DIR/build-$attempt.log" --record "$ARTIFACT_DIR/dependency-additions.jsonl"
done
test "$result" == 0
repo manifest -r -o "$ARTIFACT_DIR/resolved-manifest.xml"
VENDOR=$(bash -c 'source build/envsetup.sh >&2
  lunch rmx2072_m3_graphics-aosp_current-user >&2
  get_build_var TARGET_OUT_VENDOR')
case "$VENDOR" in
  out/target/product/rmx2072_m3/vendor|out/target/product/rmx2072_m3/system/vendor) ;;
  *) echo "Unexpected vendor output: $VENDOR" >&2; exit 1 ;;
esac
printf '%s\n' "$VENDOR" > "$ARTIFACT_DIR/vendor-output-path.txt"
test -s "$VENDOR/bin/hw/wpa_supplicant"
test -s "$VENDOR/etc/init/android.hardware.wifi.supplicant-service.rc"
find "$VENDOR" -type f -print0 | sort -z | xargs -0 -r sha256sum > "$ARTIFACT_DIR/vendor-files.sha256"
tar -C "$VENDOR" -czf "$ARTIFACT_DIR/wifi-vendor.tar.gz" .
sha256sum "$ARTIFACT_DIR/wifi-vendor.tar.gz" "$ARTIFACT_DIR/resolved-manifest.xml" \
  "$ARTIFACT_DIR/vendor-output-path.txt" > "$ARTIFACT_DIR/SHA256SUMS"
sha256sum external/wpa_supplicant_8/wpa_supplicant/Android.bp \
  external/wpa_supplicant_8/wpa_supplicant/aidl/android.hardware.wifi.supplicant-service.rc \
  external/wpa_supplicant_8/wpa_supplicant/aidl/android.hardware.wifi.supplicant.xml \
  hardware/interfaces/wifi/supplicant/aidl/aidl_api/android.hardware.wifi.supplicant/5/.hash \
  system/security/keystore-engine/Android.bp > "$ARTIFACT_DIR/wifi-source.sha256"
cp device/realme/rmx2072_m3/BoardConfig.mk device/realme/rmx2072_m3/WifiBoardConfig.mk "$ARTIFACT_DIR/"
(cd "$ROOT_DIR"; sha256sum device/realme/bladerunner_48m/m3-wifi/*) > "$ARTIFACT_DIR/project-wifi-source.sha256"
git -C "$ROOT_DIR" rev-parse HEAD > "$ARTIFACT_DIR/project-commit.txt"
printf '%s\n' 'Source-built vendor AIDL V5 supplicant, ARMv8-A generic and real nl80211. Not yet integrated or accepted on the handset. Private driver ioctls and P2P/NoA are not qualified. Mainline RRO must be removed from the integration candidate.' > "$ARTIFACT_DIR/STATUS.txt"
