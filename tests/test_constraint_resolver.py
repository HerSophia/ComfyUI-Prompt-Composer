import unittest

from prompt_composer.core.constraint_resolver import ConstraintResolver
from prompt_composer.core.models import TagEntry
from prompt_composer.core.pipeline import load_default_store


class ConstraintResolverTest(unittest.TestCase):
    def setUp(self):
        self.store = load_default_store()

    def test_requires_adds_skirt_for_skirt_lift(self):
        sl = self.store.find("skirt_lift").clone(order=0)
        resolved, features, logs, _discarded = ConstraintResolver(self.store).resolve([sl], [])
        tags = {entry.tag for entry in resolved}
        self.assertIn("skirt_lift", tags)
        self.assertIn("skirt", tags)
        self.assertTrue(any(log.code == "REQUIRES_ADDED" for log in logs))

    def test_conflict_keeps_higher_priority(self):
        dress = self.store.find("dress").clone(order=0)
        pants = self.store.find("pants").clone(order=1)
        resolved, features, logs, discarded = ConstraintResolver(self.store).resolve(
            [dress, pants], []
        )
        tags = {entry.tag for entry in resolved}
        self.assertIn("dress", tags)
        self.assertNotIn("pants", tags)
        self.assertTrue(any(log.code == "CONFLICT_REMOVED" for log in logs))
        # 被淘汰的 pants 应记入淘汰列表。
        self.assertIn("pants", discarded)

    def test_fixed_tag_has_priority_over_random_conflict(self):
        dress = self.store.find("dress").clone(source="sampled", order=0)
        pants = self.store.find("pants").clone(source="fixed", order=1)
        resolved, features, logs, _discarded = ConstraintResolver(self.store).resolve(
            [dress, pants], ["pants"]
        )
        tags = {entry.tag for entry in resolved}
        self.assertIn("pants", tags)
        self.assertNotIn("dress", tags)

    def test_feature_conflict_prefers_higher_priority(self):
        # portrait(legs_visible=false, priority 12) 与 standing(legs_visible=true, priority 8)
        portrait = self.store.find("portrait").clone(order=0)
        standing = self.store.find("standing").clone(order=1)
        resolved, features, logs, _discarded = ConstraintResolver(self.store).resolve(
            [portrait, standing], []
        )
        tags = {entry.tag for entry in resolved}
        self.assertIn("portrait", tags)
        self.assertNotIn("standing", tags)
        self.assertIs(features["legs_visible"], False)


if __name__ == "__main__":
    unittest.main()
