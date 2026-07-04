import unittest

from prompt_composer.core.negatives import build_negative, builtin_negatives_for


class BuiltinNegativesTest(unittest.TestCase):
    def test_general_returns_base(self):
        result = builtin_negatives_for("general")
        self.assertIn("lowres", result)
        # general 不含 explicit 组。
        self.assertNotIn("censored", result)

    def test_explicit_appends_group(self):
        result = builtin_negatives_for("explicit")
        self.assertIn("lowres", result)
        self.assertIn("censored", result)


class BuildNegativeTest(unittest.TestCase):
    def test_empty_when_all_off(self):
        result = build_negative(
            rating="general",
            use_builtin=False,
            user_negative=[],
            recycle_tags=[],
        )
        self.assertEqual(result, "")

    def test_builtin_only(self):
        result = build_negative(rating="general", use_builtin=True)
        self.assertIn("lowres", result)

    def test_user_negative_merged(self):
        result = build_negative(
            rating="general",
            use_builtin=False,
            user_negative=["my_bad_tag"],
        )
        self.assertEqual(result, "my_bad_tag")

    def test_dedup_case_insensitive(self):
        result = build_negative(
            rating="general",
            use_builtin=False,
            user_negative=["Bad", "bad", "worse"],
        )
        # 去重按小写比对，保留首次出现的原文。
        parts = [p.strip() for p in result.split(",")]
        self.assertEqual(parts, ["Bad", "worse"])

    def test_recycle_tags_included(self):
        result = build_negative(
            rating="general",
            use_builtin=False,
            user_negative=[],
            recycle_tags=["pants"],
        )
        self.assertEqual(result, "pants")


if __name__ == "__main__":
    unittest.main()
