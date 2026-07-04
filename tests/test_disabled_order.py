import unittest

from prompt_composer.core.association_store import AssociationStore
from prompt_composer.core.models import GenerationRequest, TagEntry
from prompt_composer.core.pipeline import PromptComposerPipeline
from prompt_composer.core.tag_store import TagStore


def _make_pipeline():
    # 一组自足的标签，用于验证禁用过滤在联想之前生效。
    entries = [
        TagEntry(tag="cat_ears", category="ears", weight=1.0),
        TagEntry(tag="animal_ears", category="ears", weight=1.0),
        TagEntry(tag="animal_ear_fluff", category="ears", weight=1.0),
        TagEntry(tag="skirt_lift", category="pose", weight=1.0, requires=["skirt"]),
        TagEntry(tag="skirt", category="clothing", weight=1.0),
    ]
    store = TagStore(entries)
    assoc = AssociationStore(
        {
            "cat_ears": [
                {"tag": "animal_ears", "weight": 0.5},
                {"tag": "animal_ear_fluff", "weight": 0.4},
            ],
        }
    )
    return PromptComposerPipeline(store=store, association_store=assoc)


class DisabledOrderTest(unittest.TestCase):
    def test_related_does_not_bring_back_disabled(self):
        # 顺序：先随机、再禁用、最后联想。
        # animal_ears 被禁用后，即便是 cat_ears 的关联词也不应被追加回来。
        pipe = _make_pipeline()
        req = GenerationRequest(
            seed=1,
            fixed_tags=["cat_ears"],
            categories=[],
            disabled_tags=["animal_ears"],
            auto_add_related=True,
            auto_add_related_limit=3,
        )
        res = pipe.generate(req)
        tags = {t.tag for t in res.selected_tags}
        self.assertNotIn("animal_ears", tags)
        # 未被禁用的关联词仍应正常追加。
        self.assertIn("animal_ear_fluff", tags)

    def test_requires_does_not_bring_back_disabled(self):
        # skirt 被禁用后，即便是 skirt_lift 的硬依赖也不应被自动追加回来。
        pipe = _make_pipeline()
        req = GenerationRequest(
            seed=1,
            fixed_tags=["skirt_lift"],
            categories=[],
            disabled_tags=["skirt"],
            auto_add_requires=True,
        )
        res = pipe.generate(req)
        auto_sources = {
          t.tag for t in res.selected_tags if t.source == "auto_requires"
        }
        self.assertNotIn("skirt", auto_sources)

    def test_disabled_removes_sampled_source(self):
        # 采样得到的非固定标签命中禁用集合时应被清除。
        pipe = _make_pipeline()
        req = GenerationRequest(
            seed=1,
            categories=["ears"],
            disabled_tags=["cat_ears", "animal_ears", "animal_ear_fluff"],
        )
        res = pipe.generate(req)
        tags = {t.tag for t in res.selected_tags}
        self.assertNotIn("cat_ears", tags)
        self.assertNotIn("animal_ears", tags)
        self.assertNotIn("animal_ear_fluff", tags)

    def test_fixed_tag_survives_disable(self):
        # 用户既固定又禁用同一标签时，显式指定优先，固定标签保留。
        pipe = _make_pipeline()
        req = GenerationRequest(
            seed=1,
            fixed_tags=["cat_ears"],
            categories=[],
            disabled_tags=["cat_ears"],
        )
        res = pipe.generate(req)
        tags = {t.tag for t in res.selected_tags}
        self.assertIn("cat_ears", tags)


if __name__ == "__main__":
    unittest.main()
