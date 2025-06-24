import customtkinter as ctk
from customtkinter import filedialog
import logging
import queue
import threading
from pathlib import Path
from logging.handlers import QueueHandler
from typing import Optional, List, Dict, Tuple, Any

from audio_highlighter.video_processor import VideoProcessor
from audio_highlighter.config import OPENROUTER_API_KEY, AVAILABLE_WHISPER_MODELS, AVAILABLE_LLM_MODELS, DEFAULT_WHISPER_MODEL, DEFAULT_LLM_MODEL
from audio_highlighter.youtube_downloader import download_youtube_video
from audio_highlighter.utils import is_ffmpeg_installed
from audio_highlighter.highlight_editor_gui import HighlightEditorWindow

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Video Highlighter v2.0")
        self.geometry("800x800")
        ctk.set_appearance_mode("dark")
        self.video_path: Optional[Path] = None
        self.processor: Optional[VideoProcessor] = None
        self.analysis_thread: Optional[threading.Thread] = None
        self.creation_thread: Optional[threading.Thread] = None
        self.download_thread: Optional[threading.Thread] = None
        self.editor_window: Optional[HighlightEditorWindow] = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1) 

        self.url_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.url_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        self.url_frame.grid_columnconfigure(1, weight=1)
        self.url_label = ctk.CTkLabel(self.url_frame, text="YouTube URL:")
        self.url_label.grid(row=0, column=0, padx=(0, 10))
        self.url_entry = ctk.CTkEntry(self.url_frame, placeholder_text="https://www.youtube.com/watch?v=...")
        self.url_entry.grid(row=0, column=1, sticky="ew")
        self.download_button = ctk.CTkButton(self.url_frame, text="Download Video", command=self.start_download_thread)
        self.download_button.grid(row=0, column=2, padx=(10, 0))
        
        self.local_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.local_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.local_frame.grid_columnconfigure(1, weight=1)
        self.select_button = ctk.CTkButton(self.local_frame, text="Or Select Local Video", command=self.select_video_file)
        self.select_button.grid(row=0, column=0, padx=(0, 10))
        self.path_label = ctk.CTkLabel(self.local_frame, text="No video selected or downloaded", text_color="gray", anchor="w")
        self.path_label.grid(row=0, column=1, sticky="ew")
        self.process_button = ctk.CTkButton(self.local_frame, text="Analyze Video", command=self.start_analysis_thread, state="disabled")
        self.process_button.grid(row=0, column=2, padx=(10, 0))

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

        self.log_textbox = ctk.CTkTextbox(self, state="disabled", text_color="#E0E0E0")
        self.log_textbox.grid(row=3, column=0, padx=10, pady=(5, 10), sticky="nsew")
        self.status_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.status_frame.grid(row=4, column=0, padx=10, pady=(5,10), sticky="ew")
        self.status_frame.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(self.status_frame, text="Ready", anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.progress_bar = ctk.CTkProgressBar(self.status_frame)
        self.progress_bar.set(0)
        
        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        logging.basicConfig(level=logging.INFO, handlers=[self.queue_handler])
        self.after(100, self.poll_log_queue)
        self.check_dependencies()

    def set_ui_state(self, is_enabled: bool):
        """Helper function to enable/disable main UI controls."""
        state = "normal" if is_enabled else "disabled"
        self.download_button.configure(state=state)
        self.select_button.configure(state=state)
        self.process_button.configure(state=state if self.video_path else "disabled")
        self.url_entry.configure(state=state)
        self.whisper_model_menu.configure(state=state)
        self.llm_model_menu.configure(state=state)

    def check_dependencies(self):
        if not is_ffmpeg_installed():
            self.set_ui_state(is_enabled=False)
            error_message = "FATAL: FFmpeg not found. Please install FFmpeg and ensure it is in your system's PATH."
            self.status_label.configure(text="FFmpeg not found!", text_color="red")
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("1.0", error_message)
            self.log_textbox.configure(state="disabled")
            logging.error(error_message)

    def start_download_thread(self):
        if (self.download_thread and self.download_thread.is_alive()) or \
           (self.analysis_thread and self.analysis_thread.is_alive()):
            logging.warning("A download or analysis process is already running.")
            return
        youtube_url = self.url_entry.get()
        if not youtube_url:
            logging.error("YouTube URL cannot be empty.")
            return
            
        self.set_ui_state(is_enabled=False)
        self.path_label.configure(text="Downloading...", text_color="gray")
        download_dir = Path("videos")
        self.download_thread = threading.Thread(
            target=self.run_youtube_downloader,
            args=(youtube_url, download_dir),
            daemon=True
        )
        self.download_thread.start()

    def run_youtube_downloader(self, url: str, output_dir: Path):
        downloaded_path = download_youtube_video(url, output_dir)
        self.after(0, self.on_download_finished, downloaded_path)

    def on_download_finished(self, downloaded_path: Optional[Path]):
        if downloaded_path and downloaded_path.is_file():
            self.video_path = downloaded_path
            self.path_label.configure(text=self.video_path.name, text_color="white")
            logging.info(f"Video set successfully: {self.video_path.name}")
        else:
            self.path_label.configure(text="Download failed. Check logs.", text_color="red")
            logging.error("Failed to set video path after download.")
        self.set_ui_state(is_enabled=True)

    def select_video_file(self):
        path_str = filedialog.askopenfilename(
            title="Select a Video File",
            filetypes=(("Video Files", "*.mp4 *.mkv *.avi *.mov"), ("All files", "*.*"))
        )
        if path_str:
            self.video_path = Path(path_str)
            self.path_label.configure(text=self.video_path.name, text_color="white")
            self.process_button.configure(state="normal")
            self.log_textbox.configure(state="normal")
            self.log_textbox.delete("1.0", "end")
            self.log_textbox.configure(state="disabled")
            self.status_label.configure(text=f"Ready to process '{self.video_path.name}'")

    def start_analysis_thread(self):
        if self.analysis_thread and self.analysis_thread.is_alive():
            logging.warning("Analysis is already in progress.")
            return
            
        self.set_ui_state(is_enabled=False)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(5,0))
        self.progress_bar.set(0)
        
        self.analysis_thread = threading.Thread(
            target=self.run_analysis,
            daemon=True
        )
        self.analysis_thread.start()

    def run_analysis(self):
        if not self.video_path:
            logging.error("No video file selected for analysis.")
            self.after(0, self.on_analysis_finished, None, None)
            return
            
        try:
            output_dir = Path("output")
            whisper_model = self.whisper_model_menu.get()
            llm_model = self.llm_model_menu.get()
            
            self.processor = VideoProcessor(
                video_path=self.video_path,
                output_dir=output_dir,
                whisper_model=whisper_model,
                llm_model=llm_model,
                progress_callback=self.update_progress
            )
            highlights_data, transcript_segments = self.processor.generate_highlights_data()
            self.after(0, self.on_analysis_finished, highlights_data, transcript_segments)
        except Exception as e:
            logging.error(f"A critical error occurred during analysis: {e}", exc_info=True)
            self.after(0, self.on_analysis_finished, None, None)

    def on_analysis_finished(self, highlights_data: Optional[List[Dict[str, str]]], transcript_segments: Optional[List[Dict[str, Any]]]):
        """Callback run on main thread after analysis is complete."""
        self.progress_bar.grid_remove()
        
        if highlights_data and self.processor:
            self.status_label.configure(text="Analysis complete. Please review highlights.")
            logging.info("Analysis finished. Opening highlight editor window.")
            self.editor_window = HighlightEditorWindow(
                master=self,
                highlights=highlights_data,
                transcript_segments=transcript_segments,
                start_creation_callback=self.start_creation_thread
            )
        else:
            logging.error("Analysis did not produce any highlights. Check logs for details.")
            self.status_label.configure(text="Analysis failed. Ready for next video.")
            self.set_ui_state(is_enabled=True)

    def start_creation_thread(self, time_segments: List[Tuple[str, str]]):
        if self.creation_thread and self.creation_thread.is_alive():
            logging.warning("A video creation process is already running.")
            return
            
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(5,0))
        self.progress_bar.set(0)
        self.status_label.configure(text="Creating final highlight video...")
        
        self.creation_thread = threading.Thread(
            target=self.run_video_creation,
            args=(time_segments,),
            daemon=True
        )
        self.creation_thread.start()
        
    def run_video_creation(self, time_segments: List[Tuple[str, str]]):
        try:
            if self.processor:
                self.processor.create_highlight_video(time_segments)
            else:
                logging.error("VideoProcessor instance was lost. Cannot create video.")
        except Exception as e:
            logging.error(f"A critical error occurred during video creation: {e}", exc_info=True)
        finally:
            self.after(0, self.on_creation_finished)

    def on_creation_finished(self):
        """Callback run on the main thread after the final video is created."""
        self.progress_bar.grid_remove()
        self.status_label.configure(text="Processing finished! Ready for next video.")
        self.set_ui_state(is_enabled=True)

    def update_progress(self, value: float, text: str):
        self.progress_bar.set(value)
        self.status_label.configure(text=text)

    def poll_log_queue(self):
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
                if record.levelno >= logging.WARNING:
                    self.status_label.configure(text=record.getMessage())
        self.after(100, self.poll_log_queue)

if __name__ == "__main__":
    if not OPENROUTER_API_KEY:
        print("FATAL: OPENROUTER_API_KEY environment variable not set.")
    app = App()
    if not OPENROUTER_API_KEY:
        app.status_label.configure(text="FATAL: OPENROUTER_API_KEY environment variable not set.", text_color="red")
        app.set_ui_state(is_enabled=False)
    app.mainloop()