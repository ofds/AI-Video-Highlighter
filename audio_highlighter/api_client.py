import requests
import json
import logging
from typing import Optional, List

# Import configuration constants
from .config import OPENROUTER_API_URL, YOUR_SITE_URL, YOUR_SITE_NAME

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

    def get_free_models(self) -> List[str]:
        """
        Fetches the list of all models from OpenRouter and filters for free ones.
        A model is considered free if its prompt and completion pricing is 0.
        """
        logging.info("Fetching available LLM models from OpenRouter...")
        try:
            response = requests.get(url="https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {self.api_key}"})
            response.raise_for_status()
            models_data = response.json().get("data", [])
            
            free_models = []
            for model in models_data:
                pricing = model.get("pricing", {})
                try:
                    # Check if prompt and completion prices are zero
                    prompt_price = float(pricing.get("prompt", "1.0"))
                    completion_price = float(pricing.get("completion", "1.0"))
                    if prompt_price == 0.0 and completion_price == 0.0:
                        free_models.append(model.get("id"))
                except (ValueError, TypeError):
                    continue  # Skip if pricing is not a valid number

            logging.info(f"Found {len(free_models)} free models.")
            return free_models
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch models from OpenRouter API: {e}")
            return []
        except (KeyError, IndexError, ValueError) as e:
            logging.error(f"Could not parse models from OpenRouter response: {e}")
            return []

    def get_highlights_from_transcript(self, full_transcript: str, llm_model: str) -> Optional[str]:
        """Sends the transcript to the LLM to get structured highlights."""
        if not self.prompt_template:
            logging.error("Cannot get highlights because the prompt template failed to load.")
            return None

        logging.info(f"Requesting highlights from LLM using model: {llm_model}...")
        
        prompt = self.prompt_template.format(full_transcript=full_transcript)
        
        data = {
            "model": llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.4
        }

        try:
            response = requests.post(url=OPENROUTER_API_URL, headers=self.headers, data=json.dumps(data))
            response.raise_for_status()
            response_data = response.json()
            logging.info("LLM response received successfully.")
            return response_data['choices'][0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            logging.error(f"API request failed: {e}")
        except (KeyError, IndexError, ValueError) as e:
            logging.error(f"Could not parse highlights from LLM response: {e}")
        
        return None