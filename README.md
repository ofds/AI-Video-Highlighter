# AI Video Highlighter

This application uses AI to automatically find interesting moments in a video and create a highlight reel. It can download videos from YouTube or use local video files.

The workflow is as follows:
1.  **Download or Select Video**: Provide a YouTube URL to download a video or select a local `.mp4`, `.mov`, etc. file.
2.  **Transcribe Audio**: The audio is extracted from the video and transcribed to text using OpenAI's Whisper model.
3.  **Analyze Transcript**: The full transcript is sent to an LLM via OpenRouter to identify interesting moments and suggest cut points.
4.  **Create Highlight Video**: The identified interesting moments are stitched together into a final highlight video using FFmpeg.

## Setup Instructions

### 1. Prerequisites

You must have **FFmpeg** installed on your system and available in your system's PATH. This is used for all video processing tasks. You can download it from [ffmpeg.org](https://ffmpeg.org/download.html).

### 2. Set Up the Environment

First, clone the repository and navigate into the directory:
```bash
git clone https://github.com/ofds/AI-Video-Highlighter.git
cd audio-highlighter
```

Install the required Python packages:
```bash
pip install -r requirements.txt
```

### 3. Configure API Key

This project uses the OpenRouter API to analyze the transcript. You need to set your API key as an environment variable.

-   **Linux/macOS**:
    ```bash
    export OPENROUTER_API_KEY="your_api_key_here"
    ```
-   **Windows**:
    ```powershell
    $env:OPENROUTER_API_KEY="your_api_key_here"
    ```

## How to Run

Execute the `main.py` script to launch the graphical user interface:
```bash
python main.py
```
