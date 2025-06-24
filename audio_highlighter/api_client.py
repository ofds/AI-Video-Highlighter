import requests
import json
import logging
from typing import Optional

# You will need to import from your new config file
from .config import OPENROUTER_API_KEY, YOUR_SITE_URL, YOUR_SITE_NAME, OPENROUTER_API_URL, DEFAULT_LLM_MODEL

class OpenRouterClient:
    """A client for interacting with the OpenRouter AI API."""
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key for OpenRouter cannot be None or empty.")
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
            "HTTP-Referer": YOUR_SITE_URL, "X-Title": YOUR_SITE_NAME,
        }

    def get_highlights_from_transcript(self, full_transcript: str) -> Optional[str]:
        logging.info("Requesting highlights from LLM...")
        prompt = f"""
---

I am providing the **full transcript of a YouTube video**. Your task is to **analyze it thoroughly** and extract **structured, machine-readable insights**. The output will be used for further automated processing, so **follow the format exactly** as described below.

✅ **Important Instructions**:

* Do **not** skip or summarize the transcript—**analyze it fully**.
* Output must match the format **precisely** for successful parsing.
* Use consistent indentation and spacing.
* **Do not add extra commentary or explanations** outside the required output.

---

### 🟩 TASK 1 – Identify the most interesting moments:

These may include:

* Engaging dialogue
* Funny or emotional highlights
* Insightful commentary
* High-energy or dramatic moments

**For each moment, provide the following details:**

* `Title`: A concise, descriptive name
* `Start_Time`: Timestamp in `hh:mm:ss` format
* `End_Time`: Timestamp in `hh:mm:ss` format
* `Why_Interesting`: 1–2 sentences explaining the significance

---

### 🟦 TASK 2 – Suggest natural cut points:

These should be moments where a segment can logically begin or end, such as:

* Topic transitions
* Speaker changes
* Long pauses or scene shifts

**For each cut point, provide:**

* `Cut_Timestamp`: Timestamp in `hh:mm:ss` format
* `Reason`: Brief explanation (1 sentence)

---

### 🔷 OUTPUT FORMAT (Strictly follow this Markdown format):

#### Interesting\_Moments:

```
1.
Title: [Title]
Start_Time: hh:mm:ss
End_Time: hh:mm:ss
Why_Interesting: [Explanation]

2.
Title: [Title]
Start_Time: hh:mm:ss
End_Time: hh:mm:ss
Why_Interesting: [Explanation]
```

#### Suggested\_Cut\_Points:

```
1.
Cut_Timestamp: hh:mm:ss
Reason: [Explanation]

2.
Cut_Timestamp: hh:mm:ss
Reason: [Explanation]
```

---

⬇️ Begin your analysis below. Here is the full transcript:

{full_transcript}

---
"""
        data = {"model": DEFAULT_LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1500, "temperature": 0.5}
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
