import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import whisper

# Import from your new modules
from .api_client import OpenRouterClient
from .config import (
    OPENROUTER_API_KEY, TRANSCRIPT_FILENAME_SUFFIX, SRT_FILENAME_SUFFIX,
    HIGHLIGHTS_FILENAME_SUFFIX, TEMP_AUDIO_FILENAME_SUFFIX,
    HIGHLIGHT_VIDEO_FILENAME_SUFFIX
)
from .utils import format_timestamp

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
