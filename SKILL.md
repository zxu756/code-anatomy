---
name: code-anatomy
description: Generate a self-contained, offline interactive 2.5D Isometric HTML5 Canvas architecture map (`architecture-anatomy.html`) and dependency graph from any local codebase (Python, Swift, TypeScript/JavaScript, Rust, Go, C/C++). Make sure to use this skill whenever the user wants to visualize a repository's architecture, onboard onto an unfamiliar codebase, map module dependencies or coupling hotspots, generate an interactive architecture diagram, explain how a project is structured visually, or says "画架构图", "生成代码全景图", "可视化项目结构", "分析模块依赖", "codebase map", "interactive architecture map", or "code anatomy".
---

# Code Anatomy

Compile any local repository into a single, zero-CDN, offline interactive **2.5D Isometric Architecture Map** (`architecture-anatomy.html`) showing subsystem districts, module LOC height, coupling hotspots (`fan-in` / `fan-out`), dependency arcs, and a guided onboarding tour.

## Ground Rules

1. **100% Local & Metadata-Only.** `scripts/build_anatomy.py` runs offline using only the Python 3.10+ standard library. It never uploads code, never reads `.env` files, and emits only repo-relative POSIX paths (never `/Users/...` host paths).
2. **Enrich with Semantic Tour Notes When Helpful.** The static compiler automatically builds a Guided Tour from the entrypoint, core hub, and highest-LOC modules. When the user asks for an explained walkthrough of a repo, inspect the top 4–6 key files first, write a concise `annotations.json` (see `references/schema.md`), and pass `--annotations annotations.json` so the interactive map carries human-friendly architectural commentary.

## Workflow

### Step 1: Run the Static Graph & Isometric Map Compiler

```bash
python3 ~/.agents/skills/code-anatomy/scripts/build_anatomy.py <repo-path> \
  --out <output-html-path> \
  [--json-out <optional-graph.json>] \
  [--annotations <optional-annotations.json>] \
  [--title "Custom Project Title"] \
  [--exclude-tests]
```

Default output if `--out` is omitted: `<repo-path>/docs/architecture-anatomy.html` (or `./architecture-anatomy.html` if `docs/` does not exist).

### Step 2: Optional Agent-Authored Walkthrough (`--annotations`)

When onboarding a user or documenting a complex system:
1. Run `build_anatomy.py <repo-path> --json-out /tmp/anatomy-graph.json` first to see the top `fan_in` hubs, entrypoints, and layer breakdown in `<1s`.
2. Read the 3–5 highest-leverage files identified in the JSON summary.
3. Create an annotations JSON file following `references/schema.md` with custom `summary` blurbs per module and `tour` steps explaining how a request or user action travels across layers.
4. Re-run `build_anatomy.py` with `--annotations` to bake the guided tour directly into the single HTML file.

### Step 3: Present Findings Concisely

After generating `architecture-anatomy.html`:
1. Link directly to the generated `.html` file so the user can open it in any browser offline.
2. Summarize the **3–5 key structural takeaways** surfaced by the graph:
   - Total analyzed modules, LOC, and cross-module dependency edges
   - Core architectural hub (highest `fan-in` module)
   - Largest complexity / LOC concentration and any unexpected cross-layer coupling.
