import unittest

from prompt_composer.core.ast_builder import ASTBuilder
from prompt_composer.core.models import LogEntry, TagEntry


class ASTBuilderTest(unittest.TestCase):
    def test_ast_builder_places_tags_in_expected_paths(self):
        tags = [
            TagEntry(tag="dress", category="clothing"),
            TagEntry(tag="standing", category="pose"),
            TagEntry(tag="waving", category="hand"),
            TagEntry(tag="outdoors", category="background"),
        ]
        ast = ASTBuilder().build(tags, {"body_state": "standing"}, [LogEntry("info", "X", "ok")])
        data = ast.to_dict()
        self.assertEqual(data["character"]["clothing"][0]["value"], "dress")
        self.assertEqual(data["pose"]["body"][0]["value"], "standing")
        self.assertEqual(data["pose"]["hand"][0]["value"], "waving")
        self.assertEqual(data["environment"]["background"][0]["value"], "outdoors")
        self.assertEqual(data["meta"]["features"]["body_state"], "standing")


if __name__ == "__main__":
    unittest.main()
