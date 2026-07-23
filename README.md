# Autonomous Paint Lab

A small Python/PyGame experiment in which an agent makes reproducible artwork
through a custom Paint-like interface.

The project keeps the canvas model separate from PyGame rendering and provides
five progressively stricter stages:

1. Human-operated Paint application.
2. Structured-state control for verifying drawing primitives.
3. Deterministic screenshot-only control through visible clicks and drags.
4. Visual checkpoints with one limited revision pass.
5. GIF/MP4 recording with concise, visible decision summaries.

The screenshot interface never returns canvas state. Its agent input is the
complete application PNG, and its only drawing outputs are visible UI actions.

## Quick start

```bash
python -m pip install -r requirements.txt
python scripts/run_paint.py
python scripts/run_structured.py --prompt "a lighthouse during a storm using four colours" --seed 23
python scripts/run_screenshot_agent.py --prompt "a cheerful robot tending square flowers" --seed 41
python scripts/screenshot_cli.py --help
```

Generated runs contain the prompt, metadata, action log, complete-application
screenshots, numbered recording frames, final canvas PNG, GIF, and MP4.

Example outputs:

- [Lighthouse, seed 23](examples/lighthouse-seed-23.png)
- [Robot gardener, seed 41](examples/robot-seed-41.png)

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
