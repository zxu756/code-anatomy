# `code-anatomy` Annotations & Graph JSON Schema

## 1. Optional `--annotations <file.json>` Input Schema

Agents can enrich the static dependency graph with human-readable subsystem explanations and a custom guided onboarding tour:

```json
{
  "subtitle": "Zero-MITM-cert local streaming proxy & 5-bucket token flamegraph",
  "modules": {
    "src/agent_xray/proxy.py": {
      "summary": "Loopback HTTP/1.1 & SSE passthrough server that flushes upstream event chunks immediately while teeing usage telemetry."
    },
    "src/agent_xray/classifier.py": {
      "summary": "Splits Anthropic and OpenAI prompt payloads into 5 token buckets and groups MCP tool schemas by server prefix."
    }
  },
  "tour": [
    {
      "title": "1. CLI Wrapper & Loopback Injection",
      "module": "src/agent_xray/cli.py",
      "body": "Spawns Claude Code, Codex, or OpenCode with ANTHROPIC_BASE_URL and OPENAI_BASE_URL pointed at localhost."
    },
    {
      "title": "2. Streaming Proxy & Secret Firewall",
      "module": "src/agent_xray/proxy.py",
      "body": "Audits headers, blocks accidental live API key leaks locally with HTTP 400, and streams SSE deltas."
    }
  ]
}
```

## 2. `--json-out <graph.json>` Output Schema

```json
{
  "title": "agent-xray",
  "subtitle": "...",
  "stats": {
    "module_count": 7,
    "edge_count": 11,
    "total_loc": 980,
    "languages": { "Python": 7 }
  },
  "nodes": [
    {
      "id": "src/agent_xray/proxy.py",
      "label": "proxy.py",
      "language": "Python",
      "layer": "service",
      "loc": 205,
      "symbols": 5,
      "fan_in": 2,
      "fan_out": 4,
      "gx": 3,
      "gy": 0,
      "summary": "..."
    }
  ],
  "edges": [
    { "from": "src/agent_xray/cli.py", "to": "src/agent_xray/proxy.py" }
  ],
  "tour": [ ... ]
}
```
