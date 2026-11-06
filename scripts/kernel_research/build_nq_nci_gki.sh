#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK_FILE="$ROOT_DIR/sources/SOURCE_LOCK.json"
KERNEL_SRC="${RUNNER_TEMP:-/tmp}/android-kernel-common"
KERNEL_OUT="${RUNNER_TEMP:-/tmp}/android-kernel-out"
ARTIFACT_DIR="$ROOT_DIR/artifacts/nfc-nq-gki-smoke"

GKI_REF="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(s["ref"] for s in d["sources"] if s["id"]=="android17-gki-618"))' "$LOCK_FILE")"
GKI_SHA="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(s["commit"] for s in d["sources"] if s["id"]=="android17-gki-618"))' "$LOCK_FILE")"

mkdir -p "$ARTIFACT_DIR" "$KERNEL_SRC" "$KERNEL_OUT"

{
  echo "GKI_REF=$GKI_REF"
  echo "GKI_SHA=$GKI_SHA"
  echo "BUILD_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "HOST=$(uname -a)"
  clang --version | head -n 1 || true
  make --version | head -n 1 || true
} | tee "$ARTIFACT_DIR/build-metadata.txt"

if [[ ! -d "$KERNEL_SRC/.git" ]]; then
  git -C "$KERNEL_SRC" init
  git -C "$KERNEL_SRC" remote add origin https://android.googlesource.com/kernel/common
fi

git -C "$KERNEL_SRC" fetch --depth=1 origin \
  "refs/tags/$GKI_REF:refs/tags/$GKI_REF"
git -C "$KERNEL_SRC" checkout --detach "refs/tags/$GKI_REF"
ACTUAL_SHA="$(git -C "$KERNEL_SRC" rev-parse HEAD)"
if [[ "$ACTUAL_SHA" != "$GKI_SHA" ]]; then
  echo "Pinned GKI SHA mismatch: expected $GKI_SHA, got $ACTUAL_SHA" >&2
  exit 1
fi

echo "Verified GKI source: $ACTUAL_SHA" | tee -a "$ARTIFACT_DIR/build-metadata.txt"

make -C "$KERNEL_SRC" O="$KERNEL_OUT" ARCH=arm64 LLVM=1 gki_defconfig \
  2>&1 | tee "$ARTIFACT_DIR/gki-defconfig.log"

"$KERNEL_SRC/scripts/config" --file "$KERNEL_OUT/.config" \
  -e MODULES -e I2C -e GPIOLIB -e OF -e PM -e REGULATOR -e COMPAT

make -C "$KERNEL_SRC" O="$KERNEL_OUT" ARCH=arm64 LLVM=1 olddefconfig \
  2>&1 | tee "$ARTIFACT_DIR/olddefconfig.log"

grep -E '^(CONFIG_(MODULES|I2C|GPIOLIB|OF|PM|REGULATOR|COMPAT|MODVERSIONS)=|# CONFIG_(MODULES|I2C|GPIOLIB|OF|PM|REGULATOR|COMPAT|MODVERSIONS) is not set)' \
  "$KERNEL_OUT/.config" > "$ARTIFACT_DIR/relevant-config.txt" || true

make -C "$KERNEL_SRC" O="$KERNEL_OUT" ARCH=arm64 LLVM=1 -j2 modules_prepare \
  2>&1 | tee "$ARTIFACT_DIR/modules-prepare.log"

make -C "$KERNEL_SRC" O="$KERNEL_OUT" ARCH=arm64 LLVM=1 \
  M="$ROOT_DIR/experiments/nfc_nq" KBUILD_MODPOST_WARN=1 modules \
  2>&1 | tee "$ARTIFACT_DIR/module-build.log"

MODULE_PATH="$ROOT_DIR/experiments/nfc_nq/nq-nci.ko"
if [[ ! -f "$MODULE_PATH" ]]; then
  echo "Expected module was not produced: $MODULE_PATH" >&2
  exit 1
fi

cp "$MODULE_PATH" "$ARTIFACT_DIR/nq-nci.ko"
cp "$KERNEL_OUT/.config" "$ARTIFACT_DIR/gki.config"

# Capture the module's unresolved imports and compare them with the checked-in
# GKI KMI symbol lists. This is a preliminary allow-list audit; Module.symvers
# and the protected-export policy still need a complete GKI build.
llvm-nm -u "$ARTIFACT_DIR/nq-nci.ko" > "$ARTIFACT_DIR/module-undefined-symbols.raw"
awk 'NF { print $NF }' "$ARTIFACT_DIR/module-undefined-symbols.raw" \
  | sort -u > "$ARTIFACT_DIR/module-undefined-symbols.txt"

mapfile -t KMI_FILES < <(find "$KERNEL_SRC/android" -maxdepth 1 -type f \
  -name 'abi_gki_aarch64*' ! -name '*.stg' ! -name '*.xml' | sort)
if (( ${#KMI_FILES[@]} > 0 )); then
  cat "${KMI_FILES[@]}" \
    | sed 's/#.*$//' \
    | awk 'NF { print $1 }' \
    | sort -u > "$ARTIFACT_DIR/gki-kmi-symbols.txt"
  comm -12 "$ARTIFACT_DIR/module-undefined-symbols.txt" \
    "$ARTIFACT_DIR/gki-kmi-symbols.txt" > "$ARTIFACT_DIR/module-imports-in-kmi.txt"
  comm -23 "$ARTIFACT_DIR/module-undefined-symbols.txt" \
    "$ARTIFACT_DIR/gki-kmi-symbols.txt" > "$ARTIFACT_DIR/module-imports-not-in-kmi.txt"
  echo "KMI symbol-list files: ${#KMI_FILES[@]}" >> "$ARTIFACT_DIR/build-metadata.txt"
  echo "Module undefined imports: $(wc -l < "$ARTIFACT_DIR/module-undefined-symbols.txt")" >> "$ARTIFACT_DIR/build-metadata.txt"
  echo "Imports present in KMI lists: $(wc -l < "$ARTIFACT_DIR/module-imports-in-kmi.txt")" >> "$ARTIFACT_DIR/build-metadata.txt"
  echo "Imports absent from KMI lists: $(wc -l < "$ARTIFACT_DIR/module-imports-not-in-kmi.txt")" >> "$ARTIFACT_DIR/build-metadata.txt"
else
  echo "KMI symbol list not found in pinned source tree" >> "$ARTIFACT_DIR/build-metadata.txt"
fi

if [[ -f "$KERNEL_SRC/android/abi_gki_protected_exports" ]]; then
  sed 's/#.*$//' "$KERNEL_SRC/android/abi_gki_protected_exports" \
    | awk 'NF { print $1 }' | sort -u > "$ARTIFACT_DIR/gki-protected-exports.txt"
  comm -12 "$ARTIFACT_DIR/module-undefined-symbols.txt" \
    "$ARTIFACT_DIR/gki-protected-exports.txt" > "$ARTIFACT_DIR/module-imports-protected.txt"
fi
if [[ -f "$KERNEL_OUT/Module.symvers" ]]; then
  cp "$KERNEL_OUT/Module.symvers" "$ARTIFACT_DIR/Module.symvers"
  echo "Module.symvers=present" >> "$ARTIFACT_DIR/build-metadata.txt"
else
  echo "Module.symvers=absent (modules_prepare-only; KMI not certified)" \
    >> "$ARTIFACT_DIR/build-metadata.txt"
fi

file "$ARTIFACT_DIR/nq-nci.ko" | tee "$ARTIFACT_DIR/module-file.txt"
sha256sum "$ARTIFACT_DIR/nq-nci.ko" "$ARTIFACT_DIR/gki.config" \
  | tee "$ARTIFACT_DIR/SHA256SUMS"

if command -v modinfo >/dev/null 2>&1; then
  modinfo "$ARTIFACT_DIR/nq-nci.ko" > "$ARTIFACT_DIR/modinfo.txt" || true
fi

echo "Compile smoke test completed. This does not certify GKI KMI compatibility or device operation."
