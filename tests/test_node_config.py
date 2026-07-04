import json
import unittest

from prompt_composer.nodes.prompt_composer_node import (
    PromptComposerGenerateNode,
    _default_config_json,
)


class NodeConfigTest(unittest.TestCase):
    def setUp(self):
        self.node = PromptComposerGenerateNode()

    def test_inputs_are_seed_and_config(self):
        inputs = PromptComposerGenerateNode.INPUT_TYPES()["required"]
        self.assertEqual(set(inputs.keys()), {"seed", "config"})

    def test_returns_six_outputs(self):
        out = self.node.generate(1, _default_config_json())
        self.assertIn("ui", out)
        self.assertIn("result", out)
        self.assertEqual(len(out["result"]), 6)

    def test_negative_output_present(self):
        out = self.node.generate(1, _default_config_json())
        # 默认启用内置负面词，negative 位于 prompt 之后，非空串。
        self.assertIsInstance(out["result"][1], str)
        self.assertTrue(out["result"][1])

    def test_disable_builtin_negative_gives_empty(self):
        cfg = json.loads(_default_config_json())
        cfg["use_builtin_negative"] = False
        out = self.node.generate(1, json.dumps(cfg))
        self.assertEqual(out["result"][1], "")

    def test_weights_wrap_fixed_tag(self):
        cfg = json.loads(_default_config_json())
        cfg["weights"] = {"1girl": 1.2}
        out = self.node.generate(1, json.dumps(cfg))
        self.assertIn("(1girl:1.20)", out["result"][0])

    def test_empty_config_equals_default(self):
        a = self.node.generate(7, "")["result"][0]
        b = self.node.generate(7, _default_config_json())["result"][0]
        self.assertEqual(a, b)

    def test_bad_json_does_not_crash(self):
        out = self.node.generate(1, "{ not valid ]")
        self.assertTrue(out["result"][0])

    def test_manual_resolution_used(self):
        cfg = json.loads(_default_config_json())
        cfg["resolution_mode"] = "manual"
        cfg["manual_width"] = 1280
        cfg["manual_height"] = 720
        out = self.node.generate(1, json.dumps(cfg))
        self.assertEqual(out["result"][4], 1280)
        self.assertEqual(out["result"][5], 720)

    def test_manual_invalid_falls_back_to_infer(self):
        cfg = json.loads(_default_config_json())
        cfg["resolution_mode"] = "manual"
        cfg["manual_width"] = 0
        cfg["manual_height"] = 0
        out = self.node.generate(1, json.dumps(cfg))
        # 回退到推断值，宽高应为正整数。
        self.assertGreater(out["result"][4], 0)
        self.assertGreater(out["result"][5], 0)

    def test_invalid_mode_falls_back_to_auto(self):
        cfg = json.loads(_default_config_json())
        cfg["resolution_mode"] = "xxx"
        out = self.node.generate(1, json.dumps(cfg))
        self.assertGreater(out["result"][4], 0)
        self.assertGreater(out["result"][5], 0)

    def test_association_defaults(self):
        cfg = PromptComposerGenerateNode._parse_config("")
        self.assertFalse(cfg["association_boost"])
        self.assertEqual(cfg["association_strength"], 0.5)
        self.assertFalse(cfg["auto_add_requires"])
        self.assertFalse(cfg["auto_add_related"])

    def test_association_strength_invalid_falls_back(self):
        cfg = PromptComposerGenerateNode._parse_config(
            json.dumps({"association_strength": "abc"})
        )
        self.assertEqual(cfg["association_strength"], 0.5)

    def test_association_strength_clamped(self):
        high = PromptComposerGenerateNode._parse_config(
            json.dumps({"association_strength": 99})
        )
        self.assertEqual(high["association_strength"], 5.0)
        low = PromptComposerGenerateNode._parse_config(
            json.dumps({"association_strength": -3})
        )
        self.assertEqual(low["association_strength"], 0.0)

    def test_association_flags_parsed(self):
        cfg = PromptComposerGenerateNode._parse_config(
            json.dumps(
                {
                    "association_boost": True,
                    "auto_add_requires": True,
                    "auto_add_related":True,
                }
            )
        )
        self.assertTrue(cfg["association_boost"])
        self.assertTrue(cfg["auto_add_requires"])
        self.assertTrue(cfg["auto_add_related"])

    def test_default_generation_unchanged_with_new_fields(self):
        # 新字段默认关闭，默认 config 生成结果应可重复。
        a = self.node.generate(7, _default_config_json())["result"][0]
        b = self.node.generate(7, _default_config_json())["result"][0]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
