import logging
import subprocess
from typing import List, Dict, Any
from pathlib import Path

def is_ffmpeg_installed():
    """Checks if FFmpeg is installed and accessible in the system's PATH."""
    try:
        # Use a version command that is quiet and returns success
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def format_timestamp(seconds: float, srt_format: bool = False) -> str:
    """Formats time in seconds to HH:MM:SS or HH:MM:SS,ms for SRT."""
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)

    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000

    minutes = milliseconds // 60_000
    milliseconds %= 60_000

    seconds = milliseconds // 1000
    milliseconds %= 1000

    if srt_format:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def export_highlights_to_txt(highlights_data: List[Dict[str, str]], output_path: Path):
    """Formats the list of highlights into a human-readable .txt file."""
    logging.info(f"Exporting {len(highlights_data)} highlights to {output_path}...")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("AI-Generated Video Highlights\n")
            f.write("="*30 + "\n\n")
            for i, highlight in enumerate(highlights_data):
                f.write(f"{i + 1}.\n")
                f.write(f"  Title: {highlight.get('title', 'N/A')}\n")
                f.write(f"  Time: {highlight.get('start_time')} -> {highlight.get('end_time')}\n")
                f.write(f"  Reason: {highlight.get('why', 'N/A')}\n\n")
        logging.info(f"Successfully exported highlights to '{output_path.name}'.")
    except Exception as e:
        logging.error(f"Failed to export highlights to .txt: {e}")

def export_transcript_to_srt(transcript_segments: List[Dict[str, Any]], output_path: Path):
    """Formats whisper output (segments with timestamps) into .srt format."""
    logging.info(f"Exporting transcript to {output_path}...")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(transcript_segments):
                f.write(f"{i + 1}\n")
                start = format_timestamp(segment['start'], srt_format=True)
                end = format_timestamp(segment['end'], srt_format=True)
                f.write(f"{start} --> {end}\n")
                f.write(f"{segment['text'].strip()}\n\n")
        logging.info(f"Successfully exported transcript to '{output_path.name}'.")
    except Exception as e:
        logging.error(f"Failed to export transcript to .srt: {e}")