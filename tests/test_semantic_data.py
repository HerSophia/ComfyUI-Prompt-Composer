import json
import unittest
from pathlib import Path

SEMANTIC_DIR = Path(__file__).resolve().parent.parent / "prompt_composer" / "data" / "semantic"


class SemanticDataTest(unittest.TestCase):
    def test_semantic_files_exist(self):
        files = list(SEMANTIC_DIR.glob("*.json"))
        self.assertGreater(len(files), 5)

    def test_entries_have_required_fields(self):
        for file_path in SEMANTIC_DIR.glob("*.json"):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, list, file_path.name)
            for entry in data[:20]:
                self.assertIn("tag", entry)
                self.assertIn("category", entry)
                self.assertIn("weight", entry)
                self.assertIn("label_zh", entry)
                self.assertIn("post_count", entry)

    def test_rules_overlay_valid(self):
        overlay = SEMANTIC_DIR / "rules" / "overlay.json"
        self.assertTrue(overlay.exists())
        data = json.loads(overlay.read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        for rule in data:
            self.assertIn("tag", rule)


if __name__ == "__main__":
    unittest.main()
