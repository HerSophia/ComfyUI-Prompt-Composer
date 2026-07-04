import random
import unittest

from prompt_composer.core.models import SamplingContext, TagEntry
from prompt_composer.core.sampler import RandomSampler, WeightedSampler


class SamplerTest(unittest.TestCase):
    def test_random_sampler_is_seed_stable(self):
        candidates = [TagEntry(tag="a", category="x"), TagEntry(tag="b", category="x")]
        context = SamplingContext(seed=123)
        first = RandomSampler().sample(candidates, context, random.Random(123))
        second = RandomSampler().sample(candidates, context, random.Random(123))
        self.assertEqual(first.tag, second.tag)

    def test_disabled_tag_is_filtered(self):
        candidates = [TagEntry(tag="a", category="x"), TagEntry(tag="b", category="x")]
        context = SamplingContext(seed=1, disabled_tags={"a"})
        result = RandomSampler().sample(candidates, context, random.Random(1))
        self.assertEqual(result.tag, "b")

    def test_weighted_sampler_ignores_zero_weight_when_possible(self):
        candidates = [
            TagEntry(tag="a", category="x", weight=0),
            TagEntry(tag="b", category="x", weight=10),
        ]
        context = SamplingContext(seed=1)
        result = WeightedSampler().sample(candidates, context, random.Random(1))
        self.assertEqual(result.tag, "b")


if __name__ == "__main__":
    unittest.main()
