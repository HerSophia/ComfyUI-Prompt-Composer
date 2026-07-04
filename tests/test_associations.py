import json
import tempfile
import unittest
from pathlib import Path

from prompt_composer.core.association_store import AssociationStore
from prompt_composer.tools.build_associations import (
    compute_associations,
    compute_strength,
    cond_prob,
)


class AssociationStrengthTest(unittest.TestCase):
    def test_cosine_strength_in_range(self):
        # 高共现给出较高 cosine 强度，落在 [0, 1]。
        s = compute_strength(1500, 5000, 2000, metric="cosine")
        self.assertGreater(s, 0.4)
        self.assertLessEqual(s, 1.0)

    def test_low_cooccurrence_is_weak(self):
        # 画面互斥的低共现应给出很小的强度。
        weak = compute_strength(10, 5000, 3000, metric="cosine")
        self.assertLess(weak, 0.05)

    def test_strength_clamped_to_one(self):
        # 频次口径差异导致越界时，强度截断到 1.0。
        s = compute_strength(6000, 5000, 5000, metric="cosine")
        self.assertLessEqual(s, 1.0)

    def test_cond_prob(self):
        self.assertAlmostEqual(cond_prob(1500, 5000), 0.3)
        self.assertEqual(cond_prob(0, 5000), 0.0)
        self.assertEqual(cond_prob(1500, 0), 0.0)

    def test_compute_associations_structure_and_conflict(self):
        semantic = {
            "long_hair": {"category": "hair", "post_count": 5000},
            "short_hair": {"category": "hair", "post_count": 3000},
            "blue_eyes": {"category": "eyes", "post_count": 2000},
        }
        stats = {
            "long_hair": {"n": 5000, "linking_to": {"short_hair"}, "linked_by": set()},
            "short_hair": {"n": 3000, "linking_to": {"long_hair"}, "linked_by": set()},
            "blue_eyes": {"n": 2000, "linking_to": set(), "linked_by": set()},
        }
        cooc = {
            "long_hair": {"blue_eyes": 1500, "short_hair": 10},
            "blue_eyes": {"long_hair": 1500},
            "short_hair": {"long_hair": 10},
        }
        related, candidates = compute_associations(semantic, stats, cooc)
        # blue_eyes 应进 long_hair 的关联。
        self.assertIn("long_hair", related)
        self.assertTrue(any(item["tag"] == "blue_eyes" for item in related["long_hair"]))
        # short_hair被 wiki 链接但共现极低，不该进 related。
        self.assertTrue(all(item["tag"] != "short_hair" for item in related["long_hair"]))
        # 同为 hair 分类的互斥对应进 conflicts 候选。
        conflict_pairs = {
            tuple(sorted((c["tag"], c["other"]))) for c in candidates["conflicts"]
        }
        self.assertIn(("long_hair", "short_hair"), conflict_pairs)


class AssociationStoreTest(unittest.TestCase):
    def _make_store(self):
        return AssociationStore(
            {
                "cat_ears": [
                    {"tag": "animal_ears", "weight": 0.5},
                    {"tag": "animal_ear_fluff", "weight": 0.4},
                    {"tag": "paw_pose", "weight": 0.2},
                ],
                "long_hair": [{"tag": "very_long_hair", "weight": 0.6}],
            }
        )

    def test_related_sorted_and_limited(self):
        store = self._make_store()
        items = store.related("cat_ears", limit=2)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["tag"], "animal_ears")

    def test_related_tags(self):
        store = self._make_store()
        self.assertEqual(
            store.related_tags("cat_ears"),
            ["animal_ears", "animal_ear_fluff", "paw_pose"],
        )

    def test_weight_of(self):
        store = self._make_store()
        self.assertAlmostEqual(store.weight_of("cat_ears", "animal_ears"), 0.5)
        self.assertEqual(store.weight_of("cat_ears", "nope"), 0.0)

    def test_missing_tag_returns_empty(self):
        store = self._make_store()
        self.assertEqual(store.related("does_not_exist"), [])
        self.assertFalse(store.has("does_not_exist"))

    def test_case_insensitive(self):
        store = self._make_store()
        self.assertTrue(store.has("CAT_EARS"))
        self.assertEqual(len(store.related("Cat_Ears")), 3)

    def test_missing_file_returns_empty_store(self):
        store = AssociationStore.from_file(
            Path(tempfile.gettempdir()) / "pc_no_such_assoc_file.json"
        )
        self.assertEqual(store.tags(), [])
        self.assertEqual(store.related("cat_ears"), [])

    def test_from_file_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "assoc.json"
            data= {"a": [{"tag": "b", "weight": 0.3}]}
            path.write_text(json.dumps(data), encoding="utf-8")
            store = AssociationStore.from_file(path)
            self.assertEqual(store.related_tags("a"), ["b"])

    def test_bad_items_are_dropped(self):
        store = AssociationStore(
            {
                "a": [
                    {"tag": "b", "weight": 0.3},
                    {"weight": 0.5},
                    "not_a_dict",
                    {"tag": "", "weight": 1.0},
                ]
            }
        )
        self.assertEqual(store.related_tags("a"), ["b"])


if __name__ == "__main__":
    unittest.main()
