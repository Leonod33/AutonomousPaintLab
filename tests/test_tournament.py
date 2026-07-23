from pathlib import Path
import tempfile
import unittest

from autonomous_paint.app import PaintApplication
from autonomous_paint.plans import make_plan
from autonomous_paint.recording import save_png
from autonomous_paint.tournament import (
    build_rubric,
    derive_candidate_seeds,
    score_candidate,
)


class TournamentTests(unittest.TestCase):
    def test_rubric_is_prompt_specific_and_totals_one_hundred(self) -> None:
        robot = build_rubric("a cheerful robot tending square flowers")
        lighthouse = build_rubric("a lighthouse during a storm using four colours")
        self.assertEqual(100, sum(item.weight for item in robot))
        self.assertEqual(100, sum(item.weight for item in lighthouse))
        self.assertIn("colour_rhythm", {item.key for item in robot})
        self.assertIn("four_colour_discipline", {item.key for item in lighthouse})

    def test_candidate_seeds_are_reproducible_and_bounded(self) -> None:
        self.assertEqual((57, 1066, 2075), derive_candidate_seeds(57, 3))
        self.assertEqual(
            derive_candidate_seeds(23, 5),
            derive_candidate_seeds(23, 5),
        )
        with self.assertRaises(ValueError):
            derive_candidate_seeds(1, 1)
        with self.assertRaises(ValueError):
            derive_candidate_seeds(1, 6)

    def test_variant_zero_preserves_baseline_plan(self) -> None:
        prompt = "a cheerful robot tending square flowers"
        baseline = make_plan(prompt, 57)
        explicit_baseline = make_plan(prompt, 57, variant_index=0)
        alternative = make_plan(prompt, 57, variant_index=2)
        self.assertEqual(baseline, explicit_baseline)
        self.assertEqual("coral", baseline.actions[6].colour)
        self.assertNotEqual(baseline.actions, alternative.actions)

    def test_candidate_score_uses_complete_application_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            app = PaintApplication(
                prompt="a cheerful robot tending square flowers",
                seed=57,
            )
            screenshot = save_png(app.render(), base / "complete_app.png")
            final_png = base / "final.png"
            app.model.save(final_png)
            rubric = build_rubric(app.prompt)
            first = score_candidate("A", screenshot, final_png, app.prompt, rubric)
            second = score_candidate("A", screenshot, final_png, app.prompt, rubric)
            self.assertEqual(first, second)
            self.assertEqual(5, len(first.criteria))
            self.assertTrue(0 <= first.total_score <= 100)
            self.assertTrue(all(item.evidence for item in first.criteria))


if __name__ == "__main__":
    unittest.main()
