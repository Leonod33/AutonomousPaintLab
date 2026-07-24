from pathlib import Path
import tempfile
import unittest

from autonomous_paint.constants import CANVAS_ORIGIN
from autonomous_paint.review import (
    FindingVerification,
    ReviewFinding,
    SemanticAssessment,
)
from autonomous_paint.session import DecisionSummary, PaintRun, VisibleAction


class SemanticQualityTests(unittest.TestCase):
    def test_high_finding_requires_revision_and_visual_reinspection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = PaintRun(
                Path(directory) / "run",
                "a recognizable subject",
                5,
                "model_vision",
                action_budget=10,
                min_actions=0,
                target_actions=2,
                review_budget=1,
                revision_budget=2,
                detail_level="draft",
                semantic_quality_required=True,
                recognizability_threshold=7.0,
            )
            finding = ReviewFinding(
                "R1-1",
                "Subject contour",
                (20, 20, 200, 150),
                "The contour is too straight to describe the requested soft form.",
                "Bow the contour and preserve the surrounding silhouette.",
                "high",
                0.9,
                "The visible upper edge is a single rigid segment.",
            )
            run.review(
                "The subject reads, but its contour needs correction.",
                (finding,),
                semantic_assessment=SemanticAssessment(
                    8.0,
                    True,
                    8.0,
                    "The requested subject is recognizable without the prompt.",
                ),
            )
            status = run.quality_gate_status()
            self.assertFalse(status["checks"]["high_findings_addressed"])
            self.assertFalse(status["checks"]["reinspection_complete"])
            with self.assertRaises(RuntimeError):
                run.verify_findings(
                    "No correction was made.",
                    (
                        FindingVerification(
                            "R1-1",
                            "resolved",
                            "The edge now appears soft.",
                        ),
                    ),
                )
            run.execute(
                VisibleAction(
                    "click",
                    (CANVAS_ORIGIN[0] + 40, CANVAS_ORIGIN[1] + 40),
                ),
                DecisionSummary(
                    "Correct the reviewed contour.",
                    "brush",
                    "Add a short curved correction.",
                    "The reviewed edge remains visible.",
                ),
                is_revision=True,
            )
            run.verify_findings(
                "The corrected edge now follows the requested form.",
                (
                    FindingVerification(
                        "R1-1",
                        "resolved",
                        "The rigid segment has been replaced by a visibly rounded edge.",
                    ),
                ),
                semantic_assessment=SemanticAssessment(
                    8.5,
                    True,
                    8.5,
                    "The corrected subject remains recognizable and more coherent.",
                ),
            )
            status = run.quality_gate_status()
            self.assertTrue(status["checks"]["high_findings_addressed"])
            self.assertTrue(status["checks"]["recognizability_gate"])
            self.assertTrue(status["checks"]["reinspection_complete"])


if __name__ == "__main__":
    unittest.main()
