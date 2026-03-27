import unittest
from unittest.mock import MagicMock, patch

from app.rag.pipeline import RAGPipeline


class RAGPipelineTests(unittest.TestCase):
    def setUp(self):
        retriever_patcher = patch("app.rag.pipeline.Retriever")
        prompt_patcher = patch("app.rag.pipeline.PromptBuilder")
        llm_patcher = patch("app.rag.pipeline.LLM")

        self.addCleanup(retriever_patcher.stop)
        self.addCleanup(prompt_patcher.stop)
        self.addCleanup(llm_patcher.stop)

        self.mock_retriever_cls = retriever_patcher.start()
        self.mock_prompt_cls = prompt_patcher.start()
        self.mock_llm_cls = llm_patcher.start()

        self.mock_retriever = self.mock_retriever_cls.return_value
        self.mock_prompt = self.mock_prompt_cls.return_value
        self.mock_llm = self.mock_llm_cls.return_value

        self.mock_retriever.retrieve.return_value = (
            {"collection": "kinexushhd", "app": "KINEXUSHHD", "routing": {}},
            [{"text": "Therapy Gap info", "section": "Clinic Dashboard", "page": 23}],
        )
        self.mock_prompt.build.return_value = "prompt"
        self.mock_llm.generate.return_value = "Detailed answer."

        self.pipeline = RAGPipeline()

    def test_source_specific_detail_follow_up_is_normalized_for_retrieval(self):
        query = 'Please provide a detailed walkthrough from the documents for "Clinic Dashboard".'
        history = [{"role": "user", "text": "What is therapy gap?"}]

        self.pipeline.run(query, history=history, where=None)

        self.mock_retriever.retrieve.assert_called_once_with(
            "What is therapy gap?\nPlease provide a detailed walkthrough from the documents.",
            history=history,
            where=None,
            top_k=self.pipeline._detailed_top_k,
        )

    def test_source_specific_visual_follow_up_is_normalized_for_retrieval(self):
        query = 'Please show reference images for "Clinic Dashboard".'
        history = [{"role": "user", "text": "What is therapy gap?"}]

        self.pipeline.run(query, history=history, where=None)

        self.mock_retriever.retrieve.assert_called_once_with(
            "What is therapy gap?\nPlease show reference images related to this answer.",
            history=history,
            where=None,
            top_k=None,
        )

    def test_clean_fallback_text_strips_chunk_metadata_labels(self):
        cleaned = self.pipeline._clean_fallback_text(
            "Treatment Flowsheet Domain: patient Type: text "
            "Keywords: flowsheet, treatment Image path: images/page_46_fig_1.png"
        )

        self.assertEqual(cleaned, "Treatment Flowsheet")


if __name__ == "__main__":
    unittest.main()
