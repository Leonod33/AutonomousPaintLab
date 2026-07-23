"""Reference-image manifests and safe thumbnail preparation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image


@dataclass(frozen=True)
class ReferenceCard:
    title: str
    source_url: str
    note: str
    image_path: str = ""
    search_query: str = ""
    rights_note: str = "Visual research only; do not trace or reproduce exactly."

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
        base_dir: Path | None = None,
    ) -> "ReferenceCard":
        image_path = str(value.get("image_path", ""))
        if image_path and base_dir is not None and not Path(image_path).is_absolute():
            image_path = str((base_dir / image_path).resolve())
        return cls(
            title=str(value["title"]),
            source_url=str(value["source_url"]),
            note=str(value["note"]),
            image_path=image_path,
            search_query=str(value.get("search_query", "")),
            rights_note=str(
                value.get(
                    "rights_note",
                    "Visual research only; do not trace or reproduce exactly.",
                )
            ),
        )

    @property
    def source_host(self) -> str:
        return urlparse(self.source_url).netloc or self.source_url


def load_reference_manifest(path: Path | None) -> tuple[ReferenceCard, ...]:
    if path is None:
        return ()
    if not path.exists():
        raise FileNotFoundError(f"reference manifest does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    items = value.get("references") if isinstance(value, dict) else None
    if not isinstance(items, list):
        raise ValueError("reference manifest must contain a references array")
    return tuple(ReferenceCard.from_dict(item, path.parent) for item in items)


def prepare_reference(
    run_dir: Path,
    *,
    title: str,
    source_url: str,
    note: str,
    search_query: str = "",
    rights_note: str = "Visual research only; do not trace or reproduce exactly.",
    image_path: Path | None = None,
    image_url: str = "",
) -> Path:
    """Append one attributed reference and create a local display thumbnail."""
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "references.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"references": []}
    if not isinstance(manifest.get("references"), list):
        raise ValueError("existing reference manifest is malformed")

    index = len(manifest["references"]) + 1
    relative_thumbnail = ""
    if image_path is not None or image_url:
        reference_dir = run_dir / "references"
        reference_dir.mkdir(parents=True, exist_ok=True)
        raw_path = reference_dir / f"reference_{index:02d}.source"
        if image_path is not None:
            if not image_path.exists():
                raise FileNotFoundError(f"reference image does not exist: {image_path}")
            shutil.copyfile(image_path, raw_path)
        else:
            _download_image(image_url, raw_path)
        thumbnail = reference_dir / f"reference_{index:02d}.png"
        with Image.open(raw_path) as source:
            image = source.convert("RGB")
            image.thumbnail((420, 280), Image.Resampling.LANCZOS)
            image.save(thumbnail, format="PNG")
        raw_path.unlink()
        relative_thumbnail = str(thumbnail.relative_to(run_dir))

    card = ReferenceCard(
        title=title,
        source_url=source_url,
        note=note,
        image_path=relative_thumbnail,
        search_query=search_query,
        rights_note=rights_note,
    )
    manifest["references"].append(card.to_dict())
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def _download_image(url: str, destination: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("reference image URL must use http or https")
    request = Request(url, headers={"User-Agent": "AutonomousPaintLab/0.2"})
    with urlopen(request, timeout=20) as response:
        content_type = response.headers.get_content_type()
        if not content_type.startswith("image/"):
            raise ValueError(f"reference URL returned {content_type}, not an image")
        data = response.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        raise ValueError("reference image exceeds the 12 MiB limit")
    destination.write_bytes(data)
