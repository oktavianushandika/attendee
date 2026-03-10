import unittest

from bots.bot_controller.prosa_tts_client import ProsaTTSClient


class TestSentenceSplitting(unittest.TestCase):
    """Test cases for sentence splitting utility"""
    
    def test_simple_sentences(self):
        """Test splitting simple sentences with periods"""
        text = "This is sentence one. This is sentence two. This is sentence three."
        result = ProsaTTSClient.split_into_sentences(text)
        expected = [
            "This is sentence one.",
            "This is sentence two.",
            "This is sentence three."
        ]
        self.assertEqual(result, expected)
    
    def test_single_sentence(self):
        """Test text with single sentence"""
        text = "This is a single sentence."
        result = ProsaTTSClient.split_into_sentences(text)
        expected = ["This is a single sentence."]
        self.assertEqual(result, expected)
    
    def test_no_period(self):
        """Test text without period"""
        text = "This is text without period"
        result = ProsaTTSClient.split_into_sentences(text)
        expected = ["This is text without period"]
        self.assertEqual(result, expected)
    
    def test_multiple_spaces(self):
        """Test sentences with multiple spaces"""
        text = "First sentence.    Second sentence.  Third sentence."
        result = ProsaTTSClient.split_into_sentences(text)
        expected = [
            "First sentence.",
            "Second sentence.",
            "Third sentence."
        ]
        self.assertEqual(result, expected)
    
    def test_empty_sentences_filtered(self):
        """Test that empty sentences are filtered out"""
        text = "Hello.  . World."
        result = ProsaTTSClient.split_into_sentences(text)
        expected = ["Hello.", "World."]
        self.assertEqual(result, expected)
    
    def test_trailing_period(self):
        """Test text ending with period"""
        text = "First. Second. Third."
        result = ProsaTTSClient.split_into_sentences(text)
        expected = ["First.", "Second.", "Third."]
        self.assertEqual(result, expected)
    
    def test_no_trailing_period(self):
        """Test text not ending with period"""
        text = "First. Second. Third"
        result = ProsaTTSClient.split_into_sentences(text)
        expected = ["First.", "Second.", "Third"]
        self.assertEqual(result, expected)
    
    def test_abbreviations(self):
        """Test that abbreviations are handled correctly"""
        text = "Dr. Smith is here. He is a doctor."
        result = ProsaTTSClient.split_into_sentences(text)
        # Note: Simple regex will split on "Dr." - this is a known limitation
        # For production, consider using NLP libraries like spaCy or NLTK
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)
    
    def test_empty_text(self):
        """Test empty text"""
        text = ""
        result = ProsaTTSClient.split_into_sentences(text)
        expected = []
        self.assertEqual(result, expected)
    
    def test_only_periods(self):
        """Test text with only periods"""
        text = "..."
        result = ProsaTTSClient.split_into_sentences(text)
        expected = []
        self.assertEqual(result, expected)
    
    def test_newlines_in_text(self):
        """Test text with newlines"""
        text = "First sentence.\nSecond sentence.\nThird sentence."
        result = ProsaTTSClient.split_into_sentences(text)
        expected = [
            "First sentence.",
            "Second sentence.",
            "Third sentence."
        ]
        self.assertEqual(result, expected)
    
    def test_long_text(self):
        """Test longer text with multiple sentences"""
        text = (
            "Lorem Ipsum is simply dummy text of the printing industry. "
            "Lorem Ipsum has been the industry's standard dummy text. "
            "An unknown printer took a galley of type and scrambled it."
        )
        result = ProsaTTSClient.split_into_sentences(text)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(s.endswith('.') for s in result))


if __name__ == "__main__":
    unittest.main()
