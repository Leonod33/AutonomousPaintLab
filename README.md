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
confidence, and proposed correction in ordinary language. Genuine model-vision
runs additionally require recognizability and prompt-fidelity scores. A later
revision no longer clears a finding by itself: the agent must reinspect every
actionable region and mark it resolved, improved, or unresolved with new visible
evidence.

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

The model-vision screenshot CLI enables semantic quality gates by default:

```bash
python scripts/screenshot_cli.py --state-file session.json review \
  --assessment "The subject is recognizable but the front rim looks rigid." \
  --recognizability-score 7.5 --recognizable-without-prompt \
  --prompt-fidelity-score 8.0 \
  --semantic-summary "A resting guinea pig and enclosing bed are clear." \
  --finding '{"area":"Front rim","region":[120,370,520,110],"issue":"The rim is too straight.","suggestion":"Reshape the editable curve into a compressed padded arc.","priority":"high","confidence":0.92,"evidence":"The visible front edge is a single rigid horizontal segment."}'

python scripts/screenshot_cli.py --state-file session.json verify \
  --assessment "The revised rim now bows and compresses below the paws." \
  --recognizability-score 8.2 --recognizable-without-prompt \
  --prompt-fidelity-score 8.5 \
  --semantic-summary "The guinea pig and padded cup are now both immediately clear." \
  --verification '{"finding_id":"R1-1","status":"resolved","evidence":"The formerly straight edge is now an uneven padded arc."}'
```

For tournaments, keep the deterministic pixel score as a reproducible baseline,
then apply blind model-vision judgments with:

```bash
python scripts/apply_semantic_judgments.py \
  --run-dir runs/guinea-pig-tournament \
  --judgments runs/guinea-pig-tournament/semantic_judgments.json
```

To remove the manual judgment-file handoff, provide any vision-capable judge
command that accepts the generated blind request and writes the requested JSON:

```bash
python scripts/run_tournament.py \
  --prompt "A cute guinea pig resting in a 'cuddle cup'" \
  --run-dir runs/guinea-pig-tournament \
  --semantic-judge-command \
  'vision-judge --request {request} --output {output}'
```

The command receives `semantic_judge_request.json`, containing only the public
prompt, visible rubric, neutral candidate labels, and copied complete-application
screenshots. Seeds, plans, canvas state, action logs, review reports, and
deterministic scores are excluded. Its result is validated and applied
automatically; the invocation audit, raw judgments, semantic report, montage,
and updated winner are retained. The same step can be run later with
`scripts/run_semantic_judge.py`.

The semantic judge hard-gates candidates that are not recognizable without the
prompt, validates evidence for every rubric score, records localized findings,
and subtracts a similarity penalty when finalists repeat silhouettes, poses,
framing, palettes, or construction.

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

The visible application includes adjustable 1–64 px strokes, outlined, filled,
and combined shape modes, eyedropper sampling, custom/recent colour state, an
expanded natural palette, and a coordinate magnifier. Layers can be selected,
added, removed, hidden, revealed, and moved through the compositing order.

The **GRADIENT** tool fills the active layer along the direction of a drag,
interpolating from colour slot **A** to **B**. Select either visible slot and
then click a palette colour before dragging. **BRUSH_FX** cycles through solid,
soft, textured, and scattered strokes; every effect is deterministic and
therefore reproducible from the action log. **SMUDGE** moves and softly blends a
local patch. **SYMMETRY** mirrors brush strokes across the vertical centre as
one undoable drawing action. **GUIDES** overlays the rule of thirds, centre
lines, and diagonals without changing or saving those guide pixels.

The **CURVE** tool creates a persistent quadratic Bézier object. Dragging makes
a useful bowed curve in one drawing action; three clicks provide explicit
start, control, and end points. Select **EDIT** and drag an anchor or the yellow
control handle to reshape the curve without repainting the surrounding image.
Curves, control points, layer ordering, undo history, and raster content all
survive session serialization.

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
