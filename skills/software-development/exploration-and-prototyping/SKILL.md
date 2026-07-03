---
name: exploration-and-prototyping
description: "Throwaway exploration and prototyping — technical spikes to validate feasibility, and UI sketches to explore design directions. Both follow a decompose → build → evaluate → verdict loop."
tags: [exploration, prototype, spike, sketch, feasibility, design, ui, mockup, proof-of-concept]
---

# Exploration & Prototyping

This umbrella covers two complementary exploration modes — one for technical feasibility (spikes), one for design exploration (sketches). Both follow the same meta-cycle: decompose → build variants → evaluate → verdict.

---

## When to Load This Skill

- User says "spike", "prototype", "is this possible", "compare approaches A vs B"
- User says "sketch", "mockup", "show me what X looks like", "2-3 design variants"
- User wants to explore an idea before committing to a build

---

## 1. Technical Spike (Code / Feasibility)

*(Absorbed from `spike` skill)*

Use this when the user wants to **feel out an idea** before committing to a real build — validating feasibility, comparing approaches, or surfacing unknowns.

### Core Method

```
decompose → research → build → verdict
```

### Decompose

Break the idea into **2-5 independent feasibility questions**. Present as a table:

| # | Spike | Validates (Given/When/Then) | Risk |
|---|-------|----------------------------|------|
| 001 | websocket-streaming | Given a WS connection, when LLM streams tokens, then client receives chunks < 100ms | High |
| 002a | pdf-parse-pdfjs | Given a multi-page PDF, when parsed with pdfjs, then structured text is extractable | Medium |

**Types:** standard (one approach), comparison (same question, different approaches `a`/`b`/`c`).

**Order by risk** — the spike most likely to kill the idea runs first.

### Align

Present the spike table. Ask: "Build all in this order, or adjust?"

### Research (per spike, before building)

1. Brief it (2-3 sentences: what, why, key risk)
2. Surface competing approaches, pick one
3. Skip research for pure logic with no external deps

Use `web_search`, `web_extract`, `terminal(pip show)` for research.

### Build

One directory per spike in `spikes/` or `.planning/spikes/`:

```
spikes/
├── 001-websocket-streaming/
│   ├── README.md
│   └── main.py
└── 002a-pdf-parse-pdfjs/
    ├── README.md
    └── parse.js
```

**Bias toward something the user can interact with.** Default choices:
1. Runnable CLI with observable output
2. Minimal HTML page
3. Small web server with one endpoint
4. Unit test with recognizable assertions

**Depth over speed** — test edge cases, follow surprising findings.

### Verdict

Each spike's README closes with:

```markdown
## Verdict: VALIDATED | PARTIAL | INVALIDATED
### What worked
### What didn't
### Surprises
### Recommendation for the real build
```

**VALIDATED** = core question answered yes, with evidence.
**PARTIAL** = works under constraints X, Y, Z.
**INVALIDATED** = doesn't work (still a successful spike).

### Comparison Spikes

Build back-to-back, then head-to-head table:

| Dimension | Approach A | Approach B |
|-----------|-----------|-----------|

### Frontier Mode

If spikes exist and user asks "what next?", look for:
- Integration risks between validated spikes
- Data handoff gaps
- Unproven assumptions
- Alternative angles for PARTIAL/INVALIDATED spikes

---

## 2. UI Sketch (Design / Mockup)

*(Absorbed from `sketch` skill)*

Use when the user wants to **see a design direction before committing** — 2-3 interactive HTML mockup variants for side-by-side comparison.

### Core Method

```
intake → variants → head-to-head → pick winner (or iterate)
```

### Intake

Get three things (one at a time):
1. **Feel** — "What should this feel like? Adjectives, emotions, a vibe."
2. **References** — "What apps/sites/products capture that feel?"
3. **Core action** — "What's the single most important thing a user does on this screen?"

### Variants (2-3, never 1)

Each variant takes a **different design stance**:

- **Density:** compact / airy / ultra-dense
- **Emphasis:** content-first / action-first / tool-first
- **Layout:** single-column / sidebar / split-pane

Name the stance, not the number:

```
sketches/
├── 001-calm-editorial/index.html + README.md
├── 001-utilitarian-dense/index.html + README.md
└── 001-playful-split/index.html + README.md
```

### Make Them Real HTML

Each variant = single self-contained HTML file:
- Inline `<style>`, no build step
- System fonts or one Google Font
- Tailwind via CDN is fine
- **Realistic fake content** (actual sentences, names, no lorem ipsum)
- **Interactive** — clicks, hovers, at least one state transition

Verify visually with `browser_navigate` + `browser_vision` — fix layout bugs.

### Variant README

```markdown
## Variant: {stance name}
### Design stance
### Key choices
### Trade-offs
### Best for
```

### Head-to-Head

Present as a comparison table with **opinionated** take:

| Dimension | Variant A | Variant B | Variant C |
|-----------|-----------|-----------|-----------|

**My take:** [which wins and why]

### Theming

If the project has an existing identity, create `sketches/themes/tokens.css`:

```css
:root {
  --color-bg: #fafafa;
  --color-fg: #1a1a1a;
  --color-accent: #0066ff;
  --font-display: "Inter", sans-serif;
}
```

### Interactivity Bar

Minimum: (1) click a primary action → visible change, (2) one meaningful state transition, (3) hover recognizable affordances.

### Frontier Mode

If sketches exist and user asks "what next?": consistency gaps, unsketched screens, state coverage, responsive gaps, interaction patterns.

### Output

- `sketches/` (or `.planning/sketches/` for GSD users)
- Keep variants disposable — don't curate, promote to real code if needed
- Tell user how to open: `start sketches/001-*/index.html` on Windows, `open` on macOS, `xdg-open` on Linux
