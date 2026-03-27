import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from app.services.image_selector import KnowledgeImageSelector


class StubLLM:
    def __init__(self, response=None, error=False):
        self.response = response or '{"choice": 1, "reason": "best match"}'
        self.error = error

    def generate(self, prompt, options=None):
        if self.error:
            raise RuntimeError("LLM unavailable")
        return self.response


class ImageSelectorTests(unittest.TestCase):
    def setUp(self):
        KnowledgeImageSelector._chunk_cache = {}
        KnowledgeImageSelector._selection_cache.clear()
        self.processed_dir = Path.cwd() / ".tmp-test-image-selector" / uuid4().hex
        self.collection_dir = self.processed_dir / "kinexushhd"
        self.images_dir = self.collection_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.processed_dir, ignore_errors=True))

    def _write_chunk_file(self, name, rows):
        path = self.collection_dir / name
        with open(path, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def test_select_image_uses_model_choice_from_nearby_candidates(self):
        first = self.images_dir / "page_022_img_001.png"
        second = self.images_dir / "page_023_img_001.png"
        first.write_bytes(b"first")
        second.write_bytes(b"second")

        self._write_chunk_file(
            "patient_chunks.jsonl",
            [
                {
                    "type": "text",
                    "page": 22,
                    "section": "Summary",
                    "domain": "patient",
                    "text": "Summary tab overview image with clinic overview cards.",
                    "image_path": "images/page_022_img_001.png",
                },
                {
                    "type": "text",
                    "page": 23,
                    "section": "Patients",
                    "domain": "patient",
                    "text": "Patients tab image with therapy gap filter and patient list details.",
                    "image_path": "images/page_023_img_001.png",
                },
            ],
        )

        selector = KnowledgeImageSelector(
            processed_dir=self.processed_dir,
            llm=StubLLM(response='{"choice": 2, "reason": "patients screen fits therapy gap better"}'),
        )

        selected = selector.select_image("kinexushhd", page=22, section="Summary")

        self.assertIsNotNone(selected)
        self.assertEqual(Path(selected["image_path"]).name, "page_023_img_001.png")

    def test_select_image_falls_back_to_top_heuristic_when_model_fails(self):
        same_page = self.images_dir / "page_023_img_000.png"
        next_page = self.images_dir / "page_024_img_000.png"
        same_page.write_bytes(b"same")
        next_page.write_bytes(b"next")

        self._write_chunk_file(
            "patient_chunks.jsonl",
            [
                {
                    "type": "text",
                    "page": 23,
                    "section": "Patients",
                    "domain": "patient",
                    "text": "Patients screen screenshot with therapy gap filter.",
                    "image_path": "images/page_023_img_000.png",
                },
                {
                    "type": "text",
                    "page": 24,
                    "section": "Clinic Dashboard",
                    "domain": "alerts",
                    "text": "Dashboard image.",
                    "image_path": "images/page_024_img_000.png",
                },
            ],
        )

        selector = KnowledgeImageSelector(
            processed_dir=self.processed_dir,
            llm=StubLLM(error=True),
        )

        selected = selector.select_image("kinexushhd", page=23, section="Patients")

        self.assertIsNotNone(selected)
        self.assertEqual(Path(selected["image_path"]).name, "page_023_img_000.png")


if __name__ == "__main__":
    unittest.main()
