# Autonomous Paint Lab

A small Python/PyGame experiment in which an agent makes reproducible artwork
through a custom Paint-like interface.

The project keeps the canvas model separate from PyGame rendering and provides
seven progressively stricter stages:

1. Human-operated Paint application.
2. Structured-state control for verifying drawing primitives.
3. Deterministic screenshot-only control through visible clicks and drags.
4. Coarse-to-fine composition, construction, form, material, lighting, texture,
   and focal-finish passes with a visible detail ledger.
5. Visual checkpoints with bounded corrections immediately after each review.
6. GIF/MP4 recording with concise, visible decision summaries and quality gates.
7. Two-stage blind tournaments that qualify thumbnails, refine finalists, and
   compare them with a detail-sensitive visible rubric.

The screenshot interface never returns canvas state. Its agent input is the
complete application PNG, and its only drawing outputs are visible UI actions.

Reviews are region-specific: numbered boxes identify what needs work, while the
side panel and `review_report.md` explain the issue, visible evidence, priority,
confidence, and proposed correction in ordinary language. The report then names
the finding that triggered revision, links the visible action, records deferred
ideas, and checks whether changed pixels stayed inside the intended region.

Web or local research images can be prepared as an attributed reference board.
The agent opens that board through the visible **REFS** control, so references
remain inside the complete-application screenshot boundary.

## Quick start

```bash
python -m pip install -r requirements.txt
python scripts/run_paint.py
python scripts/run_structured.py --prompt "a lighthouse during a storm using four colours" --seed 23
python scripts/run_screenshot_agent.py --prompt "a cheerful robot tending square flowers" --seed 41
python scripts/screenshot_cli.py --help
```

## Detail profiles and purposeful action budgets

Every autonomous runner accepts a floor, planning target, and hard ceiling:

- `--min-actions` prevents a nominally detailed run from stopping as a sketch.
- `--target-actions` is allocated across named coarse-to-fine passes.
- `--max-actions` (also `--actions` or `--action-budget`) remains a hard cap.
- `--detail-level` selects `draft`, `standard`, `high`, or `ultra` gates.
- `--revisions` (or `--review-budget`) sets the number of visual review
  checkpoints.
- `--revision-actions` caps visible drawing corrections distributed after
  checkpoints.

For example, this high-detail guinea-pig tournament requires at least 80
purposeful marks, plans for 140, never exceeds 200, and reserves 24 checkpoint
corrections:

```bash
python scripts/run_tournament.py \
  --prompt "A cute guinea pig resting in a 'cuddle cup'" \
  --seed 57 --candidates 3 \
  --detail-level high \
  --min-actions 80 --target-actions 140 --max-actions 200 \
  --revisions 5 --revision-actions 24 --finalists 2 \
  --references runs/guinea-pig-references/references.json \
  --run-dir runs/guinea-pig-tournament
```

The standard profile plans 70 actions inside a 100-action ceiling. The high
profile defaults to 80/140/200 and requires two attributed references; ultra
uses 140/220/320 and three. Save is blocked until the minimum, configured
reviews, required passes, reference rule, and high-priority correction checks
all pass. `quality_gates.json` records every check.

Prepare an attributed reference:

```bash
python scripts/prepare_references.py \
  --run-dir runs/model-robot \
  --title "Friendly robot gardener" \
  --source-url "https://example.com/source-page" \
  --image-url "https://example.com/reference.jpg" \
  --search-query "friendly robot gardening simple shapes" \
  --note "Use the broad silhouette and gardening pose; invent new colours and details."

python scripts/run_screenshot_agent.py \
  --run-dir runs/model-robot \
  --references runs/model-robot/references.json
```

Generated runs contain the prompt, metadata, action log, complete-application
screenshots, numbered recording frames, final canvas PNG, GIF, MP4, attributed
references, a human-readable visual review report, and the quality-gate report.

Run a three-candidate tournament:

```bash
python scripts/run_tournament.py \
  --prompt "a cheerful robot tending square flowers" \
  --seed 57 --candidates 3 \
  --run-dir runs/robot-tournament
```

Each candidate receives an explicit diversity contract covering pose,
composition, lighting, and rendering. A draft qualification round spends
25–40-ish actions on every concept; only the selected finalists are reproduced
at the full detail target. The judge sees only final complete-application
screenshots, brief, and visible rubric—not seeds, canvas state, logs, or review
reports. The rubric weights prompt fidelity and representation accuracy at 20%
each; composition, depth/lighting, and material rendering at 15% each; fine
detail at 10%; and originality at 5%. The run preserves every qualifier and
finalist and produces `tournament.json`, `tournament_report.md`,
`tournament_montage.png`, `winner.png`, and `winner_full_app.png`.

## Paint v2 controls

The visible application now includes adjustable 1–64 px strokes, outlined,
filled, and combined shape modes, eyedropper sampling, custom/recent colour
state, an expanded natural palette, a cursor-coordinate magnifier, and a visible
layer stack. The canvas model also supports named layers, polygons, quadratic
Bézier curves, gradients, and smudging while preserving undo and serialization.

Example outputs:

- [Lighthouse, seed 23](examples/lighthouse-seed-23.png)
- [Robot gardener, seed 41](examples/robot-seed-41.png)
- [Reference board, seed 57](examples/reference-board-seed-57.png)
- [Annotated review, seed 57](examples/review-overlay-seed-57.png)
- [Reviewed robot, seed 57](examples/robot-reviewed-seed-57.png)
- [Three-candidate tournament, seed 57](examples/tournament-seed-57.png)
- [Tournament winner, seed 57](examples/tournament-winner-seed-57.png)

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
