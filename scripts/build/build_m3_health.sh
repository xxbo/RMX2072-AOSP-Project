#!/usr/bin/env bash
# Build the pinned upstream Health implementation and its real native closure.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_DIR="${RUNNER_TEMP:?}/rmx2072-m2-aosp"
ARTIFACT_DIR="$ROOT_DIR/artifacts/m3-health"
PHASE=${1:-all}
case "$PHASE" in prepare|build|all) ;; *) exit 2 ;; esac
mkdir -p "$ARTIFACT_DIR"
if [[ "$PHASE" != build ]]; then
  # Reuse the bounded, pinned native workspace, without building the renderer.
  bash "$ROOT_DIR/scripts/build/build_m3_graphics.sh" prepare
  # HealthLoop uses UeventSkfilter through these real upstream header modules.
  # Select their projects from the same pinned manifest, then expose only the
  # native headers/defaults instead of parsing the networking Java framework.
  python3 - "$SOURCE_DIR" "$ROOT_DIR/artifacts/m3-graphics/selected.upstream.xml" <<'PY'
import copy
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
workspace = Path(sys.argv[1])
manifest_path = workspace/'.repo/manifests/rmx2072-minimal.xml'
manifest = ET.parse(manifest_path)
upstream = {p.get('path', p.get('name')):p for p in ET.parse(sys.argv[2]).findall('project')}
selected = {p.get('path', p.get('name')) for p in manifest.findall('project')}
paths = ['packages/modules/Connectivity', 'system/bpf']
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
  git -C "$SOURCE_DIR/packages/modules/Connectivity" sparse-checkout set --no-cone \
    /bpf/headers/ /bpf/syscall_wrappers/
  git -C "$SOURCE_DIR/system/bpf" sparse-checkout set --no-cone /Android.bp /NOTICE /include/
  git -C "$SOURCE_DIR/packages/modules/Connectivity" sparse-checkout list > "$ARTIFACT_DIR/connectivity-sparse.txt"
  git -C "$SOURCE_DIR/system/bpf" sparse-checkout list > "$ARTIFACT_DIR/bpf-sparse.txt"
  cp "$ROOT_DIR/artifacts/m3-graphics/selected"*.xml "$ARTIFACT_DIR/"
  cp "$SOURCE_DIR/.repo/manifests/rmx2072-minimal.xml" "$ARTIFACT_DIR/selected.xml"
  cp "$ROOT_DIR/artifacts/m3-graphics/hardwarebuffer-source.json" "$ARTIFACT_DIR/"
fi
if [[ "$PHASE" == prepare ]]; then exit 0; fi
cd "$SOURCE_DIR"
# Soong analyzes the existing product's composer declaration even when only
# Health is requested. Apply the same narrow visibility admission as graphics.
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
PY
export ALLOW_MISSING_DEPENDENCIES=true SOONG_UI_NINJA_ARGS=-v
export M3_RECIPE_ROOT="$ROOT_DIR" M3_ARTIFACT_DIR="$ARTIFACT_DIR"
for attempt in $(seq 1 12); do
  set +e
  bash -c 'set -eo pipefail
    source build/envsetup.sh
    lunch rmx2072_m3_graphics-aosp_current-user
    target=android.hardware.health-service.example
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
test -s "$VENDOR/bin/hw/android.hardware.health-service.example"
find "$VENDOR" -type f -print0 | sort -z | xargs -0 -r sha256sum > "$ARTIFACT_DIR/vendor-files.sha256"
tar -C "$VENDOR" -czf "$ARTIFACT_DIR/health-vendor.tar.gz" .
sha256sum "$ARTIFACT_DIR/health-vendor.tar.gz" "$ARTIFACT_DIR/resolved-manifest.xml" "$ARTIFACT_DIR/vendor-output-path.txt" > "$ARTIFACT_DIR/SHA256SUMS"
sha256sum hardware/interfaces/health/aidl/default/{Android.bp,main.cpp,Health.cpp,HalHealthLoop.cpp} \
  system/core/healthd/BatteryMonitor.cpp \
  packages/modules/Connectivity/bpf/{headers,syscall_wrappers}/Android.bp \
  system/bpf/Android.bp > "$ARTIFACT_DIR/health-source.sha256"
git -C "$ROOT_DIR" rev-parse HEAD > "$ARTIFACT_DIR/project-commit.txt"
printf '%s\n' 'Pinned AOSP Health AIDL V5 service. Reads kernel power_supply only; no synthetic battery override. Missing gauge/charger drivers remain unported. Device integration pending.' > "$ARTIFACT_DIR/STATUS.txt"
