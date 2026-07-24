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

    def test_layers_and_advanced_primitives_are_reversible(self) -> None:
        model = CanvasModel(80, 60)
        baseline = model.image.tobytes()
        layer = model.add_layer("Highlights")
        self.assertEqual(("Background", "Highlights"), model.layer_names)
        self.assertEqual(1, layer)
        model.gradient((10, 20, 30), (80, 90, 100))
        model.bezier((5, 50), (40, 5), (75, 50), (255, 255, 255), 3)
        model.polygon([(10, 10), (35, 8), (20, 35)], (255, 0, 0), filled=True)
        self.assertNotEqual(baseline, model.image.tobytes())
        model.set_layer_visible(1, False)
        self.assertEqual(baseline, model.image.tobytes())
        self.assertTrue(model.undo())
        self.assertNotEqual(baseline, model.image.tobytes())

    def test_persistent_curve_can_be_selected_reshaped_and_serialized(self) -> None:
        model = CanvasModel(100, 80)
        identifier = model.add_curve_object(
            (10, 60),
            (50, 10),
            (90, 60),
            (10, 20, 30),
            5,
        )
        before = model.image.tobytes()
        self.assertEqual(identifier, model.nearest_curve((50, 35)))
        model.edit_curve_point(identifier, 1, (50, 55))
        self.assertNotEqual(before, model.image.tobytes())
        restored = CanvasModel.from_payload(model.to_payload())
        self.assertEqual(model.image.tobytes(), restored.image.tobytes())
        self.assertEqual((50, 55), restored.curve_points(identifier)[1])

    def test_layers_can_be_reordered_and_hidden(self) -> None:
        model = CanvasModel(40, 40)
        model.add_layer("Subject")
        model.add_layer("Highlights")
        self.assertEqual(2, model.move_layer(1, 1))
        self.assertEqual(("Background", "Highlights", "Subject"), model.layer_names)
        model.set_layer_visible(2, False)
        self.assertFalse(model.layer_visibility[2])

    def test_transparent_layer_survives_session_round_trip(self) -> None:
        model = CanvasModel(40, 30)
        model.linear_gradient((0, 0), (39, 0), (10, 20, 30), (90, 100, 110))
        underlying = model.image.tobytes()
        model.add_layer("Subject")
        restored = CanvasModel.from_payload(model.to_payload())
        self.assertEqual(underlying, restored.image.tobytes())
        restored.rectangle((10, 8), (25, 22), (200, 100, 50), filled=True)
        self.assertEqual((10, 20, 30), restored.image.getpixel((0, 0)))
        self.assertEqual((200, 100, 50), restored.image.getpixel((15, 15)))

    def test_directional_gradient_uses_both_colours_and_is_undoable(self) -> None:
        model = CanvasModel(60, 30)
        original = model.image.tobytes()
        model.linear_gradient((0, 15), (59, 15), (10, 20, 30), (210, 220, 230))
        self.assertEqual((10, 20, 30), model.image.getpixel((0, 15)))
        self.assertEqual((210, 220, 230), model.image.getpixel((59, 15)))
        self.assertNotEqual(model.image.getpixel((15, 15)), model.image.getpixel((45, 15)))
        self.assertTrue(model.undo())
        self.assertEqual(original, model.image.tobytes())

    def test_brush_effects_are_distinct_and_symmetry_is_single_undo_step(self) -> None:
        outputs = []
        for effect in ("solid", "soft", "texture", "scatter"):
            model = CanvasModel(100, 60)
            model.effect_brush([(15, 15), (30, 30), (45, 20)], (20, 40, 80), 12, effect)
            outputs.append(model.image.tobytes())
        self.assertEqual(4, len(set(outputs)))

        model = CanvasModel(100, 60)
        baseline = model.image.tobytes()
        model.effect_brush(
            [(10, 20), (25, 30)],
            (200, 20, 40),
            8,
            "solid",
            mirror_horizontal=True,
        )
        self.assertNotEqual(model.background, model.image.getpixel((10, 20)))
        self.assertNotEqual(model.background, model.image.getpixel((89, 20)))
        self.assertTrue(model.undo())
        self.assertEqual(baseline, model.image.tobytes())

    def test_smudge_blends_along_path_without_copying_endpoint_square(self) -> None:
        model = CanvasModel(100, 60)
        model.rectangle((40, 5), (55, 55), (245, 245, 220), filled=True)
        before = model.image.tobytes()
        model.smudge((47, 15), (52, 48), 10)
        self.assertNotEqual(before, model.image.tobytes())
        self.assertNotEqual(model.background, model.image.getpixel((39, 30)))
        self.assertEqual(model.background, model.image.getpixel((80, 30)))
        self.assertTrue(model.undo())
        self.assertEqual(before, model.image.tobytes())


if __name__ == "__main__":
    unittest.main()
