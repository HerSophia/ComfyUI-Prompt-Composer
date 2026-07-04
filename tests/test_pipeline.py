import unittest

from prompt_composer.core import GenerationRequest, PromptComposerPipeline


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = PromptComposerPipeline()

    def test_pipeline_generates_prompt_and_ast(self):
        request = GenerationRequest(seed=42, fixed_tags=["1girl"])
        response = self.pipeline.generate(request)
        self.assertTrue(response.prompt)
        self.assertTrue(response.ast.to_dict()["meta"]["source_tags"])
        self.assertIsInstance(response.features, dict)

    def test_pipeline_is_seed_stable(self):
        request = GenerationRequest(seed=7, fixed_tags=["1girl"])
        first = self.pipeline.generate(request).prompt
        second = self.pipeline.generate(request).prompt
        self.assertEqual(first, second)

    def test_pipeline_requires_flow_can_be_forced(self):
        request = GenerationRequest(
            seed=1,
            categories=[],
            random_categories=[],
            fixed_tags=["skirt_lift"],
            disabled_tags=[],
        )
        response = self.pipeline.generate(request)
        tags = {entry.tag for entry in response.selected_tags}
        self.assertIn("skirt_lift", tags)
        self.assertIn("skirt", tags)


if __name__ == "__main__":
    unittest.main()
