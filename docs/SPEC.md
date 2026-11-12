# code-anatomy — Engineering Specification (`v0.1.0`)

## 1. Problem Statement & Motivation
When onboarding onto an unfamiliar repository or reviewing a large multi-agent PR, flat directory trees and static Mermaid boxes hide **scale, coupling, and architectural gravity**: a 40-line wrapper looks identical to a 900-line state machine with 14 dependents. Existing visualizers either require uploading proprietary source code to SaaS cloud services or installing heavy Node/Graphviz toolchains.

**code-anatomy** is a cross-vendor Agent Skill (`SKILL.md`) paired with a zero-dependency Python 3.10+ static dependency analyzer and **2.5D Isometric HTML5 Canvas compiler** (`scripts/build_anatomy.py`) that compiles any local repository into a single, offline, `<150 KB` interactive `architecture-anatomy.html` map in under two seconds.

---

## 2. Capabilities & Pipeline

### 2.1 Multi-Language Static Dependency & Symbol Extractor
Respects `.gitignore` and excludes build/vendor directories (`.git`, `node_modules`, `dist`, `build`, `.build`, `target`, `.venv`, `__pycache__`, `reports`). Supports:
- **Python (`.py`)**: `ast` module parsing for `import` / `from ... import`, class/function counts, and relative module resolution.
- **Swift (`.swift`)**: Module `import` statements plus **intra-module PascalCase type definition & reference resolution** (since files within a SwiftPM target share a namespace without per-file `import` statements).
- **TypeScript / JavaScript (`.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`)**: ES `import ... from`, dynamic `import()`, and CommonJS `require()` path resolution (`index.*` & extension inference).
- **Go (`.go`), Rust (`.rs`), C/C++ (`.c`, `.h`, `.cpp`, `.hpp`)**: Package/module/header dependency resolution and top-level symbol counts.

### 2.2 Architectural Subsystem Layering & Metrics
For every source file node:
- **`loc`**: Non-blank, non-comment code lines.
- **`symbols`**: Declared classes, structs, enums, protocols, traits, and functions.
- **`fan_out` / `fan_in`**: Outgoing local dependencies and incoming local dependents.
- **`layer`**: Deterministic architectural tier (`entry`, `ui`, `state`, `service`, `model`, `test`) arranged along isometric district lanes so dependencies flow naturally across the canvas.
- **Optional Agent Annotations (`--annotations <json>`)**: Allows an AI coding agent to enrich specific modules and guided-tour stops with plain-language explanations of *why* a subsystem exists and where data flows.

### 2.3 Self-Contained 2.5D Isometric Canvas Output
- Renders at `window.devicePixelRatio` (2x Retina sharp) using pure HTML5 2D Canvas isometric projection (`30°` orthographic axonometric projection) with zero external JS/CSS/font CDNs.
- Extruded 3-face shaded prisms: prism height scales with `LOC`, footprint scales with `fan_in + symbols`, and color encodes architectural layer.
- Interactive controls: click/hover any building to highlight upstream imports (cyan arcs) and downstream dependents (amber arcs), pan & zoom, live module search, layer toggles, and a **Guided Architecture Tour** stepper.

---

## 3. Repository & Skill Layout
```text
code-anatomy/
├── SKILL.md
├── LICENSE
├── README.md
├── docs/
│   ├── SPEC.md
│   └── screenshot.png
├── references/
│   └── schema.md
├── scripts/
│   └── build_anatomy.py
├── evals/
│   └── evals.json
└── tests/
    └── test_anatomy.py
```

## 4. Security & Privacy Invariants
1. **Repo-Relative Paths Only**: Absolute host paths (`/Users/...`, `/home/...`) are never written into `architecture-anatomy.html` or `anatomy.json`.
2. **Metadata-Only Extraction**: Only file paths, structural symbol names, line counts, and dependency edges are embedded—never string literals, `.env` files, or raw source bodies.
3. **Zero Network Calls**: Both the compiler and the generated HTML file operate 100% offline.
