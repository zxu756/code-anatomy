#!/usr/bin/env python3
"""code-anatomy: Zero-dependency static dependency analyzer & 2.5D Isometric HTML5 Canvas compiler."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "dist",
    "build",
    ".build",
    "target",
    "out",
    ".next",
    ".nuxt",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "DerivedData",
    "reports",
    "vendor",
    "Pods",
}

LANG_BY_EXT = {
    ".py": "Python",
    ".swift": "Swift",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C/C++",
    ".h": "C/C++",
    ".cpp": "C/C++",
    ".hpp": "C/C++",
    ".cc": "C/C++",
}

LAYER_META = [
    ("entry", "Entry & CLI", "#38bdf8", 0),
    ("ui", "Views & UI", "#a78bfa", 1),
    ("state", "State & Controllers", "#34d399", 2),
    ("service", "Core & Services", "#f59e0b", 3),
    ("model", "Models & Store", "#60a5fa", 4),
    ("test", "Verification Suite", "#fb7185", 5),
]
LAYER_ORDER = {key: idx for idx, (key, _, _, _) in enumerate(LAYER_META)}


def load_gitignore_patterns(root: Path) -> list[str]:
    gi = root / ".gitignore"
    if not gi.is_file():
        return []
    patterns: list[str] = []
    for raw in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        patterns.append(line.strip("/"))
    return patterns


def is_ignored(rel_posix: str, patterns: list[str]) -> bool:
    parts = rel_posix.split("/")
    for pat in patterns:
        if fnmatch.fnmatch(rel_posix, pat) or any(fnmatch.fnmatch(p, pat) for p in parts):
            return True
    return False


def classify_layer(rel_posix: str) -> str:
    lower = rel_posix.lower()
    base = Path(lower).stem
    if (
        lower.startswith("tests/")
        or "/tests/" in lower
        or base.startswith("test_")
        or base.endswith("_test")
        or base.endswith("tests")
        or ".spec." in lower
        or ".test." in lower
    ):
        return "test"
    if (
        base in ("main", "cli", "app", "index", "package")
        or base.endswith("app")
        or "/cmd/" in lower
        or lower.startswith("scripts/")
    ):
        return "entry"
    if (
        "/views/" in lower
        or "/components/" in lower
        or "/ui/" in lower
        or "ui_html" in base
        or base.endswith("view")
    ):
        return "ui"
    if (
        "/viewmodels/" in lower
        or "/controllers/" in lower
        or "monitor" in base
        or "proxy" in base
        or "router" in base
    ):
        return "state"
    if (
        "/models/" in lower
        or "model" in base
        or "schema" in base
        or "store" in base
        or "types" in base
    ):
        return "model"
    return "service"


def count_code_lines(text: str, lang: str) -> int:
    comment_prefix = "#" if lang == "Python" else "//"
    count = 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(comment_prefix):
            continue
        count += 1
    return max(1, count)


def extract_python_info(text: str) -> tuple[int, list[tuple[int, str]]]:
    """Returns (symbol_count, list of (relative_level, module_name))."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 0, []
    symbols = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((0, alias.name))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports.append((node.level or 0, mod))
            for alias in node.names:
                if mod:
                    imports.append((node.level or 0, f"{mod}.{alias.name}"))
                else:
                    imports.append((node.level or 0, alias.name))
    return symbols, imports


SWIFT_DECL_RE = re.compile(
    r"^\s*(?:@\w+\s+)*(?:public\s+|internal\s+|private\s+|fileprivate\s+|open\s+|final\s+)*"
    r"(?:struct|class|enum|protocol|actor)\s+([A-Z][A-Za-z0-9_]*)",
    re.MULTILINE,
)
SWIFT_FUNC_RE = re.compile(r"\bfunc\s+[A-Za-z0-9_]+")
SWIFT_IMPORT_RE = re.compile(r"^\s*(?:@testable\s+)?import\s+([A-Za-z0-9_]+)", re.MULTILINE)
JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[^'"]+?\s+from\s+)?|export\s+[^'"]+?\s+from\s+|require\s*\()\s*['"]([^'"]+)['"]"""
)
GO_IMPORT_RE = re.compile(r'"([^"]+)"')
RUST_USE_RE = re.compile(r"\b(?:mod|use)\s+(?:crate::|super::|self::)?([a-zA-Z0-9_]+)")
C_INCLUDE_RE = re.compile(r'#include\s+"([^"]+)"')


def analyze_repository(
    repo_root: Path,
    *,
    exclude_tests: bool = False,
    annotations: dict[str, Any] | None = None,
    custom_title: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    gi_patterns = load_gitignore_patterns(repo_root)

    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [
            d
            for d in sorted(dirnames)
            if d not in SKIP_DIRS and not d.startswith(".")
        ]
        for fn in sorted(filenames):
            ext = Path(fn).suffix.lower()
            if ext not in LANG_BY_EXT:
                continue
            full = Path(dirpath) / fn
            rel = full.relative_to(repo_root).as_posix()
            if is_ignored(rel, gi_patterns):
                continue
            if exclude_tests and classify_layer(rel) == "test":
                continue
            files.append(full)

    file_texts: dict[str, str] = {}
    raw_nodes: dict[str, dict[str, Any]] = {}
    lang_counts: dict[str, int] = {}

    for full in files:
        rel = full.relative_to(repo_root).as_posix()
        lang = LANG_BY_EXT[full.suffix.lower()]
        text = full.read_text(encoding="utf-8", errors="ignore")
        file_texts[rel] = text
        loc = count_code_lines(text, lang)
        layer = classify_layer(rel)
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        raw_nodes[rel] = {
            "id": rel,
            "label": full.name,
            "language": lang,
            "layer": layer,
            "loc": loc,
            "symbols": 0,
            "fan_in": 0,
            "fan_out": 0,
            "summary": "",
        }

    # Build lookup indexes for cross-file resolution
    py_mod_index: dict[str, str] = {}
    for rel, node in raw_nodes.items():
        if node["language"] != "Python":
            continue
        no_ext = rel[:-3]
        parts = no_ext.split("/")
        if parts[0] == "src" and len(parts) > 1:
            parts = parts[1:]
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            py_mod_index[".".join(parts)] = rel

    swift_type_owner: dict[str, str] = {}
    swift_target_files: dict[str, list[str]] = {}
    for rel, node in raw_nodes.items():
        if node["language"] != "Swift":
            continue
        text = file_texts[rel]
        decls = SWIFT_DECL_RE.findall(text)
        funcs = SWIFT_FUNC_RE.findall(text)
        node["symbols"] = len(decls) + len(funcs)
        for tname in decls:
            swift_type_owner.setdefault(tname, rel)
        parts = rel.split("/")
        if len(parts) >= 2 and parts[0] in ("Sources", "Tests"):
            swift_target_files.setdefault(parts[1], []).append(rel)

    edges_set: set[tuple[str, str]] = set()

    for rel, node in raw_nodes.items():
        lang = node["language"]
        text = file_texts[rel]
        cur_dir = Path(rel).parent

        if lang == "Python":
            syms, py_imps = extract_python_info(text)
            node["symbols"] = syms
            # Compute current dotted package
            no_ext = rel[:-3]
            pkg_parts = no_ext.split("/")
            if pkg_parts[0] == "src" and len(pkg_parts) > 1:
                pkg_parts = pkg_parts[1:]
            cur_pkg = pkg_parts[:-1]

            for level, mod in py_imps:
                if level > 0:
                    up = max(0, len(cur_pkg) - (level - 1))
                    base_pkg = cur_pkg[:up]
                    cand = ".".join(base_pkg + ([mod] if mod else []))
                else:
                    cand = mod
                if cand in py_mod_index and py_mod_index[cand] != rel:
                    edges_set.add((rel, py_mod_index[cand]))

        elif lang == "Swift":
            # 1. Intra-repo Swift type references
            tokens = set(re.findall(r"\b([A-Z][A-Za-z0-9_]{2,})\b", text))
            for tok in tokens:
                owner = swift_type_owner.get(tok)
                if owner and owner != rel:
                    edges_set.add((rel, owner))
            # 2. Explicit target imports (e.g. `import LaunchLensCore`) if no type matched yet
            for imp_target in SWIFT_IMPORT_RE.findall(text):
                if imp_target in swift_target_files:
                    has_edge_into_target = any(
                        dst in swift_target_files[imp_target]
                        for (src, dst) in edges_set
                        if src == rel
                    )
                    if not has_edge_into_target and swift_target_files[imp_target]:
                        hub = max(swift_target_files[imp_target], key=lambda r: raw_nodes[r]["symbols"])
                        if hub != rel:
                            edges_set.add((rel, hub))

        elif lang in ("TypeScript", "JavaScript"):
            node["symbols"] = len(
                re.findall(r"\b(?:function|class|interface|type)\s+[A-Za-z0-9_]+", text)
            )
            for spec in JS_IMPORT_RE.findall(text):
                if not spec.startswith("."):
                    continue
                base_cand = (repo_root / cur_dir / spec).resolve()
                try:
                    rel_base = base_cand.relative_to(repo_root).as_posix()
                except ValueError:
                    continue
                for suffix in ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", "/index.ts", "/index.tsx", "/index.js"):
                    cand = f"{rel_base}{suffix}"
                    if cand in raw_nodes and cand != rel:
                        edges_set.add((rel, cand))
                        break

        elif lang == "Rust":
            node["symbols"] = len(re.findall(r"\b(?:fn|struct|enum|trait)\s+[A-Za-z0-9_]+", text))
            for mod_name in RUST_USE_RE.findall(text):
                for cand in (f"src/{mod_name}.rs", f"src/{mod_name}/mod.rs", f"{cur_dir.as_posix()}/{mod_name}.rs"):
                    if cand in raw_nodes and cand != rel:
                        edges_set.add((rel, cand))

        elif lang == "Go":
            node["symbols"] = len(re.findall(r"\b(?:func|type)\s+[A-Za-z0-9_]+", text))
            for imp in GO_IMPORT_RE.findall(text):
                tail = imp.split("/")[-1]
                for other in raw_nodes:
                    if Path(other).parent.name == tail and other != rel:
                        edges_set.add((rel, other))

        elif lang == "C/C++":
            node["symbols"] = len(re.findall(r"\b(?:class|struct|void|int|bool)\s+[A-Za-z0-9_]+\s*\(", text))
            for inc in C_INCLUDE_RE.findall(text):
                inc_name = Path(inc).name
                for other in raw_nodes:
                    if Path(other).name == inc_name and other != rel:
                        edges_set.add((rel, other))

    for src, dst in edges_set:
        raw_nodes[src]["fan_out"] += 1
        raw_nodes[dst]["fan_in"] += 1

    # Merge optional annotations & synthesize smart fallback descriptions
    ann = annotations or {}
    ann_modules = ann.get("modules") if isinstance(ann.get("modules"), dict) else {}

    for rel, node in raw_nodes.items():
        custom = ann_modules.get(rel)
        if isinstance(custom, dict) and custom.get("summary"):
            node["summary"] = str(custom["summary"])
        else:
            node["summary"] = (
                f"{node['language']} {node['layer']} module ({node['loc']} LOC, "
                f"{node['symbols']} symbols) — imported by {node['fan_in']} module(s), "
                f"depends on {node['fan_out']} local module(s)."
            )

    # Assign 2.5D Isometric Grid Coordinates (gx = layer column * 2, gy = rank within layer)
    present_layers = [key for (key, _, _, _) in LAYER_META if any(n["layer"] == key for n in raw_nodes.values())]
    layer_col_map = {key: idx for idx, key in enumerate(present_layers)}

    nodes_list: list[dict[str, Any]] = []
    for key in present_layers:
        col_nodes = [n for n in raw_nodes.values() if n["layer"] == key]
        col_nodes.sort(key=lambda n: (-n["fan_in"], -n["loc"], n["id"]))
        col_idx = layer_col_map[key]
        for row_idx, n in enumerate(col_nodes):
            n["gx"] = col_idx * 2.15
            n["gy"] = row_idx * 1.65
            nodes_list.append(n)

    edges_list = [
        {"from": src, "to": dst}
        for (src, dst) in sorted(edges_set)
    ]

    # Build Guided Tour (custom or automatic architectural highlights)
    custom_tour = ann.get("tour") if isinstance(ann.get("tour"), list) else None
    if custom_tour:
        tour = [t for t in custom_tour if isinstance(t, dict) and t.get("module") in raw_nodes]
    else:
        tour = _build_auto_tour(nodes_list)

    title = custom_title or ann.get("title") or repo_root.name
    subtitle = str(
        ann.get("subtitle")
        or f"{len(nodes_list)} modules, {sum(n['loc'] for n in nodes_list):,} LOC, {len(edges_list)} dependency edges"
    )

    return {
        "title": title,
        "subtitle": subtitle,
        "layers": [
            {"id": k, "name": label, "color": color, "gx": layer_col_map[k] * 2.15}
            for (k, label, color, _) in LAYER_META
            if k in layer_col_map
        ],
        "stats": {
            "module_count": len(nodes_list),
            "edge_count": len(edges_list),
            "total_loc": sum(n["loc"] for n in nodes_list),
            "languages": lang_counts,
        },
        "nodes": nodes_list,
        "edges": edges_list,
        "tour": tour,
    }


def _build_auto_tour(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not nodes:
        return []
    tour: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_stop(prefix: str, candidate: dict[str, Any], reason: str) -> None:
        if candidate["id"] in seen:
            return
        seen.add(candidate["id"])
        tour.append(
            {
                "title": f"{len(tour) + 1}. {prefix}: {candidate['label']}",
                "module": candidate["id"],
                "body": reason,
            }
        )

    entries = [n for n in nodes if n["layer"] == "entry" and n["label"] != "Package.swift"]
    if entries:
        top_entry = max(entries, key=lambda n: (n["fan_out"], n["loc"]))
        add_stop(
            "Entrypoint",
            top_entry,
            f"Primary execution entrypoint ({top_entry['loc']} LOC) wiring {top_entry['fan_out']} downstream subsystem(s).",
        )

    non_test = [n for n in nodes if n["layer"] != "test"] or nodes
    hub = max(non_test, key=lambda n: (n["fan_in"], n["loc"]))
    add_stop(
        "Core Architectural Hub",
        hub,
        f"Highest-gravity shared module in the codebase (depended on by {hub['fan_in']} modules, {hub['symbols']} symbols).",
    )

    heaviest = max(non_test, key=lambda n: (n["loc"], n["fan_out"]))
    add_stop(
        "Primary Implementation Engine",
        heaviest,
        f"Largest concentration of logic ({heaviest['loc']} LOC, {heaviest['symbols']} symbols) driving {heaviest['fan_out']} collaborator(s).",
    )

    ui_or_state = [n for n in non_test if n["layer"] in ("ui", "state") and n["id"] not in seen]
    if ui_or_state:
        pick = max(ui_or_state, key=lambda n: n["loc"])
        add_stop(
            "State & Presentation Surface",
            pick,
            f"Coordinates interactive presentation and state flow ({pick['loc']} LOC).",
        )

    return tour


def render_anatomy_html(graph: dict[str, Any]) -> str:
    data_json = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    title_esc = (
        str(graph.get("title") or "Repository")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title_esc} — Code Anatomy 2.5D Architecture Map</title>
<style>
  :root {{
    --bg: #080f1a;
    --hud: rgba(13, 22, 36, 0.92);
    --hud-solid: #0d1624;
    --border: #1e3048;
    --ink: #eef5fc;
    --muted: #889eb8;
    --cyan: #38bdf8;
    --amber: #fbbf24;
    --emerald: #34d399;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: var(--bg);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", system-ui, sans-serif;
    font-size: 12.5px;
    font-variant-numeric: tabular-nums;
    user-select: none;
  }}
  .mono {{ font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; }}
  canvas {{
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    cursor: grab;
  }}
  canvas:active {{ cursor: grabbing; }}
  .topbar {{
    position: fixed;
    top: 14px;
    left: 16px;
    right: 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 11px 16px;
    background: var(--hud);
    border: 1px solid var(--border);
    border-radius: 10px;
    backdrop-filter: blur(10px);
    z-index: 10;
  }}
  .brand {{
    display: flex;
    align-items: center;
    gap: 11px;
  }}
  .cube-badge {{
    width: 28px;
    height: 28px;
    border-radius: 7px;
    background: rgba(56, 189, 248, 0.16);
    border: 1px solid rgba(56, 189, 248, 0.48);
    display: grid;
    place-items: center;
    color: var(--cyan);
    font-weight: 700;
    font-size: 12px;
  }}
  .brand h1 {{ font-size: 15px; font-weight: 600; }}
  .brand p {{ font-size: 11.5px; color: var(--muted); }}
  .controls {{
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .search {{
    background: #08111d;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--ink);
    padding: 6px 10px;
    font-size: 12px;
    width: 200px;
    outline: none;
  }}
  .btn {{
    background: #132033;
    border: 1px solid var(--border);
    color: var(--ink);
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 11.5px;
    font-weight: 500;
    cursor: pointer;
  }}
  .btn:hover {{ border-color: rgba(56, 189, 248, 0.55); }}
  .left-dock {{
    position: fixed;
    top: 78px;
    left: 16px;
    width: 276px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    z-index: 10;
  }}
  .card {{
    background: var(--hud);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 13px 14px;
    backdrop-filter: blur(10px);
  }}
  .card h2 {{
    font-size: 12px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 8px;
  }}
  .tour-body {{
    font-size: 12px;
    color: var(--muted);
    line-height: 1.48;
    margin-bottom: 10px;
  }}
  .tour-nav {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 6px;
  }}
  .layer-list {{
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .layer-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 11.5px;
    color: var(--muted);
  }}
  .dot {{
    width: 9px;
    height: 9px;
    border-radius: 2px;
    display: inline-block;
    margin-right: 7px;
  }}
  .right-dock {{
    position: fixed;
    top: 78px;
    right: 16px;
    width: 310px;
    z-index: 10;
  }}
  .kv-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 10px 0;
  }}
  .kv {{
    background: rgba(8, 17, 29, 0.72);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 7px 9px;
  }}
  .kv .v {{ font-size: 14px; font-weight: 600; color: var(--ink); }}
  .kv .k {{ font-size: 10.5px; color: var(--muted); }}
  .dep-section {{
    margin-top: 9px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }}
  .dep-title {{
    font-size: 11px;
    font-weight: 600;
    margin-bottom: 5px;
  }}
  .dep-chip {{
    display: inline-block;
    margin: 2px 4px 2px 0;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 11px;
    cursor: pointer;
    background: rgba(56, 189, 248, 0.13);
    color: var(--cyan);
  }}
  .dep-chip.in {{
    background: rgba(251, 191, 36, 0.14);
    color: var(--amber);
  }}
</style>
</head>
<body>
<canvas id="iso-canvas"></canvas>

<div class="topbar">
  <div class="brand">
    <div class="cube-badge mono">2.5D</div>
    <div>
      <h1 id="proj-title"></h1>
      <p id="proj-sub"></p>
    </div>
  </div>
  <div class="controls">
    <input class="search" id="search-box" type="text" placeholder="Filter module path..." />
    <button class="btn" onclick="resetCamera()">Reset view</button>
  </div>
</div>

<div class="left-dock">
  <div class="card" id="tour-card">
    <h2 id="tour-title">Guided architecture tour</h2>
    <div class="tour-body" id="tour-text"></div>
    <div class="tour-nav">
      <button class="btn" onclick="stepTour(-1)">Prev</button>
      <span class="mono" style="font-size:11px;color:var(--muted)" id="tour-counter"></span>
      <button class="btn" onclick="stepTour(1)">Next stop</button>
    </div>
  </div>

  <div class="card">
    <h2>Architectural districts &amp; arcs</h2>
    <div class="layer-list" id="layer-legend"></div>
    <div style="margin-top:9px;padding-top:8px;border-top:1px solid var(--border);font-size:11px;color:var(--muted);line-height:1.5">
      <div><span class="dot" style="background:var(--cyan)"></span>Cyan arc: imports downstream module</div>
      <div><span class="dot" style="background:var(--amber)"></span>Amber arc: depended on by caller</div>
      <div style="margin-top:3px">Prism height = LOC, footprint = coupling</div>
    </div>
  </div>
</div>

<div class="right-dock">
  <div class="card" id="inspector-card"></div>
</div>

<script>
const GRAPH = {data_json};
const canvas = document.getElementById("iso-canvas");
const ctx = canvas.getContext("2d");

const layerColor = Object.fromEntries((GRAPH.layers || []).map(l => [l.id, l.color]));
const nodeById = Object.fromEntries((GRAPH.nodes || []).map(n => [n.id, n]));

let camX = -14;
let camY = 38;
let zoom = 0.86;
let selectedId = (GRAPH.tour && GRAPH.tour[0] && GRAPH.tour[0].module) || (GRAPH.nodes[0] && GRAPH.nodes[0].id) || null;
let hoveredId = null;
let tourIdx = 0;
let searchTerm = "";
let hitBoxes = [];

document.getElementById("proj-title").textContent = `${{GRAPH.title}} — Code Anatomy`;
document.getElementById("proj-sub").textContent = GRAPH.subtitle || "";

document.getElementById("layer-legend").innerHTML = (GRAPH.layers || []).map(l => {{
  const cnt = GRAPH.nodes.filter(n => n.layer === l.id).length;
  return `<div class="layer-row"><span><i class="dot" style="background:${{l.color}}"></i>${{l.name}}</span><span class="mono">${{cnt}}</span></div>`;
}}).join("");

document.getElementById("search-box").addEventListener("input", e => {{
  searchTerm = e.target.value.trim().toLowerCase();
  const match = searchTerm && GRAPH.nodes.find(n => n.id.toLowerCase().includes(searchTerm));
  if (match) selectedId = match.id;
  updateHUD();
  draw();
}});

function shadeHex(hex, pct) {{
  const n = parseInt(hex.replace("#", ""), 16);
  const r = Math.min(255, Math.max(0, ((n >> 16) & 255) + pct));
  const g = Math.min(255, Math.max(0, ((n >> 8) & 255) + pct));
  const b = Math.min(255, Math.max(0, (n & 255) + pct));
  return `rgb(${{r}},${{g}},${{b}})`;
}}

function projectIso(gx, gy, z, cx, cy) {{
  const tileW = 48 * zoom;
  const tileH = 25 * zoom;
  return {{
    x: cx + (gx - gy) * tileW,
    y: cy + (gx + gy) * tileH - z * zoom
  }};
}}

function computeCenterOffset(w, h) {{
  if (!GRAPH.nodes.length) return {{ cx: w / 2, cy: h / 2 }};
  const gxs = GRAPH.nodes.map(n => n.gx);
  const gys = GRAPH.nodes.map(n => n.gy);
  const midGX = (Math.min(...gxs) + Math.max(...gxs)) / 2;
  const midGY = (Math.min(...gys) + Math.max(...gys)) / 2;
  const tileW = 48 * zoom;
  const tileH = 25 * zoom;
  return {{
    cx: w * 0.50 - (midGX - midGY) * tileW + camX,
    cy: h * 0.53 - (midGX + midGY) * tileH + camY
  }};
}}

function prismMetrics(n) {{
  const h = Math.min(148, 22 + Math.sqrt(Math.max(1, n.loc)) * 4.8);
  const half = Math.min(0.58, 0.34 + Math.min(8, n.fan_in + n.fan_out) * 0.025);
  return {{ h, half }};
}}

function draw() {{
  const dpr = window.devicePixelRatio || 1;
  const w = window.innerWidth;
  const h = window.innerHeight;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {{
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }}
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  // Blueprint midnight backdrop
  const grad = ctx.createRadialGradient(w * 0.5, h * 0.45, 40, w * 0.5, h * 0.5, Math.max(w, h) * 0.75);
  grad.addColorStop(0, "#0d1a2d");
  grad.addColorStop(1, "#070d17");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  const {{ cx, cy }} = computeCenterOffset(w, h);

  // Subtle isometric drafting grid
  ctx.strokeStyle = "rgba(96, 165, 250, 0.055)";
  ctx.lineWidth = 1;
  for (let i = -6; i <= 18; i++) {{
    const a = projectIso(i, -4, 0, cx, cy);
    const b = projectIso(i, 14, 0, cx, cy);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    const c = projectIso(-4, i, 0, cx, cy);
    const d = projectIso(16, i, 0, cx, cy);
    ctx.beginPath(); ctx.moveTo(c.x, c.y); ctx.lineTo(d.x, d.y); ctx.stroke();
  }}

  // District lane pads & labels
  for (const layer of (GRAPH.layers || [])) {{
    const colNodes = GRAPH.nodes.filter(n => n.layer === layer.id);
    if (!colNodes.length) continue;
    const maxGY = Math.max(...colNodes.map(n => n.gy)) + 0.85;
    const p0 = projectIso(layer.gx - 0.85, -0.85, 0, cx, cy);
    const p1 = projectIso(layer.gx + 0.85, -0.85, 0, cx, cy);
    const p2 = projectIso(layer.gx + 0.85, maxGY, 0, cx, cy);
    const p3 = projectIso(layer.gx - 0.85, maxGY, 0, cx, cy);

    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y); ctx.lineTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y); ctx.lineTo(p3.x, p3.y);
    ctx.closePath();
    ctx.fillStyle = "rgba(19, 32, 52, 0.50)";
    ctx.fill();
    ctx.strokeStyle = layer.color + "44";
    ctx.lineWidth = 1;
    ctx.stroke();

    const lblPt = projectIso(layer.gx, maxGY + 0.58, 0, cx, cy);
    ctx.font = `600 ${{Math.max(10, 11 * zoom)}}px -apple-system, BlinkMacSystemFont, sans-serif`;
    ctx.fillStyle = layer.color;
    ctx.textAlign = "center";
    ctx.fillText(layer.name, lblPt.x, lblPt.y);
  }}

  const activeFocus = hoveredId || selectedId;
  const outPeers = new Set();
  const inPeers = new Set();
  for (const e of GRAPH.edges) {{
    if (e.from === activeFocus) outPeers.add(e.to);
    if (e.to === activeFocus) inPeers.add(e.from);
  }}

  // Painter's sort back-to-front by (gx + gy)
  const sorted = [...GRAPH.nodes].sort((a, b) => (a.gx + a.gy) - (b.gx + b.gy));
  hitBoxes = [];
  const roofAnchors = {{}};

  for (const n of sorted) {{
    const {{ h: bh, half }} = prismMetrics(n);
    const baseCol = layerColor[n.layer] || "#38bdf8";
    const isFocused = n.id === activeFocus;
    const isPeer = outPeers.has(n.id) || inPeers.has(n.id);
    const matchesSearch = !searchTerm || n.id.toLowerCase().includes(searchTerm);
    const alpha = (!matchesSearch || (activeFocus && !isFocused && !isPeer)) ? 0.34 : 1.0;

    const t0 = projectIso(n.gx - half, n.gy - half, bh, cx, cy);
    const t1 = projectIso(n.gx + half, n.gy - half, bh, cx, cy);
    const t2 = projectIso(n.gx + half, n.gy + half, bh, cx, cy);
    const t3 = projectIso(n.gx - half, n.gy + half, bh, cx, cy);

    const b1 = projectIso(n.gx + half, n.gy - half, 0, cx, cy);
    const b2 = projectIso(n.gx + half, n.gy + half, 0, cx, cy);
    const b3 = projectIso(n.gx - half, n.gy + half, 0, cx, cy);

    roofAnchors[n.id] = projectIso(n.gx, n.gy, bh, cx, cy);

    ctx.save();
    ctx.globalAlpha = alpha;

    // Base glow for focused prism
    if (isFocused) {{
      ctx.beginPath();
      const g0 = projectIso(n.gx - half * 1.35, n.gy - half * 1.35, 0, cx, cy);
      const g1 = projectIso(n.gx + half * 1.35, n.gy - half * 1.35, 0, cx, cy);
      const g2 = projectIso(n.gx + half * 1.35, n.gy + half * 1.35, 0, cx, cy);
      const g3 = projectIso(n.gx - half * 1.35, n.gy + half * 1.35, 0, cx, cy);
      ctx.moveTo(g0.x, g0.y); ctx.lineTo(g1.x, g1.y); ctx.lineTo(g2.x, g2.y); ctx.lineTo(g3.x, g3.y);
      ctx.closePath();
      ctx.fillStyle = "rgba(56, 189, 248, 0.25)";
      ctx.fill();
    }}

    // Left face (t3 -> t2 -> b2 -> b3)
    ctx.beginPath();
    ctx.moveTo(t3.x, t3.y); ctx.lineTo(t2.x, t2.y);
    ctx.lineTo(b2.x, b2.y); ctx.lineTo(b3.x, b3.y);
    ctx.closePath();
    ctx.fillStyle = shadeHex(baseCol, -36);
    ctx.fill();

    // Right face (t2 -> t1 -> b1 -> b2)
    ctx.beginPath();
    ctx.moveTo(t2.x, t2.y); ctx.lineTo(t1.x, t1.y);
    ctx.lineTo(b1.x, b1.y); ctx.lineTo(b2.x, b2.y);
    ctx.closePath();
    ctx.fillStyle = shadeHex(baseCol, -68);
    ctx.fill();

    // Top roof face
    ctx.beginPath();
    ctx.moveTo(t0.x, t0.y); ctx.lineTo(t1.x, t1.y);
    ctx.lineTo(t2.x, t2.y); ctx.lineTo(t3.x, t3.y);
    ctx.closePath();
    ctx.fillStyle = isFocused ? "#eef6ff" : shadeHex(baseCol, 18);
    ctx.fill();
    ctx.strokeStyle = isFocused ? "#38bdf8" : "rgba(255,255,255,0.28)";
    ctx.lineWidth = isFocused ? 2 : 1;
    ctx.stroke();

    ctx.restore();

    const minX = Math.min(t3.x, t0.x);
    const maxX = Math.max(t1.x, b1.x);
    const minY = t0.y;
    const maxY = b2.y;
    hitBoxes.push({{ id: n.id, minX, maxX, minY, maxY }});
  }}

  // Overhead Bezier dependency arcs
  for (const e of GRAPH.edges) {{
    const a = roofAnchors[e.from];
    const b = roofAnchors[e.to];
    if (!a || !b) continue;
    const isOut = e.from === activeFocus;
    const isIn = e.to === activeFocus;
    if (activeFocus && !isOut && !isIn) {{
      ctx.strokeStyle = "rgba(136, 158, 184, 0.13)";
      ctx.lineWidth = 1;
    }} else if (isOut) {{
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 2.2;
    }} else {{
      ctx.strokeStyle = "#fbbf24";
      ctx.lineWidth = 2.2;
    }}
    const dist = Math.hypot(b.x - a.x, b.y - a.y);
    const ctrlX = (a.x + b.x) / 2;
    const ctrlY = Math.min(a.y, b.y) - Math.max(36, dist * 0.24);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.quadraticCurveTo(ctrlX, ctrlY, b.x, b.y);
    ctx.stroke();

    if (isOut || isIn) {{
      ctx.beginPath();
      ctx.arc(b.x, b.y, 3.2, 0, Math.PI * 2);
      ctx.fillStyle = isOut ? "#38bdf8" : "#fbbf24";
      ctx.fill();
    }}
  }}

  // Clean rooftop callout badges for focused + peer + top hub modules
  for (const n of sorted) {{
    const isFocused = n.id === activeFocus;
    const isPeer = outPeers.has(n.id) || inPeers.has(n.id);
    if (!isFocused && !isPeer && GRAPH.nodes.length > 10) continue;
    const pt = roofAnchors[n.id];
    if (!pt) continue;
    const text = n.label;
    ctx.font = `${{isFocused ? "600" : "500"}} 11px "SF Mono", ui-monospace, monospace`;
    const tw = ctx.measureText(text).width + 12;
    const bx = pt.x - tw / 2;
    const by = pt.y - 24;

    ctx.fillStyle = isFocused ? "rgba(14, 26, 44, 0.96)" : "rgba(10, 18, 30, 0.84)";
    ctx.strokeStyle = isFocused ? "#38bdf8" : "rgba(136, 158, 184, 0.38)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(bx, by, tw, 18, 4);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = isFocused ? "#ffffff" : "#dbe7f5";
    ctx.textAlign = "center";
    ctx.fillText(text, pt.x, by + 12.5);
  }}
}}

function updateHUD() {{
  const tour = GRAPH.tour || [];
  if (tour.length) {{
    const stop = tour[tourIdx % tour.length];
    document.getElementById("tour-title").textContent = stop.title;
    document.getElementById("tour-text").textContent = stop.body;
    document.getElementById("tour-counter").textContent = `${{(tourIdx % tour.length) + 1}} / ${{tour.length}}`;
  }} else {{
    document.getElementById("tour-card").style.display = "none";
  }}

  const cur = nodeById[selectedId] || GRAPH.nodes[0];
  const card = document.getElementById("inspector-card");
  if (!cur) {{
    card.innerHTML = `<h2>No modules found</h2>`;
    return;
  }}
  const outs = GRAPH.edges.filter(e => e.from === cur.id).map(e => e.to);
  const ins = GRAPH.edges.filter(e => e.to === cur.id).map(e => e.from);

  const outHtml = outs.length
    ? outs.map(id => `<span class="dep-chip mono" onclick="focusModule('${{escapeJs(id)}}')">${{escapeHtml(nodeById[id]?.label || id)}}</span>`).join("")
    : `<span style="color:var(--muted);font-size:11px">None (leaf module)</span>`;
  const inHtml = ins.length
    ? ins.map(id => `<span class="dep-chip in mono" onclick="focusModule('${{escapeJs(id)}}')">${{escapeHtml(nodeById[id]?.label || id)}}</span>`).join("")
    : `<span style="color:var(--muted);font-size:11px">None (top-level entrypoint)</span>`;

  card.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px">
      <h2 style="margin:0;font-size:13.5px">${{escapeHtml(cur.label)}}</h2>
      <span class="mono" style="font-size:11px;color:${{layerColor[cur.layer] || '#38bdf8'}}">${{escapeHtml(cur.layer)}}</span>
    </div>
    <div class="mono" style="font-size:10.5px;color:var(--muted);margin:3px 0 8px;word-break:break-all">${{escapeHtml(cur.id)}}</div>
    <div style="font-size:12px;color:#cbd8e8;line-height:1.45">${{escapeHtml(cur.summary)}}</div>
    <div class="kv-grid">
      <div class="kv"><div class="v mono">${{cur.loc}}</div><div class="k">Code lines (LOC)</div></div>
      <div class="kv"><div class="v mono">${{cur.symbols}}</div><div class="k">Declared symbols</div></div>
      <div class="kv"><div class="v mono" style="color:var(--amber)">${{cur.fan_in}}</div><div class="k">Dependents (fan-in)</div></div>
      <div class="kv"><div class="v mono" style="color:var(--cyan)">${{cur.fan_out}}</div><div class="k">Imports (fan-out)</div></div>
    </div>
    <div class="dep-section">
      <div class="dep-title" style="color:var(--cyan)">Imports (${{outs.length}})</div>
      <div>${{outHtml}}</div>
    </div>
    <div class="dep-section">
      <div class="dep-title" style="color:var(--amber)">Depended on by (${{ins.length}})</div>
      <div>${{inHtml}}</div>
    </div>
  `;
}}

function focusModule(id) {{
  selectedId = id;
  updateHUD();
  draw();
}}

function stepTour(delta) {{
  const tour = GRAPH.tour || [];
  if (!tour.length) return;
  tourIdx = (tourIdx + delta + tour.length) % tour.length;
  selectedId = tour[tourIdx].module;
  updateHUD();
  draw();
}}

function resetCamera() {{
  camX = -14;
  camY = 38;
  zoom = 0.86;
  draw();
}}

function hitTest(x, y) {{
  for (let i = hitBoxes.length - 1; i >= 0; i--) {{
    const b = hitBoxes[i];
    if (x >= b.minX && x <= b.maxX && y >= b.minY && y <= b.maxY) return b.id;
  }}
  return null;
}}

let dragging = false;
let dragStartX = 0, dragStartY = 0, moved = false;

canvas.addEventListener("mousedown", e => {{
  dragging = true;
  moved = false;
  dragStartX = e.clientX - camX;
  dragStartY = e.clientY - camY;
}});

window.addEventListener("mousemove", e => {{
  if (dragging) {{
    camX = e.clientX - dragStartX;
    camY = e.clientY - dragStartY;
    moved = true;
    draw();
    return;
  }}
  const hit = hitTest(e.clientX, e.clientY);
  if (hit !== hoveredId) {{
    hoveredId = hit;
    canvas.style.cursor = hit ? "pointer" : "grab";
    draw();
  }}
}});

window.addEventListener("mouseup", e => {{
  if (dragging && !moved) {{
    const hit = hitTest(e.clientX, e.clientY);
    if (hit) {{
      selectedId = hit;
      updateHUD();
      draw();
    }}
  }}
  dragging = false;
}});

canvas.addEventListener("wheel", e => {{
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.08 : 0.92;
  zoom = Math.min(2.2, Math.max(0.55, zoom * factor));
  draw();
}}, {{ passive: false }});

window.addEventListener("resize", draw);

function escapeHtml(s) {{
  return String(s || "").replace(/[&<>"']/g, c => ({{
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }}[c]));
}}
function escapeJs(s) {{
  return String(s || "").replace(/\\\\/g, "\\\\\\\\").replace(/'/g, "\\\\'");
}}

updateHUD();
draw();
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_anatomy.py",
        description="Compile a local repository into an interactive 2.5D Isometric HTML5 Canvas architecture map.",
    )
    parser.add_argument("repo", type=str, help="Path to target repository root")
    parser.add_argument("--out", type=str, default=None, help="Output HTML file path")
    parser.add_argument("--json-out", type=str, default=None, help="Optional output graph JSON path")
    parser.add_argument("--annotations", type=str, default=None, help="Optional annotations JSON path")
    parser.add_argument("--title", type=str, default=None, help="Custom project title")
    parser.add_argument("--exclude-tests", action="store_true", help="Exclude test files from graph")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo).resolve()
    if not repo_root.is_dir():
        raise SystemExit(f"Error: repository directory not found: {repo_root}")

    annotations: dict[str, Any] | None = None
    if args.annotations:
        annotations = json.loads(Path(args.annotations).read_text(encoding="utf-8"))

    graph = analyze_repository(
        repo_root,
        exclude_tests=args.exclude_tests,
        annotations=annotations,
        custom_title=args.title,
    )

    if args.json_out:
        jp = Path(args.json_out)
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")

    out_path = (
        Path(args.out)
        if args.out
        else (repo_root / "docs" / "architecture-anatomy.html" if (repo_root / "docs").is_dir() else repo_root / "architecture-anatomy.html")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_anatomy_html(graph)
    out_path.write_text(html, encoding="utf-8")

    stats = graph["stats"]
    print(
        f"[code-anatomy] Wrote {out_path} ({len(html) / 1024:.1f} KB) — "
        f"{stats['module_count']} modules, {stats['total_loc']:,} LOC, {stats['edge_count']} edges"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
