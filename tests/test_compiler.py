import unittest

from prompt_composer.core.ast_builder import ASTBuilder
from prompt_composer.core.compiler import DanbooruCompiler
from prompt_composer.core.models import TagEntry


class CompilerTest(unittest.TestCase):
    def test_danbooru_compiler_order_and_dedup(self):
        tags = [
            TagEntry(tag="standing", category="pose"),
            TagEntry(tag="dress", category="clothing"),
            TagEntry(tag="smile", category="expression"),
            TagEntry(tag="standing", category="pose"),
        ]
        ast = ASTBuilder().build(tags, {}, [])
        prompt = DanbooruCompiler().compile(ast)
        self.assertEqual(prompt, "dress, smile, standing")

    def test_empty_ast_outputs_empty_string(self):
        ast = ASTBuilder().build([], {}, [])
        self.assertEqual(DanbooruCompiler().compile(ast), "")


if __name__ == "__main__":
    unittest.main()
