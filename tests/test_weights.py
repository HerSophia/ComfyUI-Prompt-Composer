import unittest

from prompt_composer.core.ast_builder import ASTBuilder
from prompt_composer.core.compiler import DanbooruCompiler, format_weighted_tag
from prompt_composer.core.models import TagEntry


class FormatWeightedTagTest(unittest.TestCase):
    def test_weight_wraps_tag(self):
        self.assertEqual(format_weighted_tag("1girl", 1.2), "(1girl:1.20)")

    def test_weight_one_no_wrap(self):
        self.assertEqual(format_weighted_tag("smile", 1.0), "smile")

    def test_weight_below_range_clamped(self):
        # 低于 0.6 截断到 0.6。
        self.assertEqual(format_weighted_tag("blush", 0.1), "(blush:0.60)")

    def test_weight_above_range_clamped(self):
        # 高于 1.5 截断到 1.5。
        self.assertEqual(format_weighted_tag("detailed", 3.0), "(detailed:1.50)")

    def test_parentheses_escaped(self):
        result = format_weighted_tag("artoria_pendragon_(fate)", 1.2)
        self.assertEqual(result, "(artoria_pendragon_\\(fate\\):1.20)")

    def test_invalid_weight_returns_tag(self):
        self.assertEqual(format_weighted_tag("smile", "abc"), "smile")


class CompilerWeightTest(unittest.TestCase):
    def _build_ast(self):
        tags = [
            TagEntry(tag="1girl", category="character"),
            TagEntry(tag="smile", category="expression"),
            TagEntry(tag="dress", category="clothing"),
        ]
        return ASTBuilder().build(tags, {}, [])

    def test_compiler_applies_weight(self):
        ast = self._build_ast()
        prompt = DanbooruCompiler({"1girl": 1.2}).compile(ast)
        self.assertIn("(1girl:1.20)", prompt)
        # 未命中权重的标签保持原样。
        self.assertIn("smile", prompt)
        self.assertNotIn("(smile",prompt)

    def test_compiler_no_weights_unchanged(self):
        ast = self._build_ast()
        plain = DanbooruCompiler().compile(ast)
        self.assertNotIn("(", plain)

    def test_weight_key_case_insensitive(self):
        ast = self._build_ast()
        prompt = DanbooruCompiler({"1GIRL": 1.3}).compile(ast)
        self.assertIn("(1girl:1.30)", prompt)


if __name__ == "__main__":
    unittest.main()
