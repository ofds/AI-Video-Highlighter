import subprocess
import whisper
import os

def extract_audio(video_path, audio_output_path="audio.wav"):
    """
    Extracts mono, 16kHz WAV audio from a video file using ffmpeg.
    """
    command = [
        "ffmpeg",
        "-i", video_path,
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # PCM 16-bit little-endian
        "-ar", "16000",  # 16 kHz sample rate
        "-ac", "1",  # Mono audio
        audio_output_path
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
        print(f"Audio extracted successfully to {audio_output_path}")
        return audio_output_path
    except subprocess.CalledProcessError as e:
        print(f"Error during audio extraction: {e}")
        print(f"STDOUT: {e.stdout.decode()}")
        print(f"STDERR: {e.stderr.decode()}")
        return None

def transcribe_audio(audio_path, model_name="base"):
    """
    Transcribes audio using OpenAI Whisper.
    """
    try:
        model = whisper.load_model(model_name)
        result = model.transcribe(audio_path)
        segments = result["segments"]
        print("Transcription complete.")
        return segments
    except Exception as e:
        print(f"Error during transcription: {e}")
        return None

def format_timestamp(seconds: float) -> str:
    """
    Formats a timestamp in seconds to HH:MM:SS,ms format.
    """
    ms = int((seconds % 1) * 1000)
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"

def save_transcript_to_txt(segments, output_file="transcript.txt"):
    """
    Saves the transcribed segments with timestamps to a plain text file.
    """
    with open(output_file, "w", encoding="utf-8") as f:
        for segment in segments:
            start_time = format_timestamp(segment['start'])
            end_time = format_timestamp(segment['end'])
            f.write(f"[{start_time[:-4]}] {segment['text'].strip()}\n") # Using HH:MM:SS for plain text for readability
    print(f"Transcript saved to {output_file}")

def save_transcript_to_srt(segments, output_file="transcript.srt"):
    """
    Saves the transcribed segments with timestamps to an SRT (SubRip) file.
    SRT format:
    1
    00:00:00,000 --> 00:00:03,000
    This is the first subtitle.

    2
    00:00:03,500 --> 00:00:06,000
    This is the second subtitle.
    """
    with open(output_file, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments):
            f.write(f"{i + 1}\n")
            start_time = format_timestamp(segment['start'])
            end_time = format_timestamp(segment['end'])
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{segment['text'].strip()}\n\n")
    print(f"SRT file saved to {output_file}")


def main(video_file):
    audio_file = "audio.wav"

    # Step 1 & 2: Audio Extraction
    extracted_audio_path = extract_audio(video_file, audio_file)
    if not extracted_audio_path:
        print("Failed to extract audio. Exiting.")
        return

    # Step 3: Transcription
    transcribed_segments = transcribe_audio(extracted_audio_path)
    if not transcribed_segments:
        print("Failed to transcribe audio. Exiting.")
        return

    # Print a few segments to verify
    print("\nSample Transcribed Segments:")
    for i, segment in enumerate(transcribed_segments[:5]): # Print first 5 segments
        print(f"[{segment['start']:.2f} - {segment['end']:.2f}] {segment['text']}")

    # --- NEW: Save the timestamped transcript ---
    save_transcript_to_txt(transcribed_segments, "video_transcript.txt")
    save_transcript_to_srt(transcribed_segments, "video_captions.srt")
    # -------------------------------------------

    # Clean up the audio file (optional)
    # os.remove(audio_file)
    # print(f"Removed temporary audio file: {audio_file}")

    # Now you can proceed with 'Interestingness Scoring' using 'transcribed_segments'
    # The 'transcribed_segments' list will contain dictionaries like:
    # {'id': 0, 'seek': 0, 'start': 0.0, 'end': 3.0, 'text': ' This is a test.', 'tokens': [...], 'temperature': 0.0, 'avg_logprob': -0.2, 'compression_ratio': 1.0, 'no_speech_prob': 0.0}

    return transcribed_segments

if __name__ == "__main__":
    # IMPORTANT: Replace 'your_video.mp4' with the actual path to your video file
    # For testing, you might want to use a small sample video.
    video_to_process = r"C:\Codigos\audio-highlighter\extraction\videos\Our FIFA Club World Cup Predictions!.mp4" # <--- CHANGE THIS!

    if not os.path.exists(video_to_process):
        print(f"Error: Video file '{video_to_process}' not found.")
        print("Please replace 'your_video.mp4' with the correct path to your video.")
    else:
        print(f"Starting processing for video: {video_to_process}")
        segments = main(video_to_process)
        if segments:
            print("\nSuccessfully processed video and got segments. Ready for scoring!")