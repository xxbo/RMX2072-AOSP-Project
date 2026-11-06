#!/usr/bin/env python3
"""Targeted KGSL / Adreno source comparison for immutable kernel revisions.

Downloads only selected source files. This is a read-only static analysis tool:
no full source clone, kernel build, module load, device boot or firmware download.
"""

import argparse
import base64
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = "RMX2072-KGSL-Research/1.0"
GITHUB_RAW = "https://raw.githubusercontent.com"
GITILES = "https://android.googlesource.com/kernel/common"

LEGACY_FILES = [
    "drivers/gpu/msm/Kconfig", "drivers/gpu/msm/Makefile",
    "drivers/gpu/msm/kgsl.c", "drivers/gpu/msm/kgsl_ioctl.c",
    "drivers/gpu/msm/kgsl_mmu.c", "drivers/gpu/msm/kgsl_iommu.c",
    "drivers/gpu/msm/kgsl_sharedmem.c", "drivers/gpu/msm/kgsl_pwrctrl.c",
    "drivers/gpu/msm/kgsl_pwrscale.c", "drivers/gpu/msm/kgsl_sync.c",
    "drivers/gpu/msm/kgsl_gmu.c", "drivers/gpu/msm/kgsl_gmu_core.c",
    "drivers/gpu/msm/kgsl_hfi.c", "drivers/gpu/msm/adreno.c",
    "drivers/gpu/msm/adreno_a6xx.c", "drivers/gpu/msm/adreno_a6xx_gmu.c",
    "drivers/gpu/msm/adreno_a6xx_preempt.c", "drivers/gpu/msm/kgsl_reclaim.c",
    "drivers/gpu/msm/kgsl_timeline.c", "include/uapi/linux/msm_kgsl.h",
]

MODERN_EXTRA_FILES = [
    "kgsl_vbo.c", "adreno_a6xx_hfi.c", "adreno_a6xx_hwsched.c",
    "adreno_a6xx_hwsched_hfi.c", "adreno_a6xx_rpmh.c",
    "adreno_a6xx_coresight.c", "adreno-gpulist.h", "kgsl_bus.c",
]

GKI_FILES = [
    "drivers/gpu/drm/msm/Kconfig", "drivers/gpu/drm/msm/Makefile",
    "drivers/gpu/drm/msm/msm_drv.c", "drivers/gpu/drm/msm/msm_drv.h",
    "drivers/gpu/drm/msm/msm_gpu.c", "drivers/gpu/drm/msm/msm_gpu.h",
    "drivers/gpu/drm/msm/msm_gem.c", "drivers/gpu/drm/msm/msm_gem.h",
    "drivers/gpu/drm/msm/msm_ringbuffer.c", "drivers/gpu/drm/msm/msm_submitqueue.c",
    "drivers/gpu/drm/msm/adreno/adreno_device.c",
    "drivers/gpu/drm/msm/adreno/adreno_gpu.c",
    "drivers/gpu/drm/msm/adreno/adreno_gpu.h",
    "drivers/gpu/drm/msm/adreno/a6xx_catalog.c",
    "drivers/gpu/drm/msm/adreno/a6xx_gpu.c",
    "drivers/gpu/drm/msm/adreno/a6xx_gpu.h",
    "drivers/gpu/drm/msm/adreno/a6xx_gmu.c",
    "drivers/gpu/drm/msm/adreno/a6xx_gmu.h",
    "drivers/gpu/drm/msm/adreno/a6xx_hfi.c",
    "drivers/gpu/drm/msm/adreno/a6xx_preempt.c",
    "include/uapi/drm/msm_drm.h",
    "arch/arm64/configs/gki_defconfig",
    "arch/arm64/Kconfig.platforms",
    "drivers/soc/qcom/Kconfig",
    "drivers/firmware/qcom/Kconfig",
    "drivers/nvmem/qcom/Kconfig",
    "drivers/vfio/Kconfig",
    "drivers/nvmem/Kconfig",
    "lib/Kconfig",
    "include/trace/hooks/mm.h",
    "drivers/android/vendor_hooks.c",
    "include/linux/shmem_fs.h",
    "android/abi_gki_aarch64",
    "android/abi_gki_aarch64_oplus",
    "android/abi_gki_aarch64.stg",
    "include/linux/android_vendor.h",
    "init/Kconfig.gki",
    "init/Kconfig",
    "drivers/android/Kconfig",
]

MODERN_PATHS = {
    "drivers/gpu/msm/Kconfig": "Kconfig",
    "drivers/gpu/msm/Makefile": "Makefile",
    "include/uapi/linux/msm_kgsl.h": "include/uapi/linux/msm_kgsl.h",
}


def request_bytes(url, timeout=60):
    for attempt in range(5):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:500]
            if exc.code == 404:
                return None
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise RuntimeError("HTTP %s %s: %s" % (exc.code, url, body))
            time.sleep(min(2 ** attempt, 12))
        except (URLError, TimeoutError) as exc:
            if attempt == 4:
                raise RuntimeError("Network error %s: %s" % (url, exc))
            time.sleep(min(2 ** attempt, 12))
    return None


def github_raw(repo, commit, path):
    data = request_bytes("%s/%s/%s/%s" % (GITHUB_RAW, repo, commit, path))
    return None if data is None else data.decode("utf-8", "replace")


def gitiles_raw(commit, path):
    data = request_bytes("%s/+/%s/%s?format=TEXT" % (GITILES, commit, path))
    return None if data is None else base64.b64decode(data).decode("utf-8", "replace")


def gitiles_json(commit, path):
    data = request_bytes("%s/+/%s/%s?format=JSON" % (GITILES, commit, path.rstrip("/") + "/"))
    if data is None:
        return None
    text = re.sub(r"^\)\]\}'\s*", "", data.decode("utf-8", "replace"))
    return json.loads(text)


def modern_path(path):
    if path in MODERN_PATHS:
        return MODERN_PATHS[path]
    if path.startswith("drivers/gpu/msm/"):
        return path.rsplit("/", 1)[-1]
    return path


def parse_functions(text):
    # Approximate C function-definition inventory, not a compiler AST.
    pattern = re.compile(
        r"(?m)^[ \t]*(?:(?:static|inline|extern|const|__init|__exit|"
        r"__maybe_unused|__always_inline|noinline)\s+)*"
        r"(?:[A-Za-z_]\w*(?:\s+|\s*\*\s*))+"
        r"([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"
    )
    excluded = {"if", "for", "while", "switch", "return", "sizeof"}
    return sorted({m.group(1) for m in pattern.finditer(text) if m.group(1) not in excluded})


def parse_ioctl_blocks(text):
    result, lines, i = {}, text.splitlines(), 0
    while i < len(lines):
        match = re.match(r"^\s*#define\s+(IOCTL_KGSL_[A-Z0-9_]+)\b(.*)$", lines[i])
        if not match:
            i += 1
            continue
        name, block = match.group(1), [lines[i].strip()]
        while block[-1].endswith("\\") and i + 1 < len(lines):
            i += 1
            block.append(lines[i].strip())
        result[name] = "\n".join(block)
        i += 1
    return result


def parse_struct_blocks(text):
    # Brace-balanced extraction of KGSL UAPI struct definitions.
    clean = re.sub(r"/\*.*?\*/|//[^\n]*",
                   lambda match: " " * len(match.group()), text, flags=re.S)
    result = {}
    for match in re.finditer(r"\bstruct\s+(kgsl_[A-Za-z0-9_]+)\s*\{", clean):
        name = match.group(1)
        opening = clean.find("{", match.start())
        depth = 0
        for pos in range(opening, len(clean)):
            if clean[pos] == "{":
                depth += 1
            elif clean[pos] == "}":
                depth -= 1
                if depth == 0:
                    end = clean.find(";", pos)
                    if end < 0:
                        end = pos
                    result[name] = text[match.start():end + 1]
                    break
    return result


def normalize_struct(text):
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    return re.sub(r"\s+", " ", text).strip()


def normalize_struct_arm64(text):
    # Normalize UAPI integer aliases to their arm64 widths for a first-pass
    # layout comparison. This is not a substitute for sizeof/offsetof tests.
    value = normalize_struct(text)
    aliases = [
        (r"\b(?:uint64_t|__u64|u64|unsigned long long|unsigned long)\b", "U64"),
        (r"\b(?:uint32_t|__u32|u32|unsigned int)\b", "U32"),
        (r"\b(?:uint16_t|__u16|u16|unsigned short)\b", "U16"),
        (r"\b(?:uint8_t|__u8|u8|unsigned char)\b", "U8"),
        (r"\b(?:int64_t|__s64|s64|long long)\b", "S64"),
        (r"\b(?:int32_t|__s32|s32|int)\b", "S32"),
        (r"\b(?:size_t|__kernel_size_t)\b", "KSIZE64"),
    ]
    for pattern, replacement in aliases:
        value = re.sub(pattern, replacement, value)
    return value


def parse_symbols(text):
    return {
        "functions": parse_functions(text),
        "includes": sorted(set(re.findall(r'(?m)^\s*#include\s*[<"]([^>"]+)[>"]', text))),
        "ioctls": sorted(parse_ioctl_blocks(text)),
        "structs": sorted(set(re.findall(r"\bstruct\s+(kgsl_[A-Za-z0-9_]+|drm_msm_[A-Za-z0-9_]+)\b", text))),
    }


def file_metrics(text, source_id, path):
    symbols = parse_symbols(text)
    markers = [
        "KGSL_IOC_TYPE", "IOCTL_KGSL_", "/dev/kgsl-3d0", "KGSL_GPUOBJ_ALLOC",
        "kgsl_reclaim", "shmem_file_setup", "shrinker", "dma_buf", "dma_fence",
        "kgsl_timeline", "hfi_send_cmd", "a650_gmu.bin", "a650_sqe.fw",
        "0x06050002", "revn = 650", "ADRENO_REV",
    ]
    return {
        "source": source_id, "path": path,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "chars": len(text), "lines": len(text.splitlines()),
        "function_count": len(symbols["functions"]), "functions": symbols["functions"],
        "include_count": len(symbols["includes"]), "includes": symbols["includes"],
        "ioctl_count": len(symbols["ioctls"]), "ioctls": symbols["ioctls"],
        "struct_count": len(symbols["structs"]), "structs": symbols["structs"],
        "markers": {m: text.count(m) for m in markers if m in text},
    }


def compare_text(left, right, left_name, right_name):
    left_lines, right_lines = left.splitlines(), right.splitlines()
    diff = list(difflib.unified_diff(left_lines, right_lines,
                                    fromfile=left_name, tofile=right_name,
                                    lineterm="", n=2))
    added = [x[1:] for x in diff if x.startswith("+") and not x.startswith("+++")]
    removed = [x[1:] for x in diff if x.startswith("-") and not x.startswith("---")]
    a, b = parse_symbols(left), parse_symbols(right)
    return {
        "left": left_name, "right": right_name,
        "left_lines": len(left_lines), "right_lines": len(right_lines),
        "added_lines": len(added), "removed_lines": len(removed),
        "same_sha256": hashlib.sha256(left.encode()).hexdigest() == hashlib.sha256(right.encode()).hexdigest(),
        "functions_added": sorted(set(b["functions"]) - set(a["functions"])),
        "functions_removed": sorted(set(a["functions"]) - set(b["functions"])),
        "includes_added": sorted(set(b["includes"]) - set(a["includes"])),
        "includes_removed": sorted(set(a["includes"]) - set(b["includes"])),
        "added_samples": added[:8], "removed_samples": removed[:8],
    }


def parse_config_values(text):
    values = {}
    for line in text.splitlines():
        enabled = re.match(r"^(CONFIG_[A-Z0-9_]+)=(.*)$", line.strip())
        disabled = re.match(r"^# (CONFIG_[A-Z0-9_]+) is not set$", line.strip())
        if enabled:
            values[enabled.group(1)] = enabled.group(2)
        elif disabled:
            values[disabled.group(1)] = "n"
    return values


def source_record(lock, source_id):
    for source in lock.get("sources", []):
        if source.get("id") == source_id:
            return source
    raise RuntimeError("Source lock entry missing: " + source_id)


def fetch_source_files(lock, source_id, paths, kind):
    source = source_record(lock, source_id)
    result = {"id": source_id, "repo": source["repository"], "commit": source["commit"],
              "kernel_version": source.get("kernel_version"), "files": {}, "errors": []}
    for path in paths:
        try:
            actual = modern_path(path) if kind == "modern" else path
            text = gitiles_raw(source["commit"], path) if kind == "gitiles" else github_raw(source["repository"], source["commit"], actual)
            result["files"][path] = {
                "actual_path": actual, "text": text, "missing": text is None,
                "metrics": file_metrics(text, source_id, actual) if text is not None else None,
            }
        except Exception as exc:
            result["errors"].append("%s: %s" % (path, exc))
            result["files"][path] = {"actual_path": path, "text": None, "missing": True, "metrics": None}
    return result


def parse_struct_field_names(block):
    body = block[block.find("{") + 1:block.rfind("}")]
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", body, flags=re.S)
    body = re.sub(r"(?m)^\s*#.*$", "", body)
    if "{" in body or "}" in body:
        return []
    fields = []
    for declaration in body.split(";"):
        declaration = declaration.strip()
        if not declaration or "," in declaration:
            continue
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?\s*(?::\s*\d+)?$", declaration)
        if match:
            fields.append(match.group(1))
    return sorted(set(fields))


def probe_uapi_layout(source_id, header_text, compiler, workdir):
    if not compiler:
        return {"status": "skipped", "reason": "No host C compiler found"}
    source_dir = os.path.join(workdir, source_id)
    os.makedirs(source_dir, exist_ok=True)
    header_path = os.path.join(source_dir, "msm_kgsl.h")
    source_path = os.path.join(source_dir, "layout_probe.c")
    binary_path = os.path.join(source_dir, "layout_probe")
    with open(header_path, "w", encoding="utf-8") as handle:
        handle.write(header_text)

    structs = parse_struct_blocks(header_text)
    lines = [
        "#include <stddef.h>",
        "#include <stdint.h>",
        "#include <stdio.h>",
        "#ifndef __user",
        "#define __user",
        "#endif",
        '#include "msm_kgsl.h"',
        "int main(void) {",
    ]
    for name, block in sorted(structs.items()):
        lines.append('printf("S|%s|%%zu\\n", sizeof(struct %s));' % (name, name))
        for field in parse_struct_field_names(block):
            lines.append('printf("F|%s|%s|%%zu\\n", offsetof(struct %s, %s));' %
                         (name, field, name, field))
    lines.extend(["return 0;", "}"])
    with open(source_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    command = [compiler, "-m64", "-std=gnu11", "-Wno-unused", "-I", source_dir,
               source_path, "-o", binary_path]
    try:
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if compiled.returncode != 0:
            return {"status": "failed", "compiler": os.path.basename(compiler),
                    "stderr": compiled.stderr[-3000:], "struct_count": len(structs)}
        executed = subprocess.run([binary_path], capture_output=True, text=True, timeout=30)
        if executed.returncode != 0:
            return {"status": "failed", "compiler": os.path.basename(compiler),
                    "stderr": executed.stderr[-3000:], "struct_count": len(structs)}
        sizes, offsets = {}, {}
        for line in executed.stdout.splitlines():
            parts = line.split("|")
            if len(parts) == 3 and parts[0] == "S":
                sizes[parts[1]] = int(parts[2])
            elif len(parts) == 4 and parts[0] == "F":
                offsets.setdefault(parts[1], {})[parts[2]] = int(parts[3])
        return {
            "status": "passed",
            "compiler": os.path.basename(compiler),
            "data_model": "LP64 host probe (-m64); same standard integer/pointer widths as arm64, not an AArch64 cross-compile",
            "struct_count": len(sizes),
            "field_offset_count": sum(len(value) for value in offsets.values()),
            "sizes": sizes,
            "offsets": offsets,
        }
    except Exception as exc:
        return {"status": "failed", "compiler": os.path.basename(compiler), "error": str(exc)}


def compare_layout_probes(probes):
    order = ["realme-player-android-q-kernel", "sm8250-common-current-kernel",
             "qualcomm-linux-kgsl-modern-reference"]
    available = [key for key in order if probes.get(key, {}).get("status") == "passed"]
    comparisons = []
    for i in range(len(available) - 1):
        left_id, right_id = available[i], available[i + 1]
        left, right = probes[left_id], probes[right_id]
        common_structs = set(left["sizes"]) & set(right["sizes"])
        size_changed = sorted(name for name in common_structs
                              if left["sizes"][name] != right["sizes"][name])
        offset_changed = []
        for name in sorted(common_structs):
            left_fields = left["offsets"].get(name, {})
            right_fields = right["offsets"].get(name, {})
            for field in sorted(set(left_fields) & set(right_fields)):
                if left_fields[field] != right_fields[field]:
                    offset_changed.append({
                        "struct": name, "field": field,
                        "left": left_fields[field], "right": right_fields[field],
                    })
        comparisons.append({
            "left": left_id, "right": right_id,
            "common_struct_count": len(common_structs),
            "size_changed": size_changed,
            "field_offsets_changed": offset_changed,
        })
    return comparisons


def compare_uapi(sources):
    ids = ["realme-player-android-q-kernel", "sm8250-common-current-kernel",
           "qualcomm-linux-kgsl-modern-reference"]
    available = {}
    for source_id in ids:
        item = sources[source_id]["files"].get("include/uapi/linux/msm_kgsl.h")
        if item and item["text"] is not None:
            text = item["text"]
            available[source_id] = {
                "ioctls": parse_ioctl_blocks(text),
                "structs": parse_struct_blocks(text),
            }
    order = [x for x in ids if x in available]
    result = []
    for i in range(len(order) - 1):
        left_id, right_id = order[i], order[i + 1]
        left, right = available[left_id], available[right_id]
        common = set(left["ioctls"]) & set(right["ioctls"])
        result.append({
            "left": left_id, "right": right_id,
            "left_ioctl_count": len(left["ioctls"]), "right_ioctl_count": len(right["ioctls"]),
            "ioctls_added": sorted(set(right["ioctls"]) - set(left["ioctls"])),
            "ioctls_removed": sorted(set(left["ioctls"]) - set(right["ioctls"])),
            "ioctl_definitions_changed": sorted(k for k in common if left["ioctls"][k] != right["ioctls"][k]),
            "left_struct_count": len(left["structs"]), "right_struct_count": len(right["structs"]),
            "structs_added": sorted(set(right["structs"]) - set(left["structs"])),
            "structs_removed": sorted(set(left["structs"]) - set(right["structs"])),
            "struct_definitions_changed": sorted(
                name for name in set(left["structs"]) & set(right["structs"])
                if normalize_struct(left["structs"][name]) != normalize_struct(right["structs"][name])
            ),
            "arm64_layout_candidates": sorted(
                name for name in set(left["structs"]) & set(right["structs"])
                if normalize_struct_arm64(left["structs"][name]) != normalize_struct_arm64(right["structs"][name])
            ),
        })
    return result


def parse_kconfig(text):
    result, current = {}, None
    for line in text.splitlines():
        match = re.match(r"^\s*(?:menu)?config\s+([A-Z0-9_]+)", line)
        if match:
            current = match.group(1)
            result[current] = {"depends_on": [], "selects": []}
            continue
        if current:
            dep = re.match(r"^\s*depends on\s+(.+)", line)
            sel = re.match(r"^\s*select\s+([A-Z0-9_]+)", line)
            if dep:
                result[current]["depends_on"].append(dep.group(1).strip())
            if sel:
                result[current]["selects"].append(sel.group(1))
            if line and not line[0].isspace():
                current = None
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", default="sources/SOURCE_LOCK.json")
    parser.add_argument("--out", default="reports/kgsl-content-research")
    args = parser.parse_args()
    with open(args.lock, "r", encoding="utf-8") as handle:
        lock = json.load(handle)

    ids = ["realme-player-android-q-kernel", "sm8250-common-current-kernel",
           "qualcomm-linux-kgsl-modern-reference"]
    sources = {}
    for source_id in ids:
        kind = "modern" if source_id.endswith("modern-reference") else "github"
        sources[source_id] = fetch_source_files(lock, source_id, LEGACY_FILES, kind)

    modern = sources["qualcomm-linux-kgsl-modern-reference"]
    for path in MODERN_EXTRA_FILES:
        try:
            text = github_raw(modern["repo"], modern["commit"], path)
            modern["files"][path] = {
                "actual_path": path, "text": text, "missing": text is None,
                "metrics": file_metrics(text, modern["id"], path) if text is not None else None,
            }
        except Exception as exc:
            modern["errors"].append("%s: %s" % (path, exc))
            modern["files"][path] = {"actual_path": path, "text": None, "missing": True, "metrics": None}

    legacy, current = sources[ids[0]], sources[ids[1]]
    legacy_vs_current, current_vs_modern, file_presence_changes = [], [], []
    for path in LEGACY_FILES:
        old_present = legacy["files"][path]["text"] is not None
        current_present = current["files"][path]["text"] is not None
        if old_present != current_present:
            file_presence_changes.append({
                "path": path,
                "old_present": old_present,
                "current_present": current_present,
                "change": "added in community tree" if current_present else "missing in community tree",
            })
        left = legacy["files"][path]["text"]
        right = current["files"][path]["text"]
        if left is not None and right is not None:
            item = compare_text(left, right, "4.19.81/" + path, "4.19.325/" + path)
            item["path"] = path
            legacy_vs_current.append(item)
        modern_item = modern["files"].get(path, {})
        modern_text = modern_item.get("text")
        if right is not None and modern_text is not None:
            item = compare_text(right, modern_text,
                                "4.19.325/" + path,
                                "Qualcomm-KGSL/" + modern_item["actual_path"])
            item["legacy_path"] = path
            item["modern_path"] = modern_item["actual_path"]
            current_vs_modern.append(item)

    modern_extras = [{"path": p, "metrics": modern["files"][p]["metrics"]}
                     for p in MODERN_EXTRA_FILES]

    gki = fetch_source_files(lock, "android17-gki-618", GKI_FILES, "gitiles")
    drm_msm_dir = gitiles_json(gki["commit"], "drivers/gpu/drm/msm")
    kgsl_dir = gitiles_json(gki["commit"], "drivers/gpu/msm")
    gki["drm_msm_directory_present"] = drm_msm_dir is not None
    gki["kgsl_directory_present"] = kgsl_dir is not None
    gki["kgsl_uapi_present"] = gitiles_raw(gki["commit"], "include/uapi/linux/msm_kgsl.h") is not None
    gki["drm_uapi_present"] = gki["files"].get("include/uapi/drm/msm_drm.h", {}).get("text") is not None
    catalog = gki["files"].get("drivers/gpu/drm/msm/adreno/a6xx_catalog.c", {}).get("text") or ""
    gpu = gki["files"].get("drivers/gpu/drm/msm/adreno/a6xx_gpu.c", {}).get("text") or ""
    gmu = gki["files"].get("drivers/gpu/drm/msm/adreno/a6xx_gmu.c", {}).get("text") or ""
    gki["adreno_650_evidence"] = {
        "chip_id_0x06050002_in_catalog": "0x06050002" in catalog,
        "revn_650_in_catalog": bool(re.search(r"revn\s*=\s*650", catalog)),
        "a650_gmu_firmware_name_in_catalog": "a650_gmu.bin" in catalog,
        "a6xx_gpu_implementation_present": bool(gpu),
        "a6xx_gmu_implementation_present": bool(gmu),
    }
    gki_defconfig = gki["files"].get("arch/arm64/configs/gki_defconfig", {}).get("text") or ""
    gki_config_values = parse_config_values(gki_defconfig)
    kgsl_config_keys = [
        "CONFIG_ARCH_QCOM", "CONFIG_NVMEM_QCOM_QFPROM", "CONFIG_QCOM_QFPROM",
        "CONFIG_QCOM_MDT_LOADER", "CONFIG_INTERVAL_TREE", "CONFIG_TRACE_GPU_MEM",
        "CONFIG_SHMEM", "CONFIG_VFIO", "CONFIG_DRM_MSM", "CONFIG_DRM",
        "CONFIG_DMA_SHARED_BUFFER", "CONFIG_SYNC_FILE", "CONFIG_IOMMU_SUPPORT",
        "CONFIG_ANDROID_VENDOR_OEM_DATA",
    ]
    gki_config_evidence = {key: gki_config_values.get(key, "not explicit in gki_defconfig")
                           for key in kgsl_config_keys}
    gki_kconfig_files = [
        "arch/arm64/Kconfig.platforms", "drivers/soc/qcom/Kconfig",
        "drivers/firmware/qcom/Kconfig", "drivers/nvmem/Kconfig",
        "drivers/nvmem/qcom/Kconfig", "drivers/vfio/Kconfig", "lib/Kconfig",
        "drivers/gpu/drm/msm/Kconfig",
    ]
    gki_kconfig_definitions = {}
    for path in gki_kconfig_files:
        kconfig_text = gki["files"].get(path, {}).get("text") or ""
        parsed = parse_kconfig(kconfig_text)
        for symbol in ("ARCH_QCOM", "NVMEM_QCOM_QFPROM", "QCOM_QFPROM",
                       "QCOM_MDT_LOADER", "INTERVAL_TREE", "TRACE_GPU_MEM",
                       "VFIO", "SHMEM"):
            if symbol in parsed:
                gki_kconfig_definitions[symbol] = {
                    "file": path,
                    "depends_on": parsed[symbol]["depends_on"],
                    "selects": parsed[symbol]["selects"],
                }

    hook_header = gki["files"].get("include/trace/hooks/mm.h", {}).get("text") or ""
    vendor_hooks = gki["files"].get("drivers/android/vendor_hooks.c", {}).get("text") or ""
    shmem_header = gki["files"].get("include/linux/shmem_fs.h", {}).get("text") or ""
    abi_symbols = gki["files"].get("android/abi_gki_aarch64", {}).get("text") or ""
    oplus_abi_symbols = gki["files"].get("android/abi_gki_aarch64_oplus", {}).get("text") or ""
    abi_stg = gki["files"].get("android/abi_gki_aarch64.stg", {}).get("text") or ""
    android_vendor_header = gki["files"].get("include/linux/android_vendor.h", {}).get("text") or ""
    gki_kconfig = gki["files"].get("init/Kconfig.gki", {}).get("text") or ""
    modern_sharedmem = modern["files"].get("drivers/gpu/msm/kgsl_sharedmem.c", {}).get("text") or ""
    hook_match = re.search(
        r"DECLARE_RESTRICTED_HOOK\s*\(\s*android_rvh_shmem_get_folio\s*,\s*TP_PROTO\s*\((.*?)\)\s*,\s*TP_ARGS",
        hook_header, re.S)
    hook_proto = re.sub(r"\s+", " ", hook_match.group(1)).strip() if hook_match else None
    kgsl_callbacks = [
        re.sub(r"\s+", " ", match.group(1)).strip()
        for match in re.finditer(r"kgsl_shmem_fill_page\s*\((.*?)\)\s*\{", modern_sharedmem, re.S)
    ]
    hook_exported = "EXPORT_TRACEPOINT_SYMBOL_GPL(android_rvh_shmem_get_folio)" in vendor_hooks
    kmi_hook_symbols = [
        line.strip() for line in (abi_symbols + "\n" + oplus_abi_symbols).splitlines()
        if "shmem_get_folio" in line
    ]
    stg_hook_symbols = [
        line.strip() for line in abi_stg.splitlines()
        if "shmem_get_folio" in line
    ]
    android_dir = gitiles_json(gki["commit"], "android")
    android_abi_paths = sorted(
        entry.get("name", "") for entry in (android_dir or {}).get("entries", [])
        if "abi" in entry.get("name", "").lower() or "symbol" in entry.get("name", "").lower()
    )
    android_shmem_hook_evidence = {
        "android_directory_abi_related_entries": android_abi_paths,
        "hook_declared_in_gki_mm_hooks": bool(hook_match),
        "hook_tp_proto": hook_proto,
        "hook_exported_by_gki_vendor_hooks": hook_exported,
        "hook_symbol_lines_in_gki_or_oplus_abi_list": kmi_hook_symbols,
        "hook_symbol_present_in_gki_or_oplus_abi_list": bool(kmi_hook_symbols),
        "hook_symbol_lines_in_abi_stg": stg_hook_symbols,
        "shmem_inode_info_android_vendor_data_slot_present": "ANDROID_VENDOR_DATA(1)" in shmem_header,
        "android_vendor_data_macro_defined": "ANDROID_VENDOR_DATA" in android_vendor_header,
        "android_vendor_data_macro_definition_lines": [
            line.strip() for line in android_vendor_header.splitlines()
            if "ANDROID_VENDOR_DATA" in line
        ],
        "android_vendor_oem_data_config_default_y": bool(re.search(
            r"config ANDROID_VENDOR_OEM_DATA[\s\S]{0,1000}default y", gki_kconfig)),
        "shmem_inode_info_android_vendor_data1_literal_present": "android_vendor_data1" in shmem_header,
        "modern_kgsl_shmem_callbacks": kgsl_callbacks,
        "modern_kgsl_uses_android_shmem_hook": "register_trace_android_rvh_shmem_get_folio" in modern_sharedmem,
    }

    uapi_comparisons = compare_uapi(sources)
    compiler = shutil.which("gcc") or shutil.which("clang")
    uapi_layout_probes = {}
    with tempfile.TemporaryDirectory(prefix="kgsl-uapi-layout-") as tempdir:
        for source_id in ids:
            header = sources[source_id]["files"]["include/uapi/linux/msm_kgsl.h"]["text"]
            if header is not None:
                uapi_layout_probes[source_id] = probe_uapi_layout(source_id, header, compiler, tempdir)
    uapi_layout_comparisons = compare_layout_probes(uapi_layout_probes)

    kconfig_text = modern["files"].get("drivers/gpu/msm/Kconfig", {}).get("text") or ""
    modern_kconfig = parse_kconfig(kconfig_text)
    modern_gpu_list = modern["files"].get("adreno-gpulist.h", {}).get("text") or ""
    modern_adreno_650 = {
        "ADRENO_REV_A650 definition present": "ADRENO_REV_A650" in modern_gpu_list,
        "A650 firmware a650_gmu.bin referenced": "a650_gmu.bin" in modern_gpu_list,
        "A650 firmware a650_sqe.fw referenced": "a650_sqe.fw" in modern_gpu_list,
    }

    meta = source_record(lock, "qualcomm-meta-qcom-kgsl-build-reference")
    recipe = github_raw(meta["repository"], meta["commit"], "recipes-graphics/kgsl-dlkm/kgsl-dlkm_2.0.0.bb")
    extra_cfg = github_raw(meta["repository"], meta["commit"], "recipes-kernel/linux/linux-yocto-7.2/bsp/qcom-armv8a/qcom-extra.cfg")
    build_evidence = []
    if recipe:
        rev = re.search(r'(?m)^SRCREV\s*=\s*"([^"]+)"', recipe)
        lic = re.search(r'(?m)^LICENSE\s*=\s*"([^"]+)"', recipe)
        build_evidence.extend([
            "meta-qcom KGSL recipe fetched: yes",
            "recipe license: " + (lic.group(1) if lic else "not parsed"),
            "recipe SRCREV matches pinned KGSL source: " + str(bool(rev and rev.group(1) == modern["commit"])),
            "recipe uses Yocto module class: " + str(bool(re.search(r'(?m)^inherit\s+module\b', recipe))),
        ])
    else:
        build_evidence.append("meta-qcom KGSL recipe fetched: no")
    if extra_cfg:
        build_evidence.append("linux-yocto-7.2 config sets CONFIG_VFIO=m: " +
                              str(bool(re.search(r'(?m)^CONFIG_VFIO=m\s*$', extra_cfg))))
    else:
        build_evidence.append("linux-yocto-7.2 KGSL config fragment fetched: no")

    def compact_source(source):
        return {
            "repo": source["repo"], "commit": source["commit"],
            "kernel_version": source.get("kernel_version"),
            "files": {p: {"actual_path": x["actual_path"], "missing": x["missing"], "metrics": x["metrics"]}
                      for p, x in source["files"].items()},
            "errors": source["errors"],
        }

    report = {
        "schema_version": 1,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": {k: compact_source(v) for k, v in sources.items()},
        "legacy_vs_current": legacy_vs_current,
        "file_presence_changes": file_presence_changes,
        "current_vs_modern": current_vs_modern,
        "modern_extras": modern_extras,
        "uapi_comparisons": uapi_comparisons,
        "uapi_layout_probes": {
            key: {k: v for k, v in item.items() if k not in ("sizes", "offsets")}
            for key, item in uapi_layout_probes.items()
        },
        "uapi_layout_comparisons": uapi_layout_comparisons,
        "gki": {
            "repo": gki["repo"], "commit": gki["commit"],
            "files": {p: {"missing": x["missing"], "metrics": x["metrics"]} for p, x in gki["files"].items()},
            "errors": gki["errors"],
            "kgsl_directory_present": gki["kgsl_directory_present"],
            "drm_msm_directory_present": gki["drm_msm_directory_present"],
            "kgsl_uapi_present": gki["kgsl_uapi_present"],
            "drm_uapi_present": gki["drm_uapi_present"],
            "adreno_650_evidence": gki["adreno_650_evidence"],
            "config_evidence": gki_config_evidence,
            "kconfig_definitions": gki_kconfig_definitions,
            "android_shmem_hook_evidence": android_shmem_hook_evidence,
        },
        "modern_kconfig": modern_kconfig,
        "modern_adreno_650_evidence": modern_adreno_650,
        "build_evidence": build_evidence,
    }

    lines = [
        "# KGSL / Adreno 650 — Targeted Source Research", "",
        "- Snapshot: " + report["generated_at_utc"],
        "- Target: RMX2072 / Snapdragon 865 / SM8250 / Adreno 650",
        "- GKI baseline: " + gki["commit"],
        "- Method: immutable targeted raw-file retrieval; no full kernel clone",
        "- Scope: static source inventory and text-level comparison only; no build, load, boot or runtime test", "",
        "## 1. Source revisions", "",
        "| Source | Commit | Kernel / role |", "|---|---|---|",
    ]
    for key, item in report["sources"].items():
        lines.append("| %s | %s | %s |" % (key, item["commit"], item.get("kernel_version") or "reference"))
    lines.extend(["", "## 2. File coverage", "",
                  "| Source | Fetched | Missing optional files | Errors |", "|---|---:|---:|---:|"])
    for key, item in report["sources"].items():
        fetched = sum(1 for f in item["files"].values() if not f["missing"])
        missing = sum(1 for f in item["files"].values() if f["missing"])
        lines.append("| %s | %s | %s | %s |" % (key, fetched, missing, len(item["errors"])))
    lines.extend(["", "## 3. Official 4.19.81 versus community 4.19.325", "",
                  "| File | Old lines | Current lines | Added | Removed | Function names added | Function names removed |",
                  "|---|---:|---:|---:|---:|---:|---:|"])
    for item in legacy_vs_current:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            item["path"], item["left_lines"], item["right_lines"], item["added_lines"],
            item["removed_lines"], len(item["functions_added"]), len(item["functions_removed"])))
    lines.extend(["", "### File presence changes between official Q and community 4.19.325", ""])
    if file_presence_changes:
        for item in file_presence_changes:
            lines.append("- %s: %s" % (item["path"], item["change"]))
    else:
        lines.append("- No path presence changes in the selected file set.")
    lines.extend(["", "## 4. Community 4.19.325 versus modern Qualcomm KGSL", "",
                  "The Qualcomm reference is a separate kernel-module repository. Same-name files are compared as architecture references, not as proof of source ancestry or drop-in compatibility.",
                  "", "| Legacy file | Modern file | Legacy lines | Modern lines | Added | Removed |",
                  "|---|---|---:|---:|---:|---:|"])
    for item in current_vs_modern:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            item["legacy_path"], item["modern_path"], item["left_lines"],
            item["right_lines"], item["added_lines"], item["removed_lines"]))
    lines.extend(["", "### Additional modern Qualcomm files", ""])
    for item in modern_extras:
        m = item["metrics"]
        lines.append("- %s: %s" % (item["path"],
                    ("%s lines; %s detected functions" % (m["lines"], m["function_count"])) if m else "not present"))
    lines.extend(["", "## 5. KGSL userspace ABI inventory", "",
                  "| Comparison | Left ioctls | Right ioctls | Added | Removed | Changed ioctl definitions | Structs added | Structs removed | Text-changed structs | Arm64 layout candidates |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for item in uapi_comparisons:
        lines.append("| %s → %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            item["left"], item["right"], item["left_ioctl_count"], item["right_ioctl_count"],
            len(item["ioctls_added"]), len(item["ioctls_removed"]), len(item["ioctl_definitions_changed"]),
            len(item["structs_added"]), len(item["structs_removed"]),
            len(item["struct_definitions_changed"]), len(item["arm64_layout_candidates"])))
        if item["ioctls_added"]:
            lines.append("- Added ioctl names: " + ", ".join(item["ioctls_added"]))
        if item["ioctls_removed"]:
            lines.append("- Removed ioctl names: " + ", ".join(item["ioctls_removed"]))
        if item["ioctl_definitions_changed"]:
            lines.append("- Changed ioctl definitions: " + ", ".join(item["ioctl_definitions_changed"]))
        if item["structs_added"]:
            lines.append("- Added UAPI structs: " + ", ".join(item["structs_added"]))
        if item["structs_removed"]:
            lines.append("- Removed UAPI structs: " + ", ".join(item["structs_removed"]))
        if item["struct_definitions_changed"]:
            lines.append("- Struct definitions with text changes: " + ", ".join(item["struct_definitions_changed"]))
        if item["arm64_layout_candidates"]:
            lines.append("- Structs requiring ABI layout review: " + ", ".join(item["arm64_layout_candidates"]))
        else:
            lines.append("- No arm64 field-width/layout differences detected after normalizing standard UAPI integer aliases; compile-time sizeof/offsetof verification is still required.")
        lines.append("")
    lines.extend(["## 6. KGSL UAPI LP64 compile-time layout probe", "",
                  "The workflow compiles each pinned UAPI header with the runner's host C compiler in 64-bit LP64 mode, then records sizeof and offsetof values for parsed KGSL structs. This is a useful 64-bit ABI cross-check, but it is not an AArch64 cross-compile or a runtime userspace compatibility test.",
                  "",
                  "| Source | Probe status | Structs measured | Field offsets measured |",
                  "|---|---|---:|---:|"])
    for key, item in report["uapi_layout_probes"].items():
        lines.append("| %s | %s | %s | %s |" % (
            key, item["status"], item.get("struct_count", 0), item.get("field_offset_count", 0)))
    lines.append("")
    for item in report["uapi_layout_comparisons"]:
        lines.append("**%s → %s**: %s common structs; %s sizeof changes; %s field-offset changes." % (
            item["left"], item["right"], item["common_struct_count"],
            len(item["size_changed"]), len(item["field_offsets_changed"])))
        if item["size_changed"]:
            lines.append("- Size changes: " + ", ".join(item["size_changed"]))
        if item["field_offsets_changed"]:
            lines.append("- Offset changes: " + "; ".join(
                "%s.%s: %s → %s" % (x["struct"], x["field"], x["left"], x["right"])
                for x in item["field_offsets_changed"]))
        lines.append("")
    lines.extend(["", "## 7. Android 17 GKI 6.18 graphics architecture", "",
                  "- KGSL drivers/gpu/msm directory present: %s" % gki["kgsl_directory_present"],
                  "- DRM/MSM driver directory present: %s" % gki["drm_msm_directory_present"],
                  "- KGSL UAPI header present: %s" % gki["kgsl_uapi_present"],
                  "- DRM/MSM UAPI header present: %s" % gki["drm_uapi_present"],
                  "", "### Adreno 650 catalog evidence", ""])
    for key, value in gki["adreno_650_evidence"].items():
        lines.append("- %s: %s" % (key, value))
    lines.extend(["", "### GKI DRM/MSM source inventory", "",
                  "| File | Lines | Detected function definitions |", "|---|---:|---:|"])
    for path, item in gki["files"].items():
        m = item["metrics"]
        lines.append("| %s | %s | %s |" % (
            path, m["lines"] if m else "missing", m["function_count"] if m else "—"))
    lines.extend(["", "### GKI defconfig prerequisites relevant to modern KGSL", "",
                  "| Config | gki_defconfig value |", "|---|---|"])
    for key, value in report["gki"]["config_evidence"].items():
        lines.append("| %s | %s |" % (key, value))
    lines.extend(["", "Kconfig symbol definitions found in the pinned GKI tree:"])
    for key, item in report["gki"]["kconfig_definitions"].items():
        lines.append("- %s (%s): depends on %s; selects %s" % (
            key, item["file"], ", ".join(item["depends_on"]) or "none",
            ", ".join(item["selects"]) or "none"))
    lines.extend(["", "### Android shmem vendor-hook compatibility", ""])
    for key, value in report["gki"]["android_shmem_hook_evidence"].items():
        lines.append("- %s: %s" % (key, value))
    lines.extend(["", "### Modern Qualcomm KGSL Adreno 650 support", ""])
    for key, value in modern_adreno_650.items():
        lines.append("- %s: %s" % (key, value))
    lines.extend(["", "## 7. Build and Kconfig evidence", ""])
    lines.extend("- " + item for item in build_evidence)
    for key, item in modern_kconfig.items():
        if key in ("QCOM_KGSL", "QCOM_KGSL_USE_SHMEM", "QCOM_KGSL_PROCESS_RECLAIM", "QCOM_KGSL_HIBERNATION"):
            lines.append("- %s: depends on %s; selects %s" % (
                key, ", ".join(item["depends_on"]) or "none", ", ".join(item["selects"]) or "none"))
    lines.extend(["", "## 8. Preliminary migration interpretation", "",
        "1. The pinned Android 17 GKI tree is checked for both the legacy KGSL path and the DRM/MSM Adreno path. A6xx catalog support does not establish KGSL userspace compatibility.",
        "2. The separate Qualcomm KGSL repository is a promising newer KGSL reference, but the Yocto/Linux 7.2 recipe does not prove Android GKI 6.18 KMI compatibility.",
        "3. The next technical gate is to validate module compile dependencies, exported-symbol requirements, GKI KMI availability, device-tree integration and firmware names against the exact Android 17 GKI build.",
        "4. Ioctl-name inventories do not prove ABI compatibility. Struct layout, ioctl encoding, semantics and vendor userspace expectations require dedicated tests.",
        "", "## 9. Limitations", "",
        "- The UAPI compile-time layout probe uses the runner's x86_64 LP64 ABI, not a dedicated AArch64 cross-compiler; repeat with the exact Android/AOSP toolchain before treating the result as final.",
        "- Function detection is regex-based, not a full C parser or compiler AST.",
        "- Line additions/removals are text statistics, not semantic change scores.",
        "- No proprietary firmware, vendor libraries or device dumps are downloaded.",
        "- No kernel was compiled, module-loaded, booted or tested on RMX2072.",
        "", "## 10. Fetch errors", ""])
    errors = []
    for key, item in report["sources"].items():
        errors.extend(key + ": " + e for e in item["errors"])
    errors.extend("GKI: " + e for e in gki["errors"])
    lines.extend(["- " + e for e in errors] if errors else ["- None."])

    os.makedirs(args.out, exist_ok=True)
    json_path = os.path.join(args.out, "kgsl-adreno-research.json")
    md_path = os.path.join(args.out, "kgsl-adreno-research.md")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("# KGSL / Adreno 650 research\n\n")
            handle.write("- Legacy/current comparisons: %s\n" % len(legacy_vs_current))
            handle.write("- Current/modern KGSL comparisons: %s\n" % len(current_vs_modern))
            handle.write("- UAPI comparisons: %s\n" % len(uapi_comparisons))
            handle.write("- UAPI layout probes passed: %s\n" % sum(1 for item in uapi_layout_probes.values() if item.get("status") == "passed"))
            handle.write("- GKI KGSL directory present: %s\n" % gki["kgsl_directory_present"])
            handle.write("- GKI DRM/MSM directory present: %s\n" % gki["drm_msm_directory_present"])
            handle.write("- Reports uploaded as workflow artifacts.\n")

    print("KGSL research reports written:")
    print(" - " + md_path)
    print(" - " + json_path)
    for key, item in report["sources"].items():
        fetched = sum(1 for f in item["files"].values() if not f["missing"])
        print("[SOURCE] %s: %s/%s files fetched" % (key, fetched, len(item["files"])))
    print("[GKI] KGSL directory: %s; DRM/MSM: %s" %
          (gki["kgsl_directory_present"], gki["drm_msm_directory_present"]))


if __name__ == "__main__":
    main()
