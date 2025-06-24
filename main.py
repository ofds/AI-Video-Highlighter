import customtkinter as ctk
from customtkinter import filedialog
import logging
import queue
import threading
from pathlib import Path
from logging.handlers import QueueHandler
from typing import Optional, Callable

# Import the core logic and config
from audio_highlighter.video_processor import VideoProcessor
from audio_highlighter.config import OPENROUTER_API_KEY, AVAILABLE_WHISPER_MODELS, AVAILABLE_LLM_MODELS, DEFAULT_WHISPER_MODEL, DEFAULT_LLM_MODEL
from audio_highlighter.youtube_downloader import download_youtube_video
from audio_highlighter.utils import is_ffmpeg_installed # Import the new function

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Video Highlighter v2.0")
        self.geometry("800x800")
        ctk.set_appearance_mode("dark")
        self.video_path = None
        self.processing_thread = None
        self.download_thread = None

        # --- Configure grid layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1) 

        # --- Top Frame for URL Input ---
        self.url_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.url_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        self.url_frame.grid_columnconfigure(1, weight=1)

        self.url_label = ctk.CTkLabel(self.url_frame, text="YouTube URL:")
        self.url_label.grid(row=0, column=0, padx=(0, 10))

        self.url_entry = ctk.CTkEntry(self.url_frame, placeholder_text="https://www.youtube.com/watch?v=...")
        self.url_entry.grid(row=0, column=1, sticky="ew")

        self.download_button = ctk.CTkButton(self.url_frame, text="Download Video", command=self.start_download_thread)
        self.download_button.grid(row=0, column=2, padx=(10, 0))
        
        # --- Middle Frame for Local File and Processing ---
        self.local_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.local_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.local_frame.grid_columnconfigure(1, weight=1)

        self.select_button = ctk.CTkButton(self.local_frame, text="Or Select Local Video", command=self.select_video_file)
        self.select_button.grid(row=0, column=0, padx=(0, 10))

        self.path_label = ctk.CTkLabel(self.local_frame, text="No video selected or downloaded", text_color="gray", anchor="w")
        self.path_label.grid(row=0, column=1, sticky="ew")

        self.process_button = ctk.CTkButton(self.local_frame, text="Process Video", command=self.start_processing_thread, state="disabled")
        self.process_button.grid(row=0, column=2, padx=(10, 0))

        # --- Model Selection Frame ---
        self.model_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.model_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        self.model_frame.grid_columnconfigure(1, weight=1)
        self.model_frame.grid_columnconfigure(3, weight=1)

        self.whisper_label = ctk.CTkLabel(self.model_frame, text="Whisper Model:")
        self.whisper_label.grid(row=0, column=0, padx=(0,10))
        self.whisper_model_menu = ctk.CTkOptionMenu(self.model_frame, values=AVAILABLE_WHISPER_MODELS)
        self.whisper_model_menu.grid(row=0, column=1, padx=(0,20), sticky="ew")
        self.whisper_model_menu.set(DEFAULT_WHISPER_MODEL)

        self.llm_label = ctk.CTkLabel(self.model_frame, text="LLM Model:")
        self.llm_label.grid(row=0, column=2, padx=(0,10))
        self.llm_model_menu = ctk.CTkOptionMenu(self.model_frame, values=AVAILABLE_LLM_MODELS)
        self.llm_model_menu.grid(row=0, column=3, sticky="ew")
        self.llm_model_menu.set(DEFAULT_LLM_MODEL)

        # --- Log Textbox and Status Bar ---
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", text_color="#E0E0E0")
        self.log_textbox.grid(row=3, column=0, padx=10, pady=(5, 10), sticky="nsew")

        # --- Progress Bar and Status ---
        self.status_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.status_frame.grid(row=4, column=0, padx=10, pady=(5,10), sticky="ew")
        self.status_frame.grid_columnconfigure(0, weight=1)
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="Ready", anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self.status_frame)
        self.progress_bar.set(0)
        
        # Setup logging
        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        logging.basicConfig(level=logging.INFO, handlers=[self.queue_handler])
        self.after(100, self.poll_log_queue)

        # --- Final setup: Check for dependencies ---
        self.check_dependencies()

    def check_dependencies(self):
        """Checks for required system dependencies like FFmpeg."""
        if not is_ffmpeg_installed():
            # Disable all interactive controls
            self.url_entry.configure(state="disabled")
            self.download_button.configure(state="disabled")
            self.select_button.configure(state="disabled")
            self.process_button.configure(state="disabled")
            
            # Display a prominent error message
            error_message = "ERROR: FFmpeg not found in your system's PATH.\nPlease install FFmpeg to use this application."
            self.status_label.configure(text="FFmpeg not found!", text_color="red")
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("1.0", error_message)
            self.log_textbox.configure(state="disabled")
            logging.error(error_message)

    # ... (the rest of the methods remain the same)

    def start_download_thread(self):
        """Starts the YouTube download in a separate thread."""
        if self.download_thread and self.download_thread.is_alive():
            logging.warning("A download is already in progress.")
            return
        youtube_url = self.url_entry.get()
        if not youtube_url:
            logging.error("YouTube URL cannot be empty.")
            return
        self.process_button.configure(state="disabled")
        self.download_button.configure(state="disabled")
        self.select_button.configure(state="disabled")
        download_dir = Path("videos")
        self.download_thread = threading.Thread(
            target=self.run_youtube_downloader,
            args=(youtube_url, download_dir),
            daemon=True
        )
        self.download_thread.start()

    def run_youtube_downloader(self, url: str, output_dir: Path):
        """Target function for the download thread."""
        downloaded_path = download_youtube_video(url, output_dir)
        self.after(0, self.on_download_finished, downloaded_path)

    def on_download_finished(self, downloaded_path: Path | None):
        """Callback to run on the main thread after download is done."""
        if downloaded_path and downloaded_path.is_file():
            self.video_path = downloaded_path
            self.path_label.configure(text=self.video_path.name)
            self.process_button.configure(state="normal")
            logging.info(f"Video set successfully: {self.video_path.name}")
        else:
            self.path_label.configure(text="Download failed. Please check logs.", text_color="red")
            logging.error("Failed to set video path after download.")
        self.download_button.configure(state="normal")
        self.select_button.configure(state="normal")

    def select_video_file(self):
        """Opens a file dialog to select a video."""
        path = filedialog.askopenfilename(
            title="Select a Video File",
            filetypes=(("Video Files", "*.mp4 *.mkv *.avi *.mov"), ("All files", "*.*"))
        )
        if path:
            self.video_path = Path(path)
            self.path_label.configure(text=self.video_path.name, text_color="gray")
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
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(5,0))
        self.progress_bar.set(0)
        whisper_model = self.whisper_model_menu.get()
        llm_model = self.llm_model_menu.get()
        self.processing_thread = threading.Thread(
            target=self.run_video_processor, 
            args=(whisper_model, llm_model),
            daemon=True
        )
        self.processing_thread.start()

    def run_video_processor(self, whisper_model, llm_model):
        """The target function for the processing thread."""
        if not self.video_path:
            logging.error("No video file selected.")
            return
        try:
            output_dir = Path("output")
            processor = VideoProcessor(
                video_path=self.video_path,
                output_dir=output_dir,
                whisper_model=whisper_model,
                llm_model=llm_model,
                progress_callback=self.update_progress
            )
            processor.process_video()
        except Exception as e:
            logging.error(f"A critical error occurred: {e}", exc_info=True)
        finally:
            self.after(0, self.on_processing_finished)
    
    def update_progress(self, value: float):
        """Callback method to update the progress bar from another thread."""
        self.progress_bar.set(value)

    def on_processing_finished(self):
        """Callback function to run on the main thread after processing is done."""
        self.progress_bar.grid_remove()
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
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")
                self.status_label.configure(text=record.getMessage())
        self.after(100, self.poll_log_queue)

if __name__ == "__main__":
    if not OPENROUTER_API_KEY:
        print("FATAL: OPENROUTER_API_KEY environment variable not set.")
    app = App()
    app.mainloop()