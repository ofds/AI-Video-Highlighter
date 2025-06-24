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