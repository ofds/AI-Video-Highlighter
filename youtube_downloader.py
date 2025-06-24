# In youtube_downloader.py

import logging
import subprocess
from pathlib import Path

def download_youtube_video(url: str, output_dir: Path) -> Path | None:
    """
    Downloads a YouTube video using the yt-dlp command-line tool.
    This is generally more reliable than pytube.

    Args:
        url: The YouTube video URL.
        output_dir: The directory to save the video in.

    Returns:
        The path to the downloaded video file, or None if it fails.
    """
    try:
        logging.info(f"Attempting download with yt-dlp for URL: {url}")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Define the command to run yt-dlp
        command = [
            "yt-dlp",
            # Get the best mp4 video and audio and merge them
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            # Define the output file path and name
            "-o", str(output_dir / "%(title)s.%(ext)s"),
            url,
        ]

        # Run the command and capture output
        result = subprocess.run(
            command,
            check=True,
        )

        # Find the downloaded file, as yt-dlp names it based on the video title
        files_in_output_dir = list(output_dir.glob("*.mp4"))
        if not files_in_output_dir:
            logging.error("yt-dlp ran but no MP4 file was found in the output directory.")
            return None

        # Return the most recently modified file in the directory
        latest_file = max(files_in_output_dir, key=lambda p: p.stat().st_mtime)
        logging.info(f"yt-dlp download successful. File saved as: {latest_file.name}")
        return latest_file

    except FileNotFoundError:
        logging.error("yt-dlp command not found. Please ensure it is installed and in your system's PATH.")
        return None
    except subprocess.CalledProcessError as e:
        logging.error("yt-dlp failed with an error. It's possible the video is unavailable or private.")
        # The stderr from yt-dlp is often very informative
        logging.error(f"yt-dlp stderr: {e.stderr}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while running yt-dlp: {e}")
        return None