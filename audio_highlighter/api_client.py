import requests
import json
import logging
from typing import Optional

# Import configuration constants
from .config import OPENROUTER_API_KEY, YOUR_SITE_URL, YOUR_SITE_NAME, OPENROUTER_API_URL

class OpenRouterClient:
    """A client for interacting with the OpenRouter AI API."""
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key for OpenRouter cannot be None or empty.")
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": YOUR_SITE_URL,
            "X-Title": YOUR_SITE_NAME,
        }
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> Optional[str]:
        """Loads the LLM prompt from an external file."""
        try:
            with open("prompt.txt", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logging.error("CRITICAL: 'prompt.txt' not found in the application's root directory.")
            return None

    def get_highlights_from_transcript(self, full_transcript: str, llm_model: str) -> Optional[str]:
        """Sends the transcript to the LLM to get structured highlights."""
        if not self.prompt_template:
            logging.error("Cannot get highlights because the prompt template failed to load.")
            return None

        logging.info(f"Requesting highlights from LLM using model: {llm_model}...")
        
        # Format the loaded prompt template with the actual transcript
        prompt = self.prompt_template.format(full_transcript=full_transcript)
        
        data = {
            "model": llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,  # Increased tokens for potentially longer prompts/responses
            "temperature": 0.4   # Slightly adjusted for more deterministic output
        }

        try:
            response = requests.post(url=OPENROUTER_API_URL, headers=self.headers, data=json.dumps(data))
            response.raise_for_status()  # This will raise an HTTPError for bad responses (4xx or 5xx)
            response_data = response.json()
            logging.info("LLM response received successfully.")
            return response_data['choices'][0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            logging.error(f"API request failed: {e}")
        except (KeyError, IndexError, ValueError) as e:
            logging.error(f"Could not parse highlights from LLM response: {e}")
        
        return None