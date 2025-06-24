import argparse
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import queue
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from logging.handlers import QueueHandler

import requests
import whisper
import customtkinter as ctk
from customtkinter import filedialog

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

# --- Helper Functions (format_timestamp) ---
def format_timestamp(seconds: float, srt_format: bool = False) -> str:
    """Formats a timestamp in seconds to [HH:MM:SS] or SRT format."""
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1_000)
    if srt_format:
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{int(milliseconds):03d}"
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

# --- Core Logic Classes (OpenRouterClient, VideoProcessor) ---
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
        prompt = f"""Your prompt is already quite clear and structured, but to **optimize it for better performance**, especially when used with structured LLMs like Gemini or GPT, you can improve the precision, reduce ambiguity, and emphasize consistency with parsing-friendly wording.

Here’s an improved version:

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

class VideoProcessor:
    """Handles the entire video processing workflow."""
    def __init__(self, video_path: Path, output_dir: Path, whisper_model_name: str):
        self.video_path = video_path
        self.output_dir = output_dir
        video_stem = self.video_path.stem
        self.transcript_path = self.output_dir / f"{video_stem}{TRANSCRIPT_FILENAME_SUFFIX}"
        self.srt_path = self.output_dir / f"{video_stem}{SRT_FILENAME_SUFFIX}"
        self.highlights_path = self.output_dir / f"{video_stem}{HIGHLIGHTS_FILENAME_SUFFIX}"
        self.temp_audio_path = self.output_dir / f"{video_stem}{TEMP_AUDIO_FILENAME_SUFFIX}"
        self.highlight_video_path = self.output_dir / f"{video_stem}{HIGHLIGHT_VIDEO_FILENAME_SUFFIX}"
        self.whisper_model_name = whisper_model_name
        self.llm_client = OpenRouterClient(OPENROUTER_API_KEY) if OPENROUTER_API_KEY else None

    def process_video(self):
        """Main method to run the entire processing pipeline."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # --- Step 1: Get Transcript ---
        full_transcript_text = None
        if self.transcript_path.is_file():
            logging.info(f"Transcript file found at '{self.transcript_path}'. Skipping transcription.")
            full_transcript_text = self.transcript_path.read_text(encoding="utf-8")
        else:
            if self._extract_audio():
                segments = self._transcribe_audio()
                if segments:
                    self._save_transcripts(segments)
                    full_transcript_text = self._format_transcript_for_llm(segments)
        
        # --- Step 2: Get Highlights Text ---
        highlights_text = None
        if full_transcript_text:
            if self.highlights_path.is_file():
                logging.info(f"Highlights file found at '{self.highlights_path}'. Skipping LLM generation.")
                highlights_text = self.highlights_path.read_text(encoding="utf-8")
            elif self.llm_client:
                highlights_text = self._generate_and_save_highlights(full_transcript_text)
            else:
                logging.warning("OPENROUTER_API_KEY not set. Skipping highlight generation.")

        # --- Step 3: Create Highlight Video ---
        if highlights_text:
            time_segments = self._parse_highlights_for_video(highlights_text)
            if time_segments:
                self._create_highlight_video(time_segments)
        
        # --- Step 4: Cleanup ---
        self._cleanup()
        logging.info(f"✅ Processing complete for '{self.video_path.name}'.")

    def _extract_audio(self) -> bool:
        logging.info(f"Extracting audio from '{self.video_path.name}'...")
        command = ["ffmpeg", "-y", "-i", str(self.video_path), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(self.temp_audio_path)]
        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            logging.info(f"Audio extracted successfully.")
            return True
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            logging.error(f"Error during audio extraction. Make sure FFmpeg is installed and in your PATH. Details: {e}")
            return False

    def _format_transcript_for_llm(self, segments: List[Dict[str, Any]]) -> str:
        """Formats the transcript segments into a single string for the LLM."""
        return "".join(
            f"[{format_timestamp(s['start'])}] {s['text'].strip()}\n" for s in segments
        )


    def _transcribe_audio(self) -> Optional[List[Dict[str, Any]]]:
        logging.info(f"Loading Whisper model '{self.whisper_model_name}'...")
        try:
            model = whisper.load_model(self.whisper_model_name)
            logging.info("Model loaded. Starting transcription...")
            result = model.transcribe(str(self.temp_audio_path))
            logging.info("Transcription complete.")
            return result.get("segments")
        except Exception as e:
            logging.error(f"Error during transcription: {e}")
            return None

    def _generate_and_save_highlights(self, full_transcript: str) -> Optional[str]:
        highlights = self.llm_client.get_highlights_from_transcript(full_transcript)
        if highlights:
            with open(self.highlights_path, "w", encoding="utf-8") as f: f.write(highlights)
            logging.info(f"Highlights saved to {self.highlights_path}")
            return highlights
        logging.error("Could not retrieve highlights from the LLM.")
        return None

    def _parse_highlights_for_video(self, highlights_text: str) -> List[Tuple[str, str]]:
        logging.info("Parsing timestamps from highlights text...")
        segments = []
        try:
            interesting_moments_match = re.search(r"Interesting_Moments:\s*```(.*?)```", highlights_text, re.DOTALL)
            if not interesting_moments_match:
                logging.warning("Could not find 'Interesting_Moments' block in highlights file.")
                return []
            moments_text = interesting_moments_match.group(1)
            moment_blocks = re.findall(r"Title:.*?(?=\n\s*\d+\.|\Z)", moments_text, re.DOTALL)
            for block in moment_blocks:
                start_time_match = re.search(r"Start_Time:\s*(\d{2}:\d{2}:\d{2})", block)
                end_time_match = re.search(r"End_Time:\s*(\d{2}:\d{2}:\d{2})", block)
                if start_time_match and end_time_match:
                    segments.append((start_time_match.group(1), end_time_match.group(1)))
        except Exception as e:
            logging.error(f"Failed to parse highlights for video segments: {e}")
            return []
        logging.info(f"Found {len(segments)} segments to compile into a highlight video.")
        return segments

    def _create_highlight_video(self, time_segments: List[Tuple[str, str]]):
        logging.info("Creating highlight video...")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            clip_files = []
            for i, (start, end) in enumerate(time_segments):
                clip_filename = temp_path / f"clip_{i}.mp4"
                command = ["ffmpeg", "-y", "-i", str(self.video_path), "-ss", start, "-to", end, "-c", "copy", str(clip_filename)]
                try:
                    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    clip_files.append(clip_filename)
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    logging.error(f"Failed to create clip {i} with ffmpeg.")
                    if isinstance(e, subprocess.CalledProcessError): logging.error(f"FFmpeg stderr: {e.stderr.decode()}")
                    return
            if not clip_files:
                logging.error("No clips were created, cannot generate highlight video.")
                return

            concat_list_path = temp_path / "concat_list.txt"
            with open(concat_list_path, "w") as f:
                for clip in clip_files: f.write(f"file '{clip.resolve()}'\n")

            concat_command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list_path), "-c", "copy", str(self.highlight_video_path)]
            try:
                subprocess.run(concat_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logging.info(f"✅ Successfully created highlight video: {self.highlight_video_path}")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logging.error(f"Failed to stitch clips with ffmpeg.")
                if isinstance(e, subprocess.CalledProcessError): logging.error(f"FFmpeg stderr: {e.stderr.decode()}")

    def _save_transcripts(self, segments: List[Dict[str, Any]]):
        with open(self.transcript_path, "w", encoding="utf-8") as f: f.write(self._format_transcript_for_llm(segments))
        logging.info(f"Transcript saved to {self.transcript_path}")
        with open(self.srt_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments):
                f.write(f"{i + 1}\n")
                start, end = format_timestamp(segment['start'], srt_format=True), format_timestamp(segment['end'], srt_format=True)
                f.write(f"{start} --> {end}\n")
                f.write(f"{segment['text'].strip()}\n\n")
        logging.info(f"SRT captions saved to {self.srt_path}")

    def _cleanup(self):
        try:
            if self.temp_audio_path.exists(): self.temp_audio_path.unlink()
        except OSError as e:
            logging.error(f"Error removing temporary audio file: {e}")

# --- GUI Application Class ---
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Video Highlighter")
        self.geometry("800x600")
        ctk.set_appearance_mode("dark")
        self.video_path = None
        self.processing_thread = None

        # --- Configure grid layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Top Frame for Controls ---
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.top_frame.grid_columnconfigure(1, weight=1)

        self.select_button = ctk.CTkButton(self.top_frame, text="Select Video", command=self.select_video_file)
        self.select_button.grid(row=0, column=0, padx=(0, 10))

        self.path_label = ctk.CTkLabel(self.top_frame, text="No video selected", text_color="gray", anchor="w")
        self.path_label.grid(row=0, column=1, sticky="ew")

        self.process_button = ctk.CTkButton(self.top_frame, text="Process Video", command=self.start_processing_thread, state="disabled")
        self.process_button.grid(row=0, column=2, padx=(10, 0))

        # --- Log Textbox ---
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", text_color="#E0E0E0")
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # --- Status Bar ---
        self.status_label = ctk.CTkLabel(self, text="Ready", anchor="w")
        self.status_label.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="ew")

        # --- Setup logging to redirect to GUI ---
        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[self.queue_handler])
        
        self.after(100, self.poll_log_queue)

    def select_video_file(self):
        """Opens a file dialog to select a video."""
        path = filedialog.askopenfilename(
            title="Select a Video File",
            filetypes=(("Video Files", "*.mp4 *.mkv *.avi *.mov"), ("All files", "*.*"))
        )
        if path:
            self.video_path = Path(path)
            self.path_label.configure(text=self.video_path.name)
            self.process_button.configure(state="normal")
            self.log_textbox.configure(state="normal")
            self.log_textbox.delete("1.0", "end")
            self.log_textbox.insert("end", f"Selected video: {self.video_path}\n")
            self.log_textbox.configure(state="disabled")
            self.status_label.configure(text=f"Ready to process '{self.video_path.name}'")

    def start_processing_thread(self):
        """Starts the video processing in a separate thread to avoid freezing the GUI."""
        if self.processing_thread and self.processing_thread.is_alive():
            logging.warning("Processing is already in progress.")
            return

        self.process_button.configure(state="disabled")
        self.select_button.configure(state="disabled")
        
        self.processing_thread = threading.Thread(target=self.run_video_processor, daemon=True)
        self.processing_thread.start()

    def run_video_processor(self):
        """The target function for the processing thread."""
        if not self.video_path:
            logging.error("No video file selected.")
            return

        try:
            output_dir = Path("output")
            processor = VideoProcessor(
                video_path=self.video_path,
                output_dir=output_dir,
                whisper_model_name=DEFAULT_WHISPER_MODEL
            )
            processor.process_video()
        except Exception as e:
            logging.error(f"A critical error occurred: {e}", exc_info=True)
        finally:
            # Safely re-enable buttons from the main thread
            self.after(0, self.on_processing_finished)

    def on_processing_finished(self):
        """Callback function to run on the main thread after processing is done."""
        self.process_button.configure(state="normal")
        self.select_button.configure(state="normal")
        self.status_label.configure(text="Processing finished. Ready for next video.")

    def poll_log_queue(self):
        """Periodically checks the log queue and updates the textbox."""
        while True:
            try:
                record = self.log_queue.get(block=False)
            except queue.Empty:
                break
            else:
                msg = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s').format(record)
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", msg + "\n")
                self.log_textbox.see("end") # Auto-scroll
                self.log_textbox.configure(state="disabled")
                self.status_label.configure(text=record.getMessage())
        self.after(100, self.poll_log_queue)


if __name__ == "__main__":
    if not OPENROUTER_API_KEY:
        # This check is crucial. The GUI will start but processing will fail.
        # A popup could be added here for a better user experience.
        print("FATAL: OPENROUTER_API_KEY environment variable not set.")
    app = App()
    app.mainloop()
