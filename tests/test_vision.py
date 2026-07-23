from pathlib import Path
import tempfile
import unittest

from autonomous_paint.app import PaintApplication
from autonomous_paint.constants import CANVAS_ORIGIN, CANVAS_SIZE, PALETTE, TOOL_MARKERS
from autonomous_paint.vision import assess_canvas, locate_interface


class ScreenshotVisionTests(unittest.TestCase):
    def test_locates_every_visible_control_and_canvas_from_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.png"
            PaintApplication().save_screenshot(path)
            located = locate_interface(path)
            self.assertEqual(CANVAS_ORIGIN, located.canvas_origin)
            self.assertEqual(CANVAS_SIZE, located.canvas_size)
            self.assertEqual(set(TOOL_MARKERS), set(located.controls))
            self.assertEqual(set(PALETTE), set(located.palette))

    def test_assessment_uses_visible_canvas_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.png"
            app = PaintApplication()
            app.model.fill((0, 0), PALETTE["navy"])
            app.model.rectangle((100, 100), (300, 300), PALETTE["white"], 8)
            app.save_screenshot(path)
            located = locate_interface(path)
            assessment = assess_canvas(path, located)
            self.assertIn("palette colours visible", assessment)
            self.assertIn("canvas edges remain intact", assessment)


if __name__ == "__main__":
    unittest.main()

