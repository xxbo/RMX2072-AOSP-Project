#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE="${RUNNER_TEMP:-/tmp}/android17-gki-618"
BAZEL_ROOT="${RUNNER_TEMP:-/tmp}/bazel-output-root"
ARTIFACT_DIR="$ROOT_DIR/artifacts/nfc-nq-ddk"
mkdir -p "$ARTIFACT_DIR" "$WORKSPACE/rmx2072/nfc_nq"
cp -a "$ROOT_DIR/experiments/nfc_nq/." "$WORKSPACE/rmx2072/nfc_nq/"
cd "$WORKSPACE"

# Use the same Kleaf kernel target/toolchain/config/symbol versions as the full build.
# Deliberately do not set KBUILD_MODPOST_WARN or ignore failures.
tools/bazel --output_user_root="$BAZEL_ROOT" build \
  --jobs=2 --local_cpu_resources=2 --local_ram_resources=5500 --verbose_failures \
  //rmx2072/nfc_nq:nq_nci 2>&1 | tee "$ARTIFACT_DIR/build.log"

tools/bazel --output_user_root="$BAZEL_ROOT" cquery --output=files \
  //rmx2072/nfc_nq:nq_nci > "$ARTIFACT_DIR/output-files.txt"
while IFS= read -r path; do
  if [[ "$path" == *.ko ]]; then cp "$path" "$ARTIFACT_DIR/"; fi
done < "$ARTIFACT_DIR/output-files.txt"
test -s "$ARTIFACT_DIR/nq-nci.ko"
llvm-nm -u "$ARTIFACT_DIR/nq-nci.ko" > "$ARTIFACT_DIR/undefined-symbols.txt"
modinfo "$ARTIFACT_DIR/nq-nci.ko" > "$ARTIFACT_DIR/modinfo.txt"
sha256sum "$ARTIFACT_DIR/nq-nci.ko" > "$ARTIFACT_DIR/SHA256SUMS"
printf '%s\n' 'Strict DDK build passed; module load, KMI policy and physical NFC remain untested.' > "$ARTIFACT_DIR/STATUS.txt"
