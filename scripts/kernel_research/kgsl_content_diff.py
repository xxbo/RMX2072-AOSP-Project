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
    "kgsl_vbo.c", "adreno_a6xx_hwsched.c", "adreno_a6xx_hwsched_hfi.c",
    "adreno_a6xx_rpmh.c", "adreno_a6xx_coresight.c", "kgsl_bus.c",
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
    pattern = re.compile(
        r"(?m)^[ \t]*(?:(?:static|inline|extern|const|__init|__exit|"
        r"__maybe_unused|__always_inline|noinline)[ \t]+)*"
        r"(?:[A-Za-z_][A-Za-z0-9_]*[ \t\*]+)+"
        r"([A-Za-z_][A-Za-z0-9_]*)[ \t]*\([^;{}]*\)[ \t]*\{"
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
                "structs": sorted(set(re.findall(r"\bstruct\s+(kgsl_[A-Za-z0-9_]+)\b", text))),
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
        })
    return result


def parse_kconfig(text):
    result, current = {}, None
    for line in text.splitlines():
        match = re.match(r"^\s*config\s+([A-Z0-9_]+)", line)
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
    legacy_vs_current, current_vs_modern = [], []
    for path in LEGACY_FILES:
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

    uapi_comparisons = compare_uapi(sources)
    kconfig_text = modern["files"].get("drivers/gpu/msm/Kconfig", {}).get("text") or ""
    modern_kconfig = parse_kconfig(kconfig_text)

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
        "current_vs_modern": current_vs_modern,
        "modern_extras": modern_extras,
        "uapi_comparisons": uapi_comparisons,
        "gki": {
            "repo": gki["repo"], "commit": gki["commit"],
            "files": {p: {"missing": x["missing"], "metrics": x["metrics"]} for p, x in gki["files"].items()},
            "errors": gki["errors"],
            "kgsl_directory_present": gki["kgsl_directory_present"],
            "drm_msm_directory_present": gki["drm_msm_directory_present"],
            "kgsl_uapi_present": gki["kgsl_uapi_present"],
            "drm_uapi_present": gki["drm_uapi_present"],
            "adreno_650_evidence": gki["adreno_650_evidence"],
        },
        "modern_kconfig": modern_kconfig,
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
                  "| Comparison | Left ioctls | Right ioctls | Added | Removed | Changed definitions |",
                  "|---|---:|---:|---:|---:|---:|"])
    for item in uapi_comparisons:
        lines.append("| %s → %s | %s | %s | %s | %s | %s |" % (
            item["left"], item["right"], item["left_ioctl_count"], item["right_ioctl_count"],
            len(item["ioctls_added"]), len(item["ioctls_removed"]), len(item["ioctl_definitions_changed"])))
        if item["ioctls_added"]:
            lines.append("- Added ioctl names: " + ", ".join(item["ioctls_added"]))
        if item["ioctls_removed"]:
            lines.append("- Removed ioctl names: " + ", ".join(item["ioctls_removed"]))
        if item["ioctl_definitions_changed"]:
            lines.append("- Changed definitions: " + ", ".join(item["ioctl_definitions_changed"]))
        lines.append("")
    lines.extend(["## 6. Android 17 GKI 6.18 graphics architecture", "",
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
    lines.extend(["", "## 7. Build and Kconfig evidence", ""])
    lines.extend("- " + item for item in build_evidence)
    for key, item in modern_kconfig.items():
        if key == "QCOM_KGSL":
            lines.append("- QCOM_KGSL Kconfig: depends on %s; selects %s" % (
                ", ".join(item["depends_on"]) or "none", ", ".join(item["selects"]) or "none"))
    lines.extend(["", "## 8. Preliminary migration interpretation", "",
        "1. The pinned Android 17 GKI tree is checked for both the legacy KGSL path and the DRM/MSM Adreno path. A6xx catalog support does not establish KGSL userspace compatibility.",
        "2. The separate Qualcomm KGSL repository is a promising newer KGSL reference, but the Yocto/Linux 7.2 recipe does not prove Android GKI 6.18 KMI compatibility.",
        "3. The next technical gate is to validate module compile dependencies, exported-symbol requirements, GKI KMI availability, device-tree integration and firmware names against the exact Android 17 GKI build.",
        "4. Ioctl-name inventories do not prove ABI compatibility. Struct layout, ioctl encoding, semantics and vendor userspace expectations require dedicated tests.",
        "", "## 9. Limitations", "",
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
