import random
import unittest

from prompt_composer.core.models import SamplingContext, TagEntry
from prompt_composer.core.sampler import WeightedSampler, _boost_factor


def _lookup(mapping):
    return lambda tag: mapping.get(tag, {})


class SamplerBoostTest(unittest.TestCase):
    def test_boost_factor_raises_above_one(self):
        ctx = SamplingContext(
            association_boost=True,
            association_strength=0.5,
            selected_tags={"long_hair"},
            association_lookup=_lookup({"long_hair": {"blue_eyes": 0.5}}),
            conflict_lookup=lambda t: set(),
        )
        entry = TagEntry(tag="blue_eyes", category="eyes", weight=1.0)
        self.assertGreater(_boost_factor(entry, ctx), 1.0)

    def test_boost_off_returns_one(self):
        ctx = SamplingContext(
            association_boost=False,
            association_strength=0.5,
            selected_tags={"long_hair"},
            association_lookup=_lookup({"long_hair": {"blue_eyes": 0.5}}),
        )
        entry = TagEntry(tag="blue_eyes", category="eyes", weight=1.0)
        self.assertEqual(_boost_factor(entry, ctx), 1.0)

    def test_zero_strength_equals_off(self):
        ctx = SamplingContext(
            association_boost=True,
            association_strength=0.0,
            selected_tags={"long_hair"},
            association_lookup=_lookup({"long_hair": {"blue_eyes": 0.5}}),
        )
        entry = TagEntry(tag="blue_eyes", category="eyes", weight=1.0)
        self.assertEqual(_boost_factor(entry, ctx), 1.0)

    def test_conflict_not_boosted(self):
        ctx = SamplingContext(
            association_boost=True,
            association_strength=0.5,
            selected_tags={"long_hair"},
            association_lookup=_lookup({"long_hair": {"blue_eyes": 0.5}}),
            conflict_lookup=lambda t: {"long_hair"} if t == "blue_eyes" else set(),
        )
        entry = TagEntry(tag="blue_eyes", category="eyes", weight=1.0)
        self.assertEqual(_boost_factor(entry, ctx), 1.0)

    def test_boost_factor_upper_bound(self):
        # 强关联叠加高强度时，因子仍受上限约束。
        ctx = SamplingContext(
            association_boost=True,
            association_strength=5.0,
            selected_tags={"a", "b", "c"},
            association_lookup=_lookup(
                {"a": {"x": 1.0}, "b": {"x": 1.0}, "c": {"x": 1.0}}
            ),
            conflict_lookup=lambda t: set(),
        )
        entry = TagEntry(tag="x", category="cat", weight=1.0)
        self.assertLessEqual(_boost_factor(entry, ctx), 4.0)

    def test_sampler_off_matches_plain_weighted(self):
        # 关闭加成时，采样分布应与按权重一致。
        candidates = [
            TagEntry(tag="a", category="x", weight=1.0),
            TagEntry(tag="b", category="x", weight=3.0),
        ]
        ctx = SamplingContext()  # 默认关闭
        counts = {"a": 0, "b": 0}
        sampler = WeightedSampler()
        for i in range(20000):
            r = sampler.sample(candidates, ctx, random.Random(i))
            counts[r.tag] += 1
        ratio = counts["b"] / counts["a"]
        self.assertTrue(2.6 < ratio < 3.4)


if __name__ == "__main__":
    unittest.main()
