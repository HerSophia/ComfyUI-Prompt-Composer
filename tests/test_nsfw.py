import random
import unittest

from prompt_composer.core import GenerationRequest, PromptComposerPipeline
from prompt_composer.core.models import SamplingContext, TagEntry
from prompt_composer.core.sampler import RandomSampler
from prompt_composer.core.pipeline import load_default_store


NSFW_CATEGORIES = ("nsfw_act", "nsfw_body", "nsfw_gear")


class SamplerRatingTest(unittest.TestCase):
    def test_general_context_filters_explicit_tag(self):
        candidates = [
            TagEntry(tag="a", category="x", rating="general"),
            TagEntry(tag="b", category="x", rating="explicit"),
        ]
        context = SamplingContext(seed=1, rating="general")
        # explicit 被过滤，只可能取到 a
        for seed in range(10):
            result = RandomSampler().sample(candidates, context, random.Random(seed))
            self.assertEqual(result.tag, "a")

    def test_explicit_context_allows_explicit_tag(self):
        candidates = [TagEntry(tag="b", category="x", rating="explicit")]
        context = SamplingContext(seed=1, rating="explicit")
        result = RandomSampler().sample(candidates, context, random.Random(1))
        self.assertEqual(result.tag, "b")


class RequestRatingTest(unittest.TestCase):
    def test_general_effective_categories_drop_nsfw(self):
        req = GenerationRequest(
            rating="general",
            random_categories=["hair", "nsfw_act", "nsfw_body"],
        )
        cats = req.effective_categories()
        self.assertIn("hair", cats)
        self.assertNotIn("nsfw_act", cats)
        self.assertNotIn("nsfw_body", cats)

    def test_explicit_effective_categories_keep_nsfw(self):
        req = GenerationRequest(
            rating="explicit",
            random_categories=["hair", "nsfw_act"],
        )
        cats = req.effective_categories()
        self.assertIn("nsfw_act", cats)


class NsfwDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = load_default_store()

    def test_nsfw_categories_exist(self):
        categories = set(self.store.categories())
        for cat in NSFW_CATEGORIES:
            self.assertIn(cat, categories)

    def test_all_nsfw_tags_are_explicit(self):
        for cat in NSFW_CATEGORIES:
            for entry in self.store.by_category(cat):
                self.assertEqual(entry.rating, "explicit", f"{entry.tag} 应为 explicit")

    def test_normal_tags_are_general(self):
        for entry in self.store.by_category("hair"):
            self.assertEqual(entry.rating, "general")


class PipelineRatingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = PromptComposerPipeline()

    def _has_explicit(self, response):
        return any(t.rating == "explicit" for t in response.selected_tags)

    def test_general_default_has_no_explicit(self):
        req = GenerationRequest(
            seed=1,
            fixed_tags=["1girl"],
            random_categories=["hair", "eyes", "clothing", "pose"],
        )
        resp = self.pipeline.generate(req)
        self.assertFalse(self._has_explicit(resp))

    def test_general_ignores_forced_nsfw_categories(self):
        req = GenerationRequest(
            seed=1,
            fixed_tags=["1girl"],
            random_categories=["hair", "nsfw_act", "nsfw_body"],
        )
        resp = self.pipeline.generate(req)
        self.assertFalse(self._has_explicit(resp))

    def test_explicit_produces_explicit_tags(self):
        req = GenerationRequest(
            seed=1,
            rating="explicit",
            fixed_tags=["1girl"],
            random_categories=["hair", "eyes", "clothing", "pose"],
        )
        resp = self.pipeline.generate(req)
        self.assertTrue(self._has_explicit(resp))

    def test_default_behavior_unchanged_without_rating(self):
        # 不传 rating，默认 general，行为与旧版一致（不含 explicit）
        req = GenerationRequest(seed=42, fixed_tags=["1girl"])
        resp = self.pipeline.generate(req)
        self.assertFalse(self._has_explicit(resp))


class NsfwConstraintTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = PromptComposerPipeline()

    def test_sex_positions_are_mutually_exclusive(self):
        req = GenerationRequest(
            seed=3,
            rating="explicit",
            fixed_tags=["1girl", "missionary", "doggystyle", "cowgirl_position"],
            random_categories=[],
        )
        resp = self.pipeline.generate(req)
        positions = [
            t.tag
            for t in resp.selected_tags
            if t.tag in ("missionary", "doggystyle", "cowgirl_position")
        ]
        self.assertEqual(len(positions), 1)

    def test_deepthroat_requires_fellatio(self):
        req = GenerationRequest(
            seed=3,
            rating="explicit",
            fixed_tags=["1girl", "deepthroat"],
            random_categories=[],
        )
        resp = self.pipeline.generate(req)
        tags = {t.tag for t in resp.selected_tags}
        self.assertIn("deepthroat", tags)
        self.assertIn("fellatio", tags)


if __name__ == "__main__":
    unittest.main()
