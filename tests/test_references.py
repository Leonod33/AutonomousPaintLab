from pathlib import Path
import tempfile
import unittest

from PIL import Image

from autonomous_paint.app import PaintApplication
from autonomous_paint.references import (
    load_reference_manifest,
    prepare_reference,
)


class ReferenceBoardTests(unittest.TestCase):
    def test_local_reference_is_attributed_and_visible_without_canvas_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source.png"
            Image.new("RGB", (300, 180), (40, 160, 100)).save(source)
            manifest = prepare_reference(
                base / "run",
                title="Robot gardener pose",
                source_url="https://example.com/robot-gardener",
                note="Use only the broad pose; invent new shapes and colours.",
                search_query="friendly robot gardening",
                image_path=source,
            )
            references = load_reference_manifest(manifest)
            self.assertEqual(1, len(references))
            self.assertEqual("example.com", references[0].source_host)
            self.assertTrue(Path(references[0].image_path).exists())

            app = PaintApplication(references=references)
            canvas_before = app.model.image.tobytes()
            result = app.click(app._tool_rects["refs"].center)
            self.assertEqual("refs", result.control)
            self.assertTrue(app.reference_board_open)
            app.render()
            self.assertEqual(canvas_before, app.model.image.tobytes())

    def test_metadata_only_reference_remains_usable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = prepare_reference(
                Path(directory),
                title="Geometric flower layout",
                source_url="https://example.com/flowers",
                note="Study spacing and symmetry, not surface details.",
            )
            reference = load_reference_manifest(manifest)[0]
            self.assertEqual("", reference.image_path)


if __name__ == "__main__":
    unittest.main()
