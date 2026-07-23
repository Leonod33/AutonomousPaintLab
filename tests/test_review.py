from pathlib import Path
import tempfile
import unittest

from autonomous_paint.app import PaintApplication
from autonomous_paint.review import ReviewFinding
from autonomous_paint.session import DecisionSummary, PaintRun, VisibleAction


class ReviewFindingTests(unittest.TestCase):
    def test_review_overlay_is_visible_but_does_not_mutate_canvas(self) -> None:
        app = PaintApplication()
        before = app.model.image.tobytes()
        plain = app.render().get_view("1").raw
        finding = ReviewFinding(
            "R1-1",
            "Robot face",
            (200, 100, 180, 150),
            "The smile is too faint to carry the expression.",
            "Add one short warm highlight beneath the mouth.",
            "high",
            0.9,
            "The face has less local contrast than the body.",
        )
        app.set_review_findings((finding,))
        reviewed = app.render().get_view("1").raw
        self.assertNotEqual(plain, reviewed)
        self.assertEqual(before, app.model.image.tobytes())

    def test_review_report_uses_plain_language_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = PaintRun(
                Path(directory),
                "a cheerful robot tending square flowers",
                17,
                "model_vision",
            )
            finding = ReviewFinding(
                "R1-1",
                "Flower spacing",
                (440, 300, 300, 180),
                "The flowers repeat at exactly the same rhythm.",
                "Vary one flower height while keeping the square motif.",
                "medium",
                0.78,
            )
            run.review("The scene is readable but rhythm needs variety.", (finding,))
            report = run._write_review_report().read_text(encoding="utf-8")
            self.assertIn("Needs improving", report)
            self.assertIn("Suggested improvement", report)
            self.assertIn("Flower spacing", report)
            partials = list(Path(directory).rglob(".*.png"))
            self.assertEqual([], partials)

    def test_review_report_traces_trigger_revision_and_deferred_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = PaintRun(
                Path(directory),
                "a cheerful robot tending square flowers",
                17,
                "model_vision",
            )
            trigger = ReviewFinding(
                "R3-1",
                "Robot face",
                (0, 0, 180, 150),
                "The mouth is a single thin dark stroke.",
                "Add one short warm smile highlight.",
                "high",
                0.88,
                "The thin mouth has less visual weight than the large eyes.",
            )
            deferred = ReviewFinding(
                "R3-2",
                "Flower spacing",
                (400, 250, 300, 180),
                "The spacing is very regular.",
                "Vary one flower height.",
                "low",
                0.69,
                "The blossoms sit at near-even intervals.",
            )
            run.execute(
                VisibleAction("drag", (320, 446), (380, 446)),
                DecisionSummary(
                    "Establish the scene.",
                    "brush",
                    "Add a ground detail.",
                    "The canvas needs an initial anchor.",
                ),
            )
            run.review("The image is readable.", (trigger, deferred))
            run.execute(
                VisibleAction("drag", (30, 146), (90, 146)),
                DecisionSummary(
                    "Strengthen the expression.",
                    "brush",
                    "Add one short warm smile highlight.",
                    "The face is readable but the mouth is still thin.",
                ),
            )
            run.app.model.save(run.output_path)
            after = run.capture("after_revision")
            report = run._write_review_report(after).read_text(encoding="utf-8")
            self.assertIn("Triggered by:** R3-1", report)
            self.assertIn("Intentionally deferred R3-2", report)
            self.assertIn("action screenshot", report)
            self.assertIn("Observed outcome", report)
            self.assertNotIn(str(Path(directory)), report)


if __name__ == "__main__":
    unittest.main()
