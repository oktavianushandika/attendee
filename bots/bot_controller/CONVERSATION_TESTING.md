# Speech Conversation System - Testing Guide

## Overview

This guide explains how to test the speech conversation system that has been implemented in the BotController.

## Components Implemented

1. **LLMClient** (`llm_client.py`) - Handles SSE streaming from custom LLM API
2. **ProsaTTSClient** (`prosa_tts_client.py`) - Converts text to speech using Prosa AI API
3. **ConversationManager** (`conversation_manager.py`) - Orchestrates trigger detection, query capture, and response flow
4. **BotController Integration** - Wired up to process captions and play audio responses

## Environment Variables

The following environment variables are configured in `.env`:

### LLM Configuration
- `LLM_BASE_URL` - Base URL for LLM API
- `LLM_API_KEY` - API key for authentication
- `LLM_CHATBOT_ID` - Chatbot ID for requests
- `LLM_AGENT_ID` - Agent/conversation ID
- `LLM_TIMEOUT_SECONDS` - Request timeout (default: 30)

### TTS Configuration
- `TTS_BASE_URL` - Base URL for Prosa TTS API
- `TTS_API_KEY` - API key for authentication
- `TTS_MODEL` - TTS model to use (default: tts-ocha-gentle)
- `TTS_SAMPLE_RATE` - Audio sample rate (default: 16000)
- `TTS_AUDIO_FORMAT` - Audio format (default: mp3)
- `TTS_POLL_INTERVAL_SECONDS` - Polling interval (default: 3)
- `TTS_MAX_POLL_TIME_SECONDS` - Max polling time (default: 60)

### Conversation Configuration
- `CONVERSATION_ENABLED` - Enable/disable conversation system (default: true)
- `CONVERSATION_TRIGGER_PHRASES` - Comma-separated trigger phrases (default: "hi pamela,hey pamela,hai pamela")
- `CONVERSATION_QUERY_TIMEOUT_SECONDS` - Query capture timeout (default: 2.5)
- `CONVERSATION_STOP_ON_DIFFERENT_SPEAKER` - Stop capture on speaker change (default: false)

## Testing Steps

### 1. Prerequisites

Ensure the following are configured:
- Bot is created with closed captions enabled
- LLM API endpoint is accessible and configured
- Prosa TTS API key is valid
- All environment variables are set correctly

### 2. Create a Test Bot

Create a bot with the following settings:

```json
{
  "meeting_url": "https://meet.google.com/your-meeting-id",
  "bot_name": "Pamela",
  "transcription_settings": {
    "meeting_closed_captions": {}
  }
}
```

### 3. Join a Meeting

1. Start the bot and have it join a Google Meet
2. Ensure closed captions are enabled in the meeting
3. Wait for the bot to successfully join

### 4. Test Trigger Phrase Detection

**Test Case 1: Basic Trigger**
- Say: "Hi Pamela"
- Expected: Bot should detect trigger phrase and start capturing query
- Check logs for: "Trigger phrase detected: 'hi pamela'"

**Test Case 2: Trigger with Query**
- Say: "Hey Pamela, what's the weather today?"
- Expected: Bot should capture "what's the weather today?" as query
- Check logs for: "Query captured: what's the weather today?"

**Test Case 3: Multi-sentence Query**
- Say: "Hai Pamela, tell me a joke. Make it funny."
- Wait 2.5 seconds
- Expected: Bot should capture full query after timeout
- Check logs for query capture and LLM request

### 5. Test LLM Integration

Monitor logs for:
1. "Sending query to LLM: [query text]"
2. "LLM response received: [response text]"
3. Check that SSE streaming is working correctly
4. Verify JSON parsing extracts message from response

### 6. Test TTS Integration

Monitor logs for:
1. "Submitting TTS job for text: [response text]"
2. "TTS job submitted successfully. job_id: [job_id]"
3. "Polling TTS job status (attempt N): [job_id]"
4. "TTS job completed. Audio URL: [url]"
5. "Audio downloaded successfully. Size: [bytes] bytes"

### 7. Test Audio Playback

Monitor logs for:
1. "Converting MP3 to PCM for conversation audio ([bytes] bytes)"
2. "Converted to PCM ([bytes] bytes), sending to adapter"
3. "Conversation audio sent successfully"
4. Verify that participants in the meeting can hear the bot's response

### 8. Test Error Handling

**Test Case 1: LLM Timeout**
- Temporarily set `LLM_TIMEOUT_SECONDS=1`
- Trigger conversation
- Expected: "LLM request timed out" error, bot continues running

**Test Case 2: TTS Job Failure**
- Use invalid TTS configuration
- Expected: "TTS job failed" error, bot continues running

**Test Case 3: Invalid Trigger**
- Say something without trigger phrase
- Expected: No conversation triggered, bot continues monitoring

### 9. Test Query Timeout

**Test Case 1: Short Pause**
- Say: "Hi Pamela, what is..."
- Wait 2.5 seconds
- Expected: Query captured with timeout

**Test Case 2: Continuous Speech**
- Say: "Hey Pamela, tell me about the history of computers and how they evolved over time"
- Keep speaking for 5+ seconds
- Expected: Query continues capturing until pause

### 10. Test Concurrent Conversations

**Test Case 1: Rapid Triggers**
- Say: "Hi Pamela, first question"
- Immediately say: "Hey Pamela, second question"
- Expected: First query processed, second query queued or skipped
- Check logs for: "Already processing a query, skipping this one"

## Log Monitoring

Key log messages to watch for:

### Success Flow
```
ConversationManager initialized. Enabled: True, Trigger phrases: ['hi pamela', 'hey pamela', 'hai pamela']
Processing utterance: Hi Pamela, what's the weather?
Trigger phrase detected: 'hi pamela'
Started query capture for participant [id]
Query captured: what's the weather?
Sending query to LLM: what's the weather?
LLM response received: The weather today is...
Converting response to speech...
TTS job submitted successfully. job_id: abc123
Polling TTS job status (attempt 1): abc123
TTS job completed. Audio URL: https://...
Audio downloaded successfully. Size: 12345 bytes
Converting MP3 to PCM for conversation audio (12345 bytes)
Converted to PCM (54321 bytes), sending to adapter
Conversation audio sent successfully
Conversation response completed successfully
```

### Error Scenarios
```
LLM client not properly configured. Missing environment variables.
TTS client not properly configured. Missing TTS_API_KEY.
Failed to get LLM response
Failed to synthesize speech
Error playing conversation audio: [error details]
Already processing a query, skipping this one
```

## Debugging Tips

1. **Enable Debug Logging**: Set log level to DEBUG to see detailed flow
2. **Check Environment Variables**: Verify all required vars are set
3. **Test LLM Endpoint**: Use curl to test LLM API independently
4. **Test TTS Endpoint**: Use curl to test Prosa TTS API independently
5. **Monitor Network**: Check for network connectivity issues
6. **Check Captions**: Ensure closed captions are working in the meeting

## Common Issues

### Issue: Trigger not detected
- Check caption text format
- Verify trigger phrases are lowercase in config
- Ensure captions are being received (check logs)

### Issue: LLM not responding
- Verify LLM_BASE_URL is correct
- Check LLM_API_KEY is valid
- Test endpoint with curl
- Check timeout settings

### Issue: TTS job fails
- Verify TTS_API_KEY is valid
- Check TTS_BASE_URL is correct
- Ensure text is not empty
- Check Prosa API status

### Issue: Audio not playing
- Verify bot has audio permissions
- Check PCM conversion is successful
- Ensure adapter supports send_raw_audio
- Check meeting platform audio settings

## Performance Considerations

- LLM response time: Typically 2-10 seconds
- TTS job processing: Typically 5-15 seconds
- Total response time: 7-25 seconds from trigger to audio playback
- Query timeout: 2.5 seconds (configurable)
- Concurrent processing: Only 1 query at a time

## Next Steps

After successful testing:
1. Tune timeout values based on actual usage
2. Add more trigger phrases if needed
3. Implement conversation history tracking (future enhancement)
4. Add support for different speaker detection (future enhancement)
5. Optimize response time by caching common responses (future enhancement)
