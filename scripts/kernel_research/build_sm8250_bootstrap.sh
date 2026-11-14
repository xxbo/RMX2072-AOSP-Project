#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE="${RUNNER_TEMP:-/tmp}/android17-gki-618"
ARTIFACT_DIR="$ROOT_DIR/artifacts/sm8250-bootstrap"
mkdir -p "$ARTIFACT_DIR/dist"
GKI_SYNC_ONLY=1 bash "$ROOT_DIR/scripts/kernel_research/build_gki_618_kleaf.sh"
EDL_PATCH="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-patches/rmx2072-scm-edl.patch"
git -C "$WORKSPACE/common" apply --check "$EDL_PATCH"
git -C "$WORKSPACE/common" apply "$EDL_PATCH"
sha256sum "$EDL_PATCH" > "$ARTIFACT_DIR/board-patch.sha256"
TZMEM_PATCH="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-patches/rmx2072-tzmem-status.patch"
git -C "$WORKSPACE/common" apply --check "$TZMEM_PATCH"
git -C "$WORKSPACE/common" apply "$TZMEM_PATCH"
sha256sum "$TZMEM_PATCH" > "$ARTIFACT_DIR/tzmem-patch.sha256"
PHY_TEST="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-probes/rmx2072-ufs-phy-test.c"
cp "$PHY_TEST" "$WORKSPACE/common/drivers/phy/qualcomm/"
printf '\nobj-$(CONFIG_PHY_QCOM_QMP_UFS) += rmx2072-ufs-phy-test.o\n' >> "$WORKSPACE/common/drivers/phy/qualcomm/Makefile"
sha256sum "$PHY_TEST" > "$ARTIFACT_DIR/phy-test.sha256"
KM_PROBE="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-probes/rmx2072-keymaster-lookup.c"
cp "$KM_PROBE" "$WORKSPACE/common/drivers/firmware/qcom/"
printf '\nobj-$(CONFIG_QCOM_QSEECOM) += rmx2072-keymaster-lookup.o\n' >> "$WORKSPACE/common/drivers/firmware/qcom/Makefile"
sha256sum "$KM_PROBE" > "$ARTIFACT_DIR/keymaster-lookup.sha256"
LISTENER="$ROOT_DIR/device/realme/bladerunner_48m/bootstrap-probes/rmx2072-listener.inc"
cp "$LISTENER" "$WORKSPACE/common/drivers/firmware/qcom/"
python3 - "$WORKSPACE/common/drivers/firmware/qcom/qcom_scm.c" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
anchor = "/**\n * qcom_scm_qseecom_call()"
if s.count(anchor) != 1:
    raise ValueError("Pinned SCM listener insertion point changed")
p.write_text(s.replace(anchor, '#include "rmx2072-listener.inc"\n\n' + anchor))
PY
sha256sum "$LISTENER" > "$ARTIFACT_DIR/listener.sha256"
cp "$ROOT_DIR/artifacts/gki-6.18-kernel-build/resolved-manifest.xml" "$ARTIFACT_DIR/"
cp "$ROOT_DIR/artifacts/gki-6.18-kernel-build/build-metadata.txt" "$ARTIFACT_DIR/"
mkdir -p "$WORKSPACE/rmx2072/bootstrap"
cp -a "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/." "$WORKSPACE/rmx2072/bootstrap/"
cd "$WORKSPACE"
tools/bazel --output_user_root="${RUNNER_TEMP:-/tmp}/bazel-output-root" run \
  --jobs=2 --local_resources=cpu=2 --local_resources=memory=5500 --verbose_failures \
  //rmx2072/bootstrap:sm8250_bootstrap_dist -- --destdir="$ARTIFACT_DIR/dist" \
  2>&1 | tee "$ARTIFACT_DIR/build.log"
test -s "$ARTIFACT_DIR/dist/Image.gz"
python3 "$ROOT_DIR/scripts/build/check_config_fragment.py" \
  --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
  --fragment "$ROOT_DIR/device/realme/bladerunner_48m/bootstrap/sm8250_defconfig"
python3 "$ROOT_DIR/scripts/device_audit/audit_bootstrap_config.py" \
  --config "$ARTIFACT_DIR/dist/sm8250_bootstrap_dot_config" \
  --output "$ARTIFACT_DIR/platform-config-audit.json"
find "$ARTIFACT_DIR/dist" -type f -print0 | sort -z | xargs -0 -r sha256sum > "$ARTIFACT_DIR/SHA256SUMS"
printf '%s\n' 'Platform compile candidate: Qualcomm hardware mutex and APSS watchdog required built-in. Physical kernel execution is not established by this build.' > "$ARTIFACT_DIR/STATUS.txt"
