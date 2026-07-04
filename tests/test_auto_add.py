import unittest

from prompt_composer.core.association_store import AssociationStore
from prompt_composer.core.models import GenerationRequest, TagEntry
from prompt_composer.core.pipeline import PromptComposerPipeline
from prompt_composer.core.tag_store import TagStore


def _make_pipeline():
# 一组自足的标签：skirt_lift 依赖 skirt；cat_ears关联 animal_ears。
    entries = [
        TagEntry(tag="skirt_lift", category="pose", weight=1.0, requires=["skirt"]),
        TagEntry(tag="skirt", category="clothing", weight=1.0),
        TagEntry(tag="cat_ears", category="ears", weight=1.0),
        TagEntry(tag="animal_ears", category="ears", weight=1.0),
        TagEntry(tag="animal_ear_fluff", category="ears", weight=1.0),
        TagEntry(tag="tail", category="body", weight=1.0),
        # 与 cat_ears 冲突的关联词，用于验证软关联追加时排除冲突。
        TagEntry(tag="dog_ears", category="ears", weight=1.0, conflicts=["cat_ears"]),
    ]
    store = TagStore(entries)
    assoc = AssociationStore(
        {
            "cat_ears": [
                {"tag": "animal_ears", "weight": 0.5},
                {"tag": "animal_ear_fluff", "weight": 0.4},
                {"tag": "dog_ears", "weight": 0.3},
            ],
            "skirt_lift": [{"tag": "tail", "weight": 0.2}],
        }
    )
    return PromptComposerPipeline(store=store, association_store=assoc)


class AutoAddTest(unittest.TestCase):
    def test_off_by_default(self):
        pipe = _make_pipeline()
        req = GenerationRequest(
            seed=1, fixed_tags=["skirt_lift", "cat_ears"], categories=[]
        )
        res = pipe.generate(req)
        sources = {t.source for t in res.selected_tags}
        self.assertNotIn("auto_related", sources)
        # requires 由约束层补 skirt，但来源不会是 auto_requires。
        self.assertNotIn("auto_requires", sources)

    def test_auto_add_requires(self):
        pipe = _make_pipeline()
        req = GenerationRequest(
            seed=1,
            fixed_tags=["skirt_lift"],
            categories=[],
            auto_add_requires=True,
        )
        res = pipe.generate(req)
        tags = {t.tag for t in res.selected_tags}
        self.assertIn("skirt", tags)

    def test_auto_add_related(self):
        pipe = _make_pipeline()
        req = GenerationRequest(
            seed=1,
            fixed_tags=["cat_ears"],
            categories=[],
            auto_add_related=True,
            auto_add_related_limit=3,
        )
        res = pipe.generate(req)
        tags = {t.tag for t in res.selected_tags}
        self.assertIn("animal_ears", tags)
        self.assertIn("animal_ear_fluff", tags)

    def test_auto_add_related_excludes_conflict(self):
        pipe = _make_pipeline()
        req = GenerationRequest(
            seed=1,
            fixed_tags=["cat_ears"],
            categories=[],
            auto_add_related=True,
            auto_add_related_limit=5,
        )
        res = pipe.generate(req)
        tags = {t.tag for t in res.selected_tags}
        # dog_ears 与已选 cat_ears 冲突，软关联追加时应被排除。
        self.assertNotIn("dog_ears", tags)

    def test_auto_add_related_no_recursion(self):
        # tail 是 skirt_lift 的关联，但 tail 自己的关联不应再展开。
        pipe = _make_pipeline()
        req = GenerationRequest(
            seed=1,
            fixed_tags=["skirt_lift"],
            categories=[],
            auto_add_related=True,
            auto_add_related_limit=3,
        )
        res = pipe.generate(req)
        tags = [t.tag for t in res.selected_tags]
        # tail 被补入一次即可，不做递归展开。
        self.assertIn("tail", tags)
        self.assertEqual(tags.count("tail"), 1)


if __name__ == "__main__":
    unittest.main()
