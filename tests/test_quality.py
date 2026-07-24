from pathlib import Path
import tempfile
import unittest

from autonomous_paint.plans import prepare_plan
from autonomous_paint.quality import allocate_pass_actions, resolve_budget_policy
from autonomous_paint.session import PaintRun


class QualityPolicyTests(unittest.TestCase):
    def test_high_profile_resolves_floor_target_and_ceiling(self) -> None:
        policy = resolve_budget_policy(
            action_budget=200,
            review_budget=5,
            detail_level="high",
        )
        self.assertEqual((80, 140, 200), (
            policy.minimum_actions,
            policy.target_actions,
            policy.maximum_actions,
        ))
        self.assertEqual(24, policy.revision_actions)
        self.assertEqual(2, policy.reference_minimum)

    def test_pass_allocations_use_every_targeted_action(self) -> None:
        allocation = allocate_pass_actions(140)
        self.assertEqual(140, sum(allocation.values()))
        self.assertTrue(all(value > 0 for value in allocation.values()))

    def test_guinea_pig_plan_reaches_target_with_all_detail_passes(self) -> None:
        plan = prepare_plan(
            "A cute guinea pig resting in a 'cuddle cup'",
            57,
            target_actions=140,
            maximum_actions=200,
            revision_budget=24,
        )
        self.assertEqual(140, len(plan.actions) + len(plan.revision_actions))
        self.assertEqual(
            {
                "composition",
                "construction",
                "form",
                "materials",
                "lighting",
                "texture",
                "focal_finish",
            },
            {action.pass_name for action in plan.actions},
        )
        self.assertIn("fur", plan.detail_ledger)
        self.assertIn("cuddle_cup", plan.detail_ledger)

    def test_save_gate_blocks_an_underdeveloped_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = PaintRun(
                Path(directory),
                "A cute guinea pig resting in a cuddle cup",
                57,
                "model_vision",
                action_budget=200,
                review_budget=5,
                min_actions=80,
                target_actions=140,
                detail_level="high",
            )
            status = run.quality_gate_status()
            self.assertFalse(status["ready"])
            with self.assertRaisesRegex(RuntimeError, "save quality gate blocked"):
                run.assert_save_ready()


if __name__ == "__main__":
    unittest.main()
