import json
import logging
import os
import re
from typing import Generator, Optional

import requests

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Client for interacting with custom LLM API via SSE (Server-Sent Events).
    
    The LLM API returns newline-separated JSON objects in SSE format.
    We extract the 'message' field from the last JSON object where status === 'response'.
    """
    
    def __init__(self):
        self.base_url = os.getenv("LLM_BASE_URL")
        self.api_key = os.getenv("LLM_API_KEY")
        self.chatbot_id = os.getenv("LLM_CHATBOT_ID")
        self.agent_id = os.getenv("LLM_AGENT_ID")
        self.timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        
        if not self.base_url:
            logger.warning("LLM_BASE_URL not set in environment variables")
        if not self.api_key:
            logger.warning("LLM_API_KEY not set in environment variables")
        if not self.chatbot_id:
            logger.warning("LLM_CHATBOT_ID not set in environment variables")
        if not self.agent_id:
            logger.warning("LLM_AGENT_ID not set in environment variables")
    
    def is_configured(self) -> bool:
        """Check if all required configuration is present"""
        return bool(self.base_url and self.api_key and self.chatbot_id and self.agent_id)
    
    def get_response(self, query: str) -> Optional[str]:
        """
        Send query to LLM and get response.
        
        Args:
            query: The user's query text
            
        Returns:
            The LLM's response text, or None if failed
        """
        if not self.is_configured():
            logger.error("LLM client not properly configured. Missing environment variables.")
            return None
        
        try:
            logger.info(f"Sending query to LLM: {query}")
            
            # Prepare form data
            form_data = {
                "chatbot_id": self.chatbot_id,
                "message": query,
                "conversation_id": self.agent_id,
                "model_name": "GPT 5 Mini"
            }
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # Make POST request with streaming enabled for SSE
            response = requests.post(
                f"{self.base_url}/message/",
                data=form_data,
                headers=headers,
                stream=True,
                timeout=self.timeout
            )
            
            response.raise_for_status()

            logger.info(f"LLM response: {response.text}")
            
            # Parse SSE response (newline-separated JSON objects)
            response_message = self._parse_sse_response(response)
            
            if response_message:
                logger.info(f"LLM response received: {response_message[:100]}...")
                return response_message
            else:
                logger.warning("No valid response message found in LLM response")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"LLM request timed out after {self.timeout} seconds")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in LLM client: {e}")
            return None
    
    def stream_sentences(self, query: str) -> Generator[str, None, None]:
        """
        Generator that yields complete sentences from the LLM SSE stream as they arrive.

        Sentences are detected at `.`, `?`, and `!` boundaries so TTS can start
        processing sentence N while the LLM is still generating sentence N+1.

        The SSE API sends cumulative growing text in each `status=response` chunk
        (the last chunk carries the full response). We compute the delta on each
        chunk and buffer it until a sentence boundary is found.
        """
        if not self.is_configured():
            logger.error("LLM client not properly configured. Missing environment variables.")
            return

        sentence_end_pattern = re.compile(r'([^.?!]*[.?!])\s*')

        try:
            form_data = {
                "chatbot_id": self.chatbot_id,
                "message": query,
                "conversation_id": self.agent_id,
                "model_name": "GPT 5 Mini"
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            response = requests.post(
                f"{self.base_url}/message/",
                data=form_data,
                headers=headers,
                stream=True,
                timeout=self.timeout
            )
            response.raise_for_status()

            last_seen_text = ""
            buffer = ""

            for raw_line in response.iter_lines():
                if not raw_line:
                    continue

                if isinstance(raw_line, bytes):
                    line = raw_line.decode("utf-8")
                else:
                    line = raw_line

                if not line.startswith("data:"):
                    continue

                json_str = line[5:].strip()
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    continue

                if data.get("status") != "response" or not data.get("message"):
                    continue

                current_text = data["message"]

                # Compute delta: if the API sends cumulative text, only the new
                # suffix is new content; if it sends pure deltas, the delta is
                # the entire current_text.
                if current_text.startswith(last_seen_text):
                    delta = current_text[len(last_seen_text):]
                else:
                    delta = current_text

                last_seen_text = current_text
                buffer += delta

                # Yield complete sentences from the buffer
                while True:
                    match = sentence_end_pattern.match(buffer)
                    if not match:
                        break
                    sentence = match.group(1).strip()
                    if sentence:
                        logger.info("Streaming sentence to TTS: %s...", sentence[:60])
                        yield sentence
                    buffer = buffer[match.end():]

            # Yield any remaining text after the stream ends
            remaining = buffer.strip()
            if remaining:
                logger.info("Streaming final sentence to TTS: %s...", remaining[:60])
                yield remaining

        except requests.exceptions.Timeout:
            logger.error("LLM stream request timed out after %d seconds", self.timeout)
        except requests.exceptions.RequestException as e:
            logger.error("LLM stream request failed: %s", e)
        except Exception as e:
            logger.error("Unexpected error in LLM stream_sentences: %s", e, exc_info=True)

    def _extract_latest_response_message(self, sse_data: str) -> Optional[str]:
        """
        Extract the latest response message from SSE data string.
        Converted from TypeScript implementation.
        
        Args:
            sse_data: Complete SSE response data as string
            
        Returns:
            The latest response message, or None if not found
        """
        try:
            logger.debug("Parsing GLChat SSE response data (length: %d, preview: %s...)", 
                        len(sse_data) if sse_data else 0,
                        sse_data[:500] if sse_data else "")
            
            if not sse_data or not isinstance(sse_data, str):
                logger.warning("Invalid SSE data provided")
                return None
            
            # Split the SSE data by lines
            lines = [line for line in sse_data.split('\n') if line.strip()]
            logger.debug("Split SSE data into %d lines (preview: %s)", 
                        len(lines), 
                        lines[:5] if lines else [])
            
            # Filter for lines starting with "data:" and parse JSON
            response_messages = []
            
            for line in lines:
                if line.startswith('data:'):
                    try:
                        # Remove "data:" prefix
                        json_str = line[5:].strip()
                        data = json.loads(json_str)
                        
                        logger.debug("Parsed SSE data line - status: %s, has_message: %s, message_length: %d",
                                    data.get('status'),
                                    bool(data.get('message')),
                                    len(data.get('message', '')) if data.get('message') else 0)
                        
                        # Collect messages with "response" status
                        if data.get('status') == 'response' and data.get('message'):
                            response_messages.append(data['message'])
                            logger.debug("Found response message (preview: %s..., total: %d)",
                                        data['message'][:100],
                                        len(response_messages))
                    
                    except json.JSONDecodeError as parse_error:
                        logger.warning("Failed to parse SSE data line (line: %s..., error: %s)",
                                      line[:200],
                                      str(parse_error))
                        continue
            
            logger.info("Response message extraction summary - lines_processed: %d, response_messages_found: %d",
                       len(lines),
                       len(response_messages))
            
            # Return the last (latest) response message
            if response_messages:
                latest_message = response_messages[-1]
                logger.info("Found latest response message (preview: %s..., total_messages: %d)",
                           latest_message[:200],
                           len(response_messages))
                return latest_message
            
            logger.warning("No response messages found in SSE data")
            return None
        
        except Exception as e:
            logger.error("Failed to extract latest response message - error: %s, sse_data_length: %d",
                        str(e),
                        len(sse_data) if sse_data else 0,
                        exc_info=True)
            return None
    
    def _parse_sse_response(self, response) -> Optional[str]:
        """
        Parse SSE response by reading entire stream and extracting latest response message.
        
        Args:
            response: requests.Response object with streaming enabled
            
        Returns:
            The latest response message text, or None if not found
        """
        try:
            # Read entire response content as string
            sse_data = response.text    
            
            # Extract latest response message using the converted TypeScript logic
            return self._extract_latest_response_message(sse_data)
            
        except Exception as e:
            logger.error("Error parsing SSE response: %s", e, exc_info=True)
            return None
