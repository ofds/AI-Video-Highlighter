import datetime
import subprocess # Import the subprocess module

def format_timestamp(seconds: float, srt_format: bool = False) -> str:
    """Formats a timestamp in seconds into hh:mm:ss or hh:mm:ss,ms format."""
    td = datetime.timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = int(td.microseconds / 1000)
    
    if srt_format:
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"
    return f"{hours:02}:{minutes:02}:{seconds:02}"

def is_ffmpeg_installed() -> bool:
    """Checks if FFmpeg is installed and accessible in the system's PATH."""
    try:
        # Execute 'ffmpeg -version'. We capture the output to prevent it from printing to the console.
        # 'check=True' will raise a CalledProcessError if the command returns a non-zero exit code.
        subprocess.run(
            ["ffmpeg", "-version"], 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        # FileNotFoundError occurs if 'ffmpeg' command is not found.
        # CalledProcessError might occur for other reasons, but we treat it as a failure.
        return False