from pathlib import Path
import tempfile
import unittest

from autonomous_paint.app import PaintApplication
from autonomous_paint.constants import CANVAS_ORIGIN, PALETTE


class PaintApplicationTests(unittest.TestCase):
    def test_visible_tool_palette_drag_and_save_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "final.png"
            app = PaintApplication(output_path=output)
            line_control = app._tool_rects["line"].center
            coral_control = app._palette_rects["coral"].center
            self.assertEqual("line", app.click(line_control).control)
            self.assertEqual("palette:coral", app.click(coral_control).control)
            start = (CANVAS_ORIGIN[0] + 10, CANVAS_ORIGIN[1] + 10)
            end = (CANVAS_ORIGIN[0] + 100, CANVAS_ORIGIN[1] + 100)
            self.assertTrue(app.drag(start, end).drawing_applied)
            colours = {colour for _, colour in app.model.image.getcolors(maxcolors=5000) or []}
            self.assertIn(PALETTE["coral"], colours)
            result = app.click(app._tool_rects["save"].center)
            self.assertEqual(str(output), result.saved_path)
            self.assertTrue(output.exists())

    def test_clear_and_undo_are_visible_controls(self) -> None:
        app = PaintApplication()
        app.model.line((0, 0), (50, 50), (0, 0, 0), 4)
        changed = app.model.image.tobytes()
        result = app.click(app._tool_rects["clear"].center)
        self.assertTrue(result.drawing_applied)
        self.assertNotEqual(changed, app.model.image.tobytes())
        self.assertTrue(app.click(app._tool_rects["undo"].center).applied)
        self.assertEqual(changed, app.model.image.tobytes())

    def test_budget_configuration_round_trips_with_counters(self) -> None:
        app = PaintApplication(
            action_budget=180,
            review_budget=5,
            revision_budget=8,
        )
        app.drawing_actions = 72
        app.review_checkpoints = 4
        app.revision_actions = 6
        restored = PaintApplication.from_payload(app.to_payload())
        self.assertEqual(180, restored.action_budget)
        self.assertEqual(5, restored.review_budget)
        self.assertEqual(8, restored.revision_budget)
        self.assertEqual(72, restored.drawing_actions)
        self.assertEqual(4, restored.review_checkpoints)
        self.assertEqual(6, restored.revision_actions)

    def test_visible_curve_tool_creates_and_edits_persistent_curve(self) -> None:
        app = PaintApplication()
        self.assertEqual("curve", app.click(app._tool_rects["curve"].center).control)
        start = (CANVAS_ORIGIN[0] + 100, CANVAS_ORIGIN[1] + 300)
        end = (CANVAS_ORIGIN[0] + 500, CANVAS_ORIGIN[1] + 300)
        created = app.drag(start, end)
        self.assertTrue(created.drawing_applied)
        identifier = app.selected_curve_id
        self.assertIsNotNone(identifier)
        control_before = app.model.curve_points(identifier)[1]  # type: ignore[arg-type]
        self.assertEqual("edit", app.click(app._tool_rects["edit"].center).control)
        control_screen = (
            CANVAS_ORIGIN[0] + control_before[0],
            CANVAS_ORIGIN[1] + control_before[1],
        )
        edited = app.drag(
            control_screen,
            (control_screen[0], control_screen[1] + 80),
        )
        self.assertTrue(edited.drawing_applied)
        self.assertNotEqual(
            control_before,
            app.model.curve_points(identifier)[1],  # type: ignore[arg-type]
        )

    def test_gradient_secondary_colour_brush_effects_and_guides_are_visible(self) -> None:
        app = PaintApplication()
        self.assertEqual(
            "secondary:select",
            app.click(app._secondary_colour_rect.center).control,
        )
        self.assertEqual(
            "secondary:navy",
            app.click(app._palette_rects["navy"].center).control,
        )
        self.assertEqual("primary:select", app.click(app._custom_colour_rect.center).control)
        self.assertEqual("palette:coral", app.click(app._palette_rects["coral"].center).control)
        self.assertEqual("gradient", app.click(app._tool_rects["gradient"].center).control)
        start = (CANVAS_ORIGIN[0], CANVAS_ORIGIN[1] + 300)
        end = (CANVAS_ORIGIN[0] + 759, CANVAS_ORIGIN[1] + 300)
        self.assertTrue(app.drag(start, end).drawing_applied)
        self.assertEqual(PALETTE["coral"], app.model.image.getpixel((0, 300)))
        self.assertEqual(PALETTE["navy"], app.model.image.getpixel((759, 300)))

        canvas_before_guides = app.model.image.tobytes()
        self.assertEqual("guides:on", app.click(app._tool_rects["guides"].center).control)
        self.assertNotEqual(
            app.render().get_at((CANVAS_ORIGIN[0] + 760 // 3, CANVAS_ORIGIN[1] + 20))[:3],
            app.model.image.getpixel((760 // 3, 20)),
        )
        self.assertEqual(canvas_before_guides, app.model.image.tobytes())
        self.assertEqual("brush_fx:soft", app.click(app._tool_rects["brush_fx"].center).control)
        self.assertEqual("symmetry:on", app.click(app._tool_rects["symmetry"].center).control)

        restored = PaintApplication.from_payload(app.to_payload())
        self.assertEqual("soft", restored.brush_effect)
        self.assertTrue(restored.symmetry_enabled)
        self.assertTrue(restored.guides_visible)
        self.assertEqual(PALETTE["navy"], restored.secondary_colour)


if __name__ == "__main__":
    unittest.main()
