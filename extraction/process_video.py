import argparse
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import whisper

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
HIGHLIGHT_VIDEO_FILENAME_SUFFIX = "_highlight.mp4" # New for the final video
DEFAULT_WHISPER_MODEL = "base.en"


# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def format_timestamp(seconds: float, srt_format: bool = False) -> str:
    """Formats a timestamp in seconds to [HH:MM:SS] or SRT format."""
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)

    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000

    minutes = milliseconds // 60_000
    milliseconds %= 60_000

    seconds = milliseconds // 1_000
    milliseconds %= 1_000

    if srt_format:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


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

    def get_highlights_from_transcript(self, full_transcript: str) -> Optional[str]:
        # Cleaned up the prompt to be a proper multi-line f-string to avoid syntax warnings
        # and improve readability for the LLM.
        prompt = f"""I am providing you with the transcript of a YouTube video. Your task is to analyze the full transcript and extract structured insights. This output will be used in a further processing phase, so **strictly follow the format** provided below and ensure **consistency and machine-readability**.

---

### 🟩 Your tasks:

#### 1. Identify the **most interesting moments** in the video:
These can be engaging conversations, funny remarks, insightful commentary, or high-energy moments. For each moment, provide:
- **Title**: A short, descriptive title.
- **Start_Time**: The beginning timestamp `hh:mm:ss`.
- **End_Time**: The ending timestamp `hh:mm:ss`.
- **Why_Interesting**: 1-2 concise sentences explaining the appeal.

#### 2. Suggest **good cut points**:
These are natural transitions or breaks (e.g., topic shifts, pauses). For each cut point, provide:
- **Cut_Timestamp**: The timestamp `hh:mm:ss`.
- **Reason**: A short justification for the cut.

---

### 🟦 REQUIRED OUTPUT FORMAT (strictly follow this markdown structure):

#### Interesting_Moments:
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

#### Suggested_Cut_Points:
```
1.
Cut_Timestamp: hh:mm:ss
Reason: [Explanation]

2.
Cut_Timestamp: hh:mm:ss
Reason: [Explanation]
```
---

Please output only in the exact format above. Here is the transcript:

{full_transcript}
"""
        data = {"model": DEFAULT_LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1500, "temperature": 0.5}
        try:
            response = requests.post(url=OPENROUTER_API_URL, headers=self.headers, data=json.dumps(data))
            response.raise_for_status()
            response_data = response.json()
            return response_data['choices'][0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            logging.error(f"API request failed: {e}")
        except (KeyError, IndexError, ValueError) as e:
            logging.error(f"Could not parse highlights from LLM response: {e}")
        return None

class VideoProcessor:
    """Handles the entire video processing workflow."""

    def __init__(self, video_path: Path, output_dir: Path, whisper_model: str):
        self.video_path = video_path
        self.output_dir = output_dir
        
        video_stem = self.video_path.stem
        self.transcript_path = self.output_dir / f"{video_stem}{TRANSCRIPT_FILENAME_SUFFIX}"
        self.srt_path = self.output_dir / f"{video_stem}{SRT_FILENAME_SUFFIX}"
        self.highlights_path = self.output_dir / f"{video_stem}{HIGHLIGHTS_FILENAME_SUFFIX}"
        self.temp_audio_path = self.output_dir / f"{video_stem}{TEMP_AUDIO_FILENAME_SUFFIX}"
        # New path for the final highlight video
        self.highlight_video_path = self.output_dir / f"{video_stem}{HIGHLIGHT_VIDEO_FILENAME_SUFFIX}"

        self.whisper_model = self._load_whisper_model(whisper_model)
        self.llm_client = OpenRouterClient(OPENROUTER_API_KEY) if OPENROUTER_API_KEY else None

    @classmethod
    def run_with_hardcoded_path(cls):
        """Initializes and runs the processor using a hardcoded path."""
        video_to_process = Path(r"C:\Codigos\audio-highlighter\videos\Our FIFA Club World Cup Predictions!.mp4")

        if not video_to_process.is_file():
            logging.error(f"HARDCODED PATH ERROR: Video file not found at '{video_to_process}'")
            return

        logging.info(f"Running in hardcoded mode for: {video_to_process.name}")
        
        output_directory = Path("output") 
        whisper_model_name = DEFAULT_WHISPER_MODEL
        
        try:
            processor = cls(
                video_path=video_to_process,
                output_dir=output_directory,
                whisper_model=whisper_model_name
            )
            processor.process_video()
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}", exc_info=True)

    def _load_whisper_model(self, model_name: str):
        logging.info(f"Loading Whisper model: {model_name}...")
        try:
            return whisper.load_model(model_name)
        except Exception as e:
            logging.error(f"Failed to load Whisper model '{model_name}': {e}")
            raise

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
        logging.info(f"Processing complete for '{self.video_path.name}'.")

    def _extract_audio(self) -> bool:
        logging.info(f"Extracting audio from '{self.video_path.name}'...")
        command = ["ffmpeg", "-y", "-i", str(self.video_path), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(self.temp_audio_path)]
        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            logging.info(f"Audio extracted successfully to '{self.temp_audio_path.name}'")
            return True
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            logging.error(f"Error during audio extraction. Make sure FFmpeg is installed and in your PATH. Details: {e}")
            return False

    def _transcribe_audio(self) -> Optional[List[Dict[str, Any]]]:
        logging.info("Transcribing audio...")
        try:
            result = self.whisper_model.transcribe(str(self.temp_audio_path))
            logging.info("Transcription complete.")
            return result.get("segments")
        except Exception as e:
            logging.error(f"Error during transcription: {e}")
            return None

    def _format_transcript_for_llm(self, segments: List[Dict[str, Any]]) -> str:
        return "".join(f"[{format_timestamp(s['start'])}] {s['text'].strip()}\n" for s in segments)

    def _save_transcripts(self, segments: List[Dict[str, Any]]):
        with open(self.transcript_path, "w", encoding="utf-8") as f:
            f.write(self._format_transcript_for_llm(segments))
        logging.info(f"Transcript saved to {self.transcript_path}")

        with open(self.srt_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments):
                f.write(f"{i + 1}\n")
                start = format_timestamp(segment['start'], srt_format=True)
                end = format_timestamp(segment['end'], srt_format=True)
                f.write(f"{start} --> {end}\n")
                f.write(f"{segment['text'].strip()}\n\n")
        logging.info(f"SRT captions saved to {self.srt_path}")

    def _generate_and_save_highlights(self, full_transcript: str) -> Optional[str]:
        """Generates highlights, saves them, and returns the text content."""
        logging.info("Generating highlights with LLM...")
        highlights = self.llm_client.get_highlights_from_transcript(full_transcript)
        if highlights:
            with open(self.highlights_path, "w", encoding="utf-8") as f:
                f.write(highlights)
            logging.info(f"--- Highlights ---\n{highlights}")
            logging.info(f"Highlights saved to {self.highlights_path}")
            return highlights
        else:
            logging.error("Could not retrieve highlights from the LLM.")
            return None

    def _parse_highlights_for_video(self, highlights_text: str) -> List[Tuple[str, str]]:
        """Parses the LLM output to extract start and end times for video clips."""
        logging.info("Parsing timestamps from highlights text...")
        segments = []
        try:
            # Find the "Interesting_Moments" block using regex
            interesting_moments_match = re.search(r"Interesting_Moments:\s*```(.*?)```", highlights_text, re.DOTALL)
            if not interesting_moments_match:
                logging.warning("Could not find 'Interesting_Moments' block in highlights file.")
                return []

            moments_text = interesting_moments_match.group(1)
            
            # Find all individual moments within the block
            # This regex looks for a block of text starting with "Title:"
            moment_blocks = re.findall(r"Title:.*?(?=\n\s*\d+\.|\Z)", moments_text, re.DOTALL)

            for block in moment_blocks:
                start_time_match = re.search(r"Start_Time:\s*(\d{2}:\d{2}:\d{2})", block)
                end_time_match = re.search(r"End_Time:\s*(\d{2}:\d{2}:\d{2})", block)
                if start_time_match and end_time_match:
                    segments.append((start_time_match.group(1), end_time_match.group(1)))
        except Exception as e:
            logging.error(f"Failed to parse highlights for video segments: {e}")
            return []
            
        logging.info(f"Found {len(segments)} highlight segments to compile into a video.")
        return segments

    def _create_highlight_video(self, time_segments: List[Tuple[str, str]]):
        """Creates a highlight video by cutting and stitching clips with FFmpeg."""
        if not time_segments:
            logging.info("No time segments found, skipping highlight video creation.")
            return

        logging.info("Creating highlight video...")
        
        # Use a temporary directory that gets cleaned up automatically
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            clip_files = []

            for i, (start, end) in enumerate(time_segments):
                clip_filename = temp_path / f"clip_{i}.mp4"
                # Command to cut a clip from the source video without re-encoding
                command = [
                    "ffmpeg", "-y",
                    "-ss", start,
                    "-to", end,
                    "-i", str(self.video_path),
                    "-c", "copy",  # Use stream copy for extreme speed and original quality
                    str(clip_filename)
                ]
                try:
                    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    clip_files.append(clip_filename)
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    logging.error(f"Failed to create clip {i} with ffmpeg.")
                    if isinstance(e, subprocess.CalledProcessError):
                        logging.error(f"FFmpeg stderr: {e.stderr.decode()}")
                    return # Stop if a clip fails

            if not clip_files:
                logging.error("No clips were created, cannot generate highlight video.")
                return

            # Create a file list for ffmpeg's concat demuxer
            concat_list_path = temp_path / "concat_list.txt"
            with open(concat_list_path, "w") as f:
                for clip in clip_files:
                    # Use resolve() to get an absolute path, which is safer for ffmpeg
                    f.write(f"file '{clip.resolve()}'\n")

            # Command to stitch the clips together
            concat_command = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_path),
                "-c", "copy",
                str(self.highlight_video_path)
            ]
            try:
                subprocess.run(concat_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logging.info(f"Successfully created highlight video: {self.highlight_video_path}")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logging.error(f"Failed to stitch clips with ffmpeg.")
                if isinstance(e, subprocess.CalledProcessError):
                    logging.error(f"FFmpeg stderr: {e.stderr.decode()}")

    def _cleanup(self):
        """Removes temporary files."""
        try:
            if self.temp_audio_path.exists():
                self.temp_audio_path.unlink()
                logging.info(f"Removed temporary audio file: {self.temp_audio_path.name}")
        except OSError as e:
            logging.error(f"Error removing temporary file: {e}")

def cli_main():
    """Main entry point for command-line execution."""
    parser = argparse.ArgumentParser(description="Transcribe a video and generate a highlight reel.")
    parser.add_argument("video_path", type=Path, help="The path to the video file.")
    parser.add_argument("--model", type=str, default=DEFAULT_WHISPER_MODEL, help="Whisper model name.")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Directory to save output files.")
    args = parser.parse_args()

    if not args.video_path.is_file():
        logging.error(f"Error: Video file not found at '{args.video_path}'")
        return

    try:
        processor = VideoProcessor(
            video_path=args.video_path,
            output_dir=args.output_dir,
            whisper_model=args.model
        )
        processor.process_video()
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    RUN_WITH_HARDCODED_PATH = True

    if not OPENROUTER_API_KEY:
        logging.error("FATAL: OPENROUTER_API_KEY environment variable not set.")
    elif RUN_WITH_HARDCODED_PATH:
        VideoProcessor.run_with_hardcoded_path()
    else:
        cli_main()
