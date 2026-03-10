import os
import unittest
from unittest.mock import MagicMock, patch, Mock

from bots.bot_controller.conversation_manager import (
    ConversationManager,
    TriggerPhraseDetector,
    QueryCaptureBuffer,
)
from bots.bot_controller.llm_client import LLMClient
from bots.bot_controller.prosa_tts_client import ProsaTTSClient


class TestTriggerPhraseDetector(unittest.TestCase):
    def setUp(self):
        self.detector = TriggerPhraseDetector(["hi pamela", "hey pamela", "hai pamela"])

    def test_detect_trigger_phrase_hi(self):
        result = self.detector.detect("Hi Pamela, what's the weather?")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "hi pamela")
        self.assertEqual(result[1], "what's the weather?")

    def test_detect_trigger_phrase_hey(self):
        result = self.detector.detect("Hey Pamela tell me a joke")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "hey pamela")
        self.assertEqual(result[1], "tell me a joke")

    def test_detect_trigger_phrase_hai(self):
        result = self.detector.detect("Hai Pamela how are you")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "hai pamela")
        self.assertEqual(result[1], "how are you")

    def test_no_trigger_phrase(self):
        result = self.detector.detect("Hello everyone, how are you?")
        self.assertIsNone(result)

    def test_case_insensitive(self):
        result = self.detector.detect("HI PAMELA what's up")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "hi pamela")

    def test_trigger_phrase_only(self):
        result = self.detector.detect("Hi Pamela")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "hi pamela")
        self.assertEqual(result[1], "")


class TestQueryCaptureBuffer(unittest.TestCase):
    def setUp(self):
        self.buffer = QueryCaptureBuffer(timeout_seconds=2.5)

    def test_start_capture(self):
        self.buffer.start_capture("initial text", "participant_1", "hi pamela")
        self.assertTrue(self.buffer.state.is_capturing)
        self.assertEqual(self.buffer.state.query_text, "initial text")
        self.assertEqual(self.buffer.state.participant_id, "participant_1")

    def test_append_text(self):
        self.buffer.start_capture("hello", "participant_1", "hi pamela")
        result = self.buffer.append_text("world", "participant_1")
        self.assertTrue(result)
        self.assertEqual(self.buffer.state.query_text, "hello world")

    def test_get_query(self):
        self.buffer.start_capture("test query", "participant_1", "hi pamela")
        query = self.buffer.get_query()
        self.assertEqual(query, "test query")
        self.assertFalse(self.buffer.state.is_capturing)

    def test_timeout_not_reached(self):
        self.buffer.start_capture("test", "participant_1", "hi pamela")
        self.assertFalse(self.buffer.is_timeout_reached())

    def test_reset(self):
        self.buffer.start_capture("test", "participant_1", "hi pamela")
        self.buffer.reset()
        self.assertFalse(self.buffer.state.is_capturing)
        self.assertEqual(self.buffer.state.query_text, "")


class TestLLMClient(unittest.TestCase):
    def setUp(self):
        os.environ["LLM_BASE_URL"] = "https://test-llm.com/api"
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["LLM_CHATBOT_ID"] = "test-chatbot"
        os.environ["LLM_AGENT_ID"] = "test-agent"
        self.client = LLMClient()

    def test_is_configured(self):
        self.assertTrue(self.client.is_configured())

    def test_not_configured_without_api_key(self):
        del os.environ["LLM_API_KEY"]
        client = LLMClient()
        self.assertFalse(client.is_configured())
        os.environ["LLM_API_KEY"] = "test-key"

    @patch("bots.bot_controller.llm_client.requests.post")
    def test_get_response_success(self, mock_post):
        # Mock SSE response
        mock_response = Mock()
        mock_response.iter_lines.return_value = [
            'data: {"status": "processing"}',
            'data: {"status": "response", "message": "Test response"}',
        ]
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = self.client.get_response("test query")
        self.assertEqual(result, "Test response")

    @patch("bots.bot_controller.llm_client.requests.post")
    def test_get_response_timeout(self, mock_post):
        mock_post.side_effect = Exception("Timeout")
        result = self.client.get_response("test query")
        self.assertIsNone(result)


class TestProsaTTSClient(unittest.TestCase):
    def setUp(self):
        os.environ["TTS_BASE_URL"] = "https://test-tts.com"
        os.environ["TTS_API_KEY"] = "test-tts-key"
        self.client = ProsaTTSClient()

    def test_is_configured(self):
        self.assertTrue(self.client.is_configured())

    def test_not_configured_without_api_key(self):
        del os.environ["TTS_API_KEY"]
        client = ProsaTTSClient()
        self.assertFalse(client.is_configured())
        os.environ["TTS_API_KEY"] = "test-tts-key"

    @patch("bots.bot_controller.prosa_tts_client.requests.post")
    def test_submit_tts_job_success(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"job_id": "test-job-123"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        job_id = self.client._submit_tts_job("test text")
        self.assertEqual(job_id, "test-job-123")

    @patch("bots.bot_controller.prosa_tts_client.requests.get")
    def test_poll_job_status_complete(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "complete",
            "result": {"path": "https://test.com/audio.mp3"},
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        audio_url = self.client._poll_job_status("test-job-123")
        self.assertEqual(audio_url, "https://test.com/audio.mp3")

    @patch("bots.bot_controller.prosa_tts_client.requests.get")
    def test_download_audio_success(self, mock_get):
        mock_response = Mock()
        mock_response.content = b"fake audio data"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        audio_bytes = self.client._download_audio("https://test.com/audio.mp3")
        self.assertEqual(audio_bytes, b"fake audio data")


class TestConversationManager(unittest.TestCase):
    def setUp(self):
        os.environ["CONVERSATION_ENABLED"] = "true"
        os.environ["CONVERSATION_TRIGGER_PHRASES"] = "hi pamela,hey pamela"
        os.environ["CONVERSATION_QUERY_TIMEOUT_SECONDS"] = "2.5"

        self.mock_llm_client = MagicMock()
        self.mock_tts_client = MagicMock()
        self.mock_play_audio = MagicMock()
        self.mock_get_participant = MagicMock()

        self.manager = ConversationManager(
            llm_client=self.mock_llm_client,
            tts_client=self.mock_tts_client,
            play_audio_callback=self.mock_play_audio,
            get_participant_callback=self.mock_get_participant,
        )

    def test_initialization(self):
        self.assertTrue(self.manager.enabled)
        self.assertEqual(len(self.manager.trigger_phrases), 2)
        self.assertIn("hi pamela", self.manager.trigger_phrases)

    def test_process_utterance_with_trigger(self):
        self.mock_llm_client.is_configured.return_value = True
        self.mock_tts_client.is_configured.return_value = True

        utterance = {
            "text": "Hi Pamela, what's the weather?",
            "participant_id": "participant_1",
            "participant_name": "John Doe",
        }

        self.manager.process_utterance(utterance)
        self.assertTrue(self.manager.query_buffer.state.is_capturing)

    def test_process_utterance_without_trigger(self):
        self.mock_llm_client.is_configured.return_value = True
        self.mock_tts_client.is_configured.return_value = True

        utterance = {
            "text": "Hello everyone",
            "participant_id": "participant_1",
            "participant_name": "John Doe",
        }

        self.manager.process_utterance(utterance)
        self.assertFalse(self.manager.query_buffer.state.is_capturing)

    def test_disabled_conversation(self):
        os.environ["CONVERSATION_ENABLED"] = "false"
        manager = ConversationManager(
            llm_client=self.mock_llm_client,
            tts_client=self.mock_tts_client,
            play_audio_callback=self.mock_play_audio,
            get_participant_callback=self.mock_get_participant,
        )

        utterance = {
            "text": "Hi Pamela, test",
            "participant_id": "participant_1",
            "participant_name": "John Doe",
        }

        manager.process_utterance(utterance)
        self.assertFalse(manager.query_buffer.state.is_capturing)
        os.environ["CONVERSATION_ENABLED"] = "true"


if __name__ == "__main__":
    unittest.main()
