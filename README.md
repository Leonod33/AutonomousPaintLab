# Autonomous Paint Lab

A small Python/PyGame experiment in which an agent makes reproducible artwork
through a custom Paint-like interface.

The project keeps the canvas model separate from PyGame rendering and provides
six progressively stricter stages:

1. Human-operated Paint application.
2. Structured-state control for verifying drawing primitives.
3. Deterministic screenshot-only control through visible clicks and drags.
4. Visual checkpoints with one limited revision pass.
5. GIF/MP4 recording with concise, visible decision summaries.
6. Blind variant tournaments that compare several screenshot-only candidates
   with a prompt-specific visible rubric.

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
references, and a human-readable visual review report.

Run a three-candidate tournament:

```bash
python scripts/run_tournament.py \
  --prompt "a cheerful robot tending square flowers" \
  --seed 57 --candidates 3 \
  --run-dir runs/robot-tournament
```

Each candidate receives an isolated action and review budget. The tournament
judge sees only the final complete-application screenshots, brief, and visible
rubric—not seeds, canvas state, logs, or review reports. It preserves every
candidate and produces `tournament.json`, `tournament_report.md`,
`tournament_montage.png`, `winner.png`, and `winner_full_app.png`.

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
