import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, List

from .llm_client import LLMClient
from .prosa_tts_client import ProsaTTSClient

logger = logging.getLogger(__name__)


@dataclass
class CaptureState:
    """State for capturing query after trigger phrase"""
    is_capturing: bool = False
    query_text: str = ""
    last_update_time: float = 0
    participant_id: Optional[str] = None
    trigger_phrase: Optional[str] = None


class TriggerPhraseDetector:
    """Detects trigger phrases in text (case-insensitive)"""
    
    def __init__(self, trigger_phrases: List[str]):
        self.trigger_phrases = [phrase.lower() for phrase in trigger_phrases]
        # Create regex patterns for each trigger phrase
        self.patterns = [
            re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
            for phrase in trigger_phrases
        ]
    
    def detect(self, text: str) -> Optional[tuple]:
        """
        Detect trigger phrase in text.
        
        Args:
            text: The text to search
            
        Returns:
            Tuple of (trigger_phrase, remaining_text) if found, None otherwise
        """
        for i, phrase in enumerate(self.trigger_phrases):
            pattern = self.patterns[i]
            match = pattern.search(text)
            
            if match:
                # Extract text after trigger phrase
                trigger_end = match.end()
                remaining_text = text[trigger_end:].strip()
                
                logger.info(f"Trigger phrase detected: '{phrase}'")
                return (phrase, remaining_text)
        
        return None


class QueryCaptureBuffer:
    """Buffers text after trigger phrase with timeout"""
    
    def __init__(self, timeout_seconds: float):
        self.timeout_seconds = timeout_seconds
        self.state = CaptureState()
    
    def start_capture(self, initial_text: str, participant_id: str, trigger_phrase: str):
        """Start capturing query text"""
        self.state.is_capturing = True
        self.state.query_text = initial_text
        self.state.last_update_time = time.time()
        self.state.participant_id = participant_id
        self.state.trigger_phrase = trigger_phrase
        
        logger.info(f"Started query capture for participant {participant_id}")
    
    def append_text(self, text: str, participant_id: str) -> bool:
        """
        Append text to capture buffer.
        
        Args:
            text: Text to append
            participant_id: ID of participant speaking
            
        Returns:
            True if capture should continue, False if should stop
        """
        if not self.state.is_capturing:
            return False
        
        # Check if different speaker (if enabled)
        stop_on_different_speaker = os.getenv("CONVERSATION_STOP_ON_DIFFERENT_SPEAKER", "false").lower() == "true"
        if stop_on_different_speaker and participant_id != self.state.participant_id:
            logger.info("Different speaker detected, stopping capture")
            return False
        
        # Append text
        if self.state.query_text:
            self.state.query_text += " " + text
        else:
            self.state.query_text = text
        
        self.state.last_update_time = time.time()
        return True
    
    def is_timeout_reached(self) -> bool:
        """Check if timeout has been reached"""
        if not self.state.is_capturing:
            return False
        
        elapsed = time.time() - self.state.last_update_time
        return elapsed >= self.timeout_seconds
    
    def get_query(self) -> str:
        """Get captured query and reset state"""
        query = self.state.query_text.strip()
        self.reset()
        return query
    
    def reset(self):
        """Reset capture state"""
        self.state = CaptureState()


class ConversationManager:
    """
    Manages speech conversation flow:
    1. Monitors captions for trigger phrases
    2. Captures query text after trigger
    3. Sends query to LLM
    4. Converts LLM response to speech
    5. Plays audio response
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        tts_client: ProsaTTSClient,
        play_audio_callback: Callable[[bytes], None],
        get_participant_callback: Callable[[str], Optional[dict]]
    ):
        self.llm_client = llm_client
        self.tts_client = tts_client
        self.play_audio_callback = play_audio_callback
        self.get_participant_callback = get_participant_callback
        
        # Configuration
        self.enabled = os.getenv("CONVERSATION_ENABLED", "true").lower() == "true"
        trigger_phrases_str = os.getenv("CONVERSATION_TRIGGER_PHRASES", "hi pamela,hey pamela,hai pamela")
        self.trigger_phrases = [phrase.strip() for phrase in trigger_phrases_str.split(",")]
        timeout_seconds = float(os.getenv("CONVERSATION_QUERY_TIMEOUT_SECONDS", "2.5"))
        
        # Components
        self.trigger_detector = TriggerPhraseDetector(self.trigger_phrases)
        self.query_buffer = QueryCaptureBuffer(timeout_seconds)
        
        # State
        self.processing_lock = threading.Lock()
        self.is_processing = False
        
        logger.info("ConversationManager initialized. Enabled: %s, Trigger phrases: %s", self.enabled, self.trigger_phrases)
    
    def process_utterance(self, utterance: dict):
        """
        Process an utterance from closed captions.
        
        Args:
            utterance: Dictionary with keys: 'text', 'participant_id', 'participant_name'
        """
        if not self.enabled:
            return
        
        if not self.llm_client.is_configured() or not self.tts_client.is_configured():
            logger.warning("Conversation system not fully configured, skipping utterance")
            return
        
        text = utterance.get("text", "").strip()
        participant_id = utterance.get("participant_id", "unknown")
        
        if not text:
            return
        
        logger.debug(f"Processing utterance: {text[:50]}... (participant: {participant_id})")
        
        # Check if we're currently capturing
        if self.query_buffer.state.is_capturing:
            # Check timeout
            if self.query_buffer.is_timeout_reached():
                # Timeout reached, process query
                self._finalize_and_process_query()
            else:
                # Continue capturing
                should_continue = self.query_buffer.append_text(text, participant_id)
                if not should_continue:
                    # Different speaker, finalize query
                    self._finalize_and_process_query()
        else:
            # Not capturing, check for trigger phrase
            detection_result = self.trigger_detector.detect(text)
            if detection_result:
                trigger_phrase, remaining_text = detection_result
                # Start capturing query
                self.query_buffer.start_capture(remaining_text, participant_id, trigger_phrase)
                
                # If there's already text after trigger, start timeout check
                if remaining_text:
                    self._schedule_timeout_check()
    
    def _schedule_timeout_check(self):
        """Schedule a check for query timeout"""
        def check_timeout():
            time.sleep(self.query_buffer.timeout_seconds + 0.1)  # Add small buffer
            if self.query_buffer.is_timeout_reached():
                self._finalize_and_process_query()
        
        thread = threading.Thread(target=check_timeout, daemon=True)
        thread.start()
    
    def _finalize_and_process_query(self):
        """Finalize query capture and process with LLM"""
        query = self.query_buffer.get_query()
        
        if not query:
            logger.info("Query capture finished but no text captured")
            return
        
        logger.info(f"Query captured: {query}")
        
        # Process in background thread to avoid blocking
        thread = threading.Thread(
            target=self._process_query_async,
            args=(query,),
            daemon=True
        )
        thread.start()
    
    def _process_query_async(self, query: str):
        """Process query with LLM and TTS in background thread"""
        # Prevent concurrent processing
        with self.processing_lock:
            if self.is_processing:
                logger.warning("Already processing a query, skipping this one")
                return
            self.is_processing = True
        
        try:
            # TODO: Re-enable LLM integration once parsing is fixed
            # For now, skip LLM and pass query directly to TTS for testing
            
            # Step 1: Get LLM response (TEMPORARILY DISABLED)
            # logger.info(f"Sending query to LLM: {query}")
            # llm_response = self.llm_client.get_response(query)
            # 
            # if not llm_response:
            #     logger.error("Failed to get LLM response")
            #     return
            # 
            # logger.info(f"LLM response: {llm_response[:100]}...")
            
            # TEMPORARY: Use query directly as the text to speak
            logger.info("TEMPORARY MODE: Skipping LLM, using query directly for TTS")
            logger.info(f"Query to speak: {query}")
            text_to_speak = "Lorem Ipsum adalah contoh teks atau dummy dalam industri percetakan dan penataan huruf atau typesetting. Lorem Ipsum telah menjadi standar contoh teks sejak tahun 1500an, saat seorang tukang cetak yang tidak dikenal mengambil sebuah kumpulan teks dan mengacaknya untuk menjadi sebuah buku contoh huruf."
            
            # Step 2: Split text into sentences
            logger.info("Splitting response into sentences...")
            sentences = self.tts_client.split_into_sentences(text_to_speak)
            logger.info("Split into %d sentences", len(sentences))
            
            # Step 3: Process and play each sentence
            for i, sentence in enumerate(sentences, 1):
                logger.info("Processing sentence %d/%d: %s...", i, len(sentences), sentence[:50])
                
                # Convert sentence to speech (synchronous)
                audio_bytes = self.tts_client.synthesize_speech_sync(sentence)
                
                if not audio_bytes:
                    logger.error("Failed to synthesize sentence %d, skipping", i)
                    continue
                
                logger.info("Sentence %d synthesized, size: %d bytes", i, len(audio_bytes))
                
                # Play audio immediately
                logger.info("Playing sentence %d audio...", i)
                self.play_audio_callback(audio_bytes)
            
            logger.info("Conversation response completed successfully - played %d sentences", len(sentences))
            
        except Exception as e:
            logger.error(f"Error processing conversation query: {e}", exc_info=True)
        finally:
            self.is_processing = False
