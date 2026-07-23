from pathlib import Path
import tempfile
import unittest

from autonomous_paint.model import CanvasModel


class CanvasModelTests(unittest.TestCase):
    def test_primitives_change_pixels_and_undo_restores_previous_image(self) -> None:
        model = CanvasModel(80, 60)
        original = model.image.tobytes()
        model.line((5, 5), (70, 50), (0, 0, 0), 3)
        after_line = model.image.tobytes()
        self.assertNotEqual(original, after_line)
        model.rectangle((10, 10), (40, 35), (255, 0, 0), 2)
        self.assertTrue(model.undo())
        self.assertEqual(after_line, model.image.tobytes())

    def test_fill_stays_inside_closed_rectangle(self) -> None:
        model = CanvasModel(50, 50)
        model.rectangle((10, 10), (40, 40), (0, 0, 0), 2)
        model.fill((20, 20), (255, 0, 0))
        self.assertEqual((255, 0, 0), model.image.getpixel((20, 20)))
        self.assertEqual(model.background, model.image.getpixel((2, 2)))

    def test_payload_round_trip_preserves_image_and_history(self) -> None:
        model = CanvasModel(40, 30)
        model.brush([(2, 2), (20, 20)], (10, 20, 30), 5)
        restored = CanvasModel.from_payload(model.to_payload())
        self.assertEqual(model.image.tobytes(), restored.image.tobytes())
        self.assertTrue(restored.undo())

    def test_save_writes_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            CanvasModel(20, 20).save(path)
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

