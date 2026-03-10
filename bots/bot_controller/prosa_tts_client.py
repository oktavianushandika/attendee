import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class ProsaTTSClient:
    """
    Client for Prosa TTS API.
    
    Submits TTS jobs asynchronously and polls for completion.
    Downloads audio from signed URL when job is complete.
    """
    
    def __init__(self):
        self.base_url = os.getenv("TTS_BASE_URL", "https://tts-api.stg.prosa.ai")
        self.api_key = os.getenv("TTS_API_KEY")
        self.model = os.getenv("TTS_MODEL", "tts-ocha-gentle")
        self.sample_rate = int(os.getenv("TTS_SAMPLE_RATE", "16000"))
        self.audio_format = os.getenv("TTS_AUDIO_FORMAT", "mp3")
        self.poll_interval = int(os.getenv("TTS_POLL_INTERVAL_SECONDS", "3"))
        self.max_poll_time = int(os.getenv("TTS_MAX_POLL_TIME_SECONDS", "60"))
        
        if not self.api_key:
            logger.warning("TTS_API_KEY not set in environment variables")
    
    def is_configured(self) -> bool:
        """Check if TTS client is properly configured"""
        return bool(self.base_url and self.api_key)
    
    def synthesize_speech(self, text: str) -> Optional[bytes]:
        """
        Convert text to speech and return audio bytes.
        
        Args:
            text: The text to convert to speech
            
        Returns:
            MP3 audio bytes, or None if failed
        """
        if not self.is_configured():
            logger.error("TTS client not properly configured. Missing TTS_API_KEY.")
            return None
        
        if not text or not text.strip():
            logger.warning("Empty text provided to TTS, skipping")
            return None
        
        try:
            # Step 1: Submit TTS job
            job_id = self._submit_tts_job(text)
            if not job_id:
                return None
            
            # Step 2: Poll for job completion
            audio_url = self._poll_job_status(job_id)
            if not audio_url:
                return None
            
            # Step 3: Download audio
            audio_bytes = self._download_audio(audio_url)
            return audio_bytes
            
        except Exception as e:
            logger.error(f"Unexpected error in TTS synthesis: {e}")
            return None
    
    def _submit_tts_job(self, text: str) -> Optional[str]:
        """
        Submit TTS job to Prosa API.
        
        Args:
            text: The text to synthesize
            
        Returns:
            job_id if successful, None otherwise
        """
        try:
            url = f"{self.base_url}/v2/speech/tts?as_signed_url=true"
            
            headers = {
                "X-API-Key": self.api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "config": {
                    "model": self.model,
                    "wait": False,
                    "pitch": 0,
                    "tempo": 1,
                    "audio_format": self.audio_format,
                    "sample_rate": self.sample_rate
                },
                "request": {
                    "label": "Audio Result",
                    "text": text
                }
            }
            
            logger.info(f"Submitting TTS job for text: {text[:50]}...")
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            job_id = result.get("job_id")
            
            if job_id:
                logger.info(f"TTS job submitted successfully. job_id: {job_id}")
                return job_id
            else:
                logger.error(f"No job_id in TTS response: {result}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to submit TTS job: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error submitting TTS job: {e}")
            return None
    
    def _poll_job_status(self, job_id: str) -> Optional[str]:
        """
        Poll TTS job status until complete or failed.
        
        Args:
            job_id: The TTS job ID
            
        Returns:
            Audio URL if successful, None otherwise
        """
        try:
            url = f"{self.base_url}/v2/speech/tts/{job_id}?as_signed_url=true"
            
            headers = {
                "X-API-Key": self.api_key
            }
            
            start_time = time.time()
            poll_count = 0
            
            while True:
                # Check if we've exceeded max poll time
                elapsed = time.time() - start_time
                if elapsed > self.max_poll_time:
                    logger.error(f"TTS job polling timeout after {elapsed:.1f} seconds")
                    return None
                
                # Poll job status
                poll_count += 1
                logger.info(f"Polling TTS job status (attempt {poll_count}): {job_id}")
                
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                result = response.json()
                status = result.get("status")
                
                if status == "complete":
                    # Job completed successfully
                    audio_path = result.get("result", {}).get("path")
                    if audio_path:
                        logger.info(f"TTS job completed. Audio URL: {audio_path[:50]}...")
                        return audio_path
                    else:
                        logger.error(f"TTS job complete but no audio path in result: {result}")
                        return None
                
                elif status == "failed":
                    # Job failed
                    logger.error(f"TTS job failed: {result}")
                    return None
                
                elif status == "queued" or status == "processing":
                    # Job still processing, wait and retry
                    logger.debug(f"TTS job status: {status}, waiting {self.poll_interval}s...")
                    time.sleep(self.poll_interval)
                    continue
                
                else:
                    # Unknown status
                    logger.warning(f"Unknown TTS job status: {status}")
                    time.sleep(self.poll_interval)
                    continue
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to poll TTS job status: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error polling TTS job: {e}")
            return None
    
    def _download_audio(self, audio_url: str) -> Optional[bytes]:
        """
        Download audio file from signed URL.
        
        Args:
            audio_url: The signed URL to download audio from
            
        Returns:
            Audio bytes (MP3 format), or None if failed
        """
        try:
            logger.info(f"Downloading audio from: {audio_url[:50]}...")
            
            # Download audio file
            response = requests.get(audio_url, timeout=30)
            response.raise_for_status()
            
            audio_bytes = response.content
            logger.info(f"Audio downloaded successfully. Size: {len(audio_bytes)} bytes")
            
            return audio_bytes
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download audio: {e}")
            
            # Retry once
            try:
                logger.info("Retrying audio download...")
                response = requests.get(audio_url, timeout=30)
                response.raise_for_status()
                audio_bytes = response.content
                logger.info(f"Audio downloaded on retry. Size: {len(audio_bytes)} bytes")
                return audio_bytes
            except Exception as retry_error:
                logger.error(f"Audio download retry failed: {retry_error}")
                return None
                
        except Exception as e:
            logger.error(f"Unexpected error downloading audio: {e}")
            return None
