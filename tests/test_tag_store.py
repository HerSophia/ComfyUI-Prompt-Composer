import unittest

from prompt_composer.core.models import TagEntry
from prompt_composer.core.pipeline import load_default_store
from prompt_composer.core.tag_store import TagStore


class TagStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = load_default_store()

    def test_three_layer_load(self):
        # 三层加载后能查到真实数据里的常见 tag。
        self.assertIsNotNone(self.store.find("standing"))
        self.assertIsNotNone(self.store.find("dress"))
        self.assertGreater(len(self.store.all()), 1000)

    def test_categories_present(self):
        cats = self.store.categories()
        for expected in ["pose", "hand", "clothing", "hair", "eyes"]:
            self.assertIn(expected, cats)

    def test_overlay_applied(self):
        # overlay 里给 dress 加了 conflicts。
        dress = self.store.find("dress")
        self.assertIn("pants", dress.conflicts)

    def test_unclassified_tag_not_in_store(self):
        # 角色名没有进入候选（映射表标为 null）。
        self.assertIsNone(self.store.find("hatsune_miku"))

    def test_duplicate_tag_raises(self):
        entry = TagEntry(tag="same", category="pose")
        with self.assertRaises(ValueError):
            TagStore([entry, entry])


if __name__ == "__main__":
    unittest.main()
