import unittest

from prompt_composer.core import GenerationRequest, PromptComposerPipeline
from prompt_composer.core.identity_resolver import IdentityResolver
from prompt_composer.core.identity_store import IdentityStore
from prompt_composer.core.models import Identity
from prompt_composer.core.pipeline import (
    load_default_identity_store,
    load_default_store,
)


class IdentityResolverTest(unittest.TestCase):
    def setUp(self):
        self.store = load_default_store()

    def test_resolve_expands_tags_and_locked_features(self):
        identity = Identity.from_dict(
            {
                "id": "demo",
                "identity_tags": ["demo_char"],
                "locked_features": {"hair_color": "aqua"},
                "default_tags": {"hair": ["twintails"]},
            }
        )
        tags, logs = IdentityResolver(self.store).resolve(identity)
        names = {t.tag for t in tags}
        self.assertIn("demo_char", names)
        self.assertIn("twintails", names)
        # locked_features 挂在主 identity_tag 上。
        main = next(t for t in tags if t.tag == "demo_char")
        self.assertEqual(main.features.get("hair_color"), "aqua")
        #展开的 tag 都是 fixed。
        self.assertTrue(all(t.source == "fixed" for t in tags))


class IdentityStoreTest(unittest.TestCase):
    def test_default_identities_loaded(self):
        store = load_default_identity_store()
        self.assertIn("hatsune_miku", store.ids())


class DerivativePipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = PromptComposerPipeline()

    def test_identity_tags_are_kept(self):
        request = GenerationRequest(
            seed=1,
            fixed_tags=["1girl"],
            identity="hatsune_miku",
            lock_categories=["hair", "eyes", "clothing"],
            random_categories=["pose", "expression", "camera", "background"],
        )
        response = self.pipeline.generate(request)
        tags = {t.tag for t in response.selected_tags}
        self.assertIn("hatsune_miku", tags)
        self.assertIn("aqua_hair", tags)
        self.assertIn("aqua_eyes", tags)

    def test_locked_categories_not_randomized(self):
        # 锁定 hair 时，随机不应再从 hair 分类取样。
        request = GenerationRequest(
            seed=1,
            identity="hatsune_miku",
            lock_categories=["hair", "eyes", "clothing"],
            random_categories=["hair", "pose"],
        )
        cats = request.effective_categories()
        self.assertNotIn("hair", cats)
        self.assertIn("pose", cats)

    def test_missing_identity_logs_warning(self):
        request = GenerationRequest(seed=1, identity="no_such_char")
        response = self.pipeline.generate(request)
        self.assertTrue(any(log.code == "IDENTITY_NOT_FOUND" for log in response.logs))


if __name__ == "__main__":
    unittest.main()
