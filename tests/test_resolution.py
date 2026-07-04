import unittest

from prompt_composer.core.resolution import infer_resolution


class ResolutionTest(unittest.TestCase):
    def test_portrait_shot_levels(self):
        # 竖向各景别档位。
        self.assertEqual(infer_resolution(["portrait"]), (1024, 1024))
        self.assertEqual(infer_resolution(["close-up"]), (1024, 1024))
        self.assertEqual(infer_resolution(["upper_body"]), (896, 1152))
        self.assertEqual(infer_resolution(["cowboy_shot"]), (832, 1216))
        self.assertEqual(infer_resolution(["full_shot"]), (768, 1344))
        self.assertEqual(infer_resolution(["foot_focus"]), (640, 1536))

    def test_no_shot_defaults_to_portrait_3_4(self):
        # 无景别标签时竖向默认 3:4。
        self.assertEqual(infer_resolution(["1girl", "solo"]), (896, 1152))

    def test_multiple_shots_take_tallest(self):
        # 同时命中多个景别时取最竖长的一档。
        self.assertEqual(infer_resolution(["close-up", "full_shot"]), (768, 1344))
        self.assertEqual(infer_resolution(["upper_body", "foot_focus"]), (640, 1536))

    def test_landscape_signal_scenery(self):
        # 风景信号触发横向，无景别时默认 16:9。
        self.assertEqual(infer_resolution(["scenery"]), (1344, 768))

    def test_landscape_signal_multiple_girls(self):
        # 多人群像触发横向，上半身档取 4:3。
        self.assertEqual(infer_resolution(["multiple_girls", "upper_body"]), (1152, 896))

    def test_landscape_shot_levels(self):
        # 横向各景别档位。
        self.assertEqual(infer_resolution(["scenery", "portrait"]), (1024, 1024))
        self.assertEqual(infer_resolution(["scenery", "cowboy_shot"]), (1216, 832))
        self.assertEqual(infer_resolution(["scenery", "full_shot"]), (1344, 768))
        self.assertEqual(infer_resolution(["scenery", "foot_focus"]), (1536, 640))

    def test_empty_input(self):
        # 空输入回退竖向默认。
        self.assertEqual(infer_resolution([]), (896, 1152))

    def test_case_insensitive(self):
        # 标签大小写与空白不敏感。
        self.assertEqual(infer_resolution([" Portrait "]), (1024, 1024))


if __name__ == "__main__":
    unittest.main()
