import os

# --- Configuration ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Optional:
YOUR_SITE_URL = ""
YOUR_SITE_NAME = ""

# --- Constants ---
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_LLM_MODEL = "deepseek/deepseek-chat-v3-0324:free"
TEMP_AUDIO_FILENAME_SUFFIX = "_temp_audio.wav"
TRANSCRIPT_FILENAME_SUFFIX = "_transcript.txt"
SRT_FILENAME_SUFFIX = "_transcript.srt"
HIGHLIGHTS_FILENAME_SUFFIX = "_highlights.txt"
HIGHLIGHT_VIDEO_FILENAME_SUFFIX = "_highlight.mp4"
DEFAULT_WHISPER_MODEL = "base.en"