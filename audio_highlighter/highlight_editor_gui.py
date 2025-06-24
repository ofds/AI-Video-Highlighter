import customtkinter as ctk
import logging
from typing import List, Dict, Callable, Tuple

class HighlightEditorWindow(ctk.CTkToplevel):
    """A Toplevel window for editing and selecting video highlights."""
    
    def __init__(self, master, highlights: List[Dict[str, str]], start_creation_callback: Callable[[List[Tuple[str, str]]], None]):
        super().__init__(master)
        self.transient(master)
        self.grab_set()  # Make the window modal
        self.title("Interactive Highlight Editor")
        self.geometry("900x600")

        self.highlights = highlights
        self.start_creation_callback = start_creation_callback
        self.checkbox_vars = []

        # --- Main Frame ---
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        # --- Top Controls Frame ---
        self.controls_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.controls_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.controls_frame.grid_columnconfigure(1, weight=1)

        self.toggle_button = ctk.CTkButton(self.controls_frame, text="Select/Deselect All", command=self.toggle_all_checkboxes)
        self.toggle_button.grid(row=0, column=0, padx=(0, 20))
        
        self.info_label = ctk.CTkLabel(self.controls_frame, text=f"Found {len(highlights)} potential highlights. Review and select below.", anchor="center")
        self.info_label.grid(row=0, column=1, sticky="ew")

        self.create_video_button = ctk.CTkButton(self.controls_frame, text="Create Highlight Video", command=self.create_video_action, fg_color="green", hover_color="darkgreen")
        self.create_video_button.grid(row=0, column=2, padx=(20, 0))

        # --- Scrollable Frame for Highlights ---
        self.scrollable_frame = ctk.CTkScrollableFrame(self.main_frame, label_text="Select Highlights to Include")
        self.scrollable_frame.grid(row=1, column=0, sticky="nsew")
        self.scrollable_frame.grid_columnconfigure(0, weight=1)

        self.populate_highlights()

    def populate_highlights(self):
        """Dynamically create checkboxes and labels for each highlight."""
        for i, highlight in enumerate(self.highlights):
            var = ctk.BooleanVar(value=True)  # Default to selected
            
            # Frame for each highlight entry
            entry_frame = ctk.CTkFrame(self.scrollable_frame)
            entry_frame.grid(row=i, column=0, sticky="ew", padx=5, pady=(0, 8))
            entry_frame.grid_columnconfigure(1, weight=1)

            check = ctk.CTkCheckBox(entry_frame, text="", variable=var, width=20)
            check.grid(row=0, column=0, rowspan=2, padx=10, pady=10, sticky="ns")
            
            title_text = f"{i+1}. {highlight.get('title', 'No Title')}  ({highlight.get('start_time')} -> {highlight.get('end_time')})"
            title_label = ctk.CTkLabel(entry_frame, text=title_text, font=ctk.CTkFont(weight="bold"), anchor="w")
            title_label.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(5, 0))

            why_label = ctk.CTkLabel(entry_frame, text=f"Reason: {highlight.get('why', 'N/A')}", wraplength=700, anchor="w", justify="left", text_color="gray")
            why_label.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 5))
            
            self.checkbox_vars.append(var)

    def toggle_all_checkboxes(self):
        """Selects or deselects all highlight checkboxes."""
        current_states = [var.get() for var in self.checkbox_vars]
        new_state = not all(current_states)
        for var in self.checkbox_vars:
            var.set(new_state)

    def create_video_action(self):
        """Gathers selected highlights and triggers the video creation process."""
        self.create_video_button.configure(state="disabled", text="Please wait...")
        
        selected_highlights = []
        for i, checkbox_var in enumerate(self.checkbox_vars):
            if checkbox_var.get():
                selected_highlights.append(self.highlights[i])

        if not selected_highlights:
            logging.warning("No highlights were selected. Aborting video creation.")
            self.destroy()  # Close the editor window
            return

        logging.info(f"Confirmed selection of {len(selected_highlights)} highlights for final video.")
        
        # Extract just the time segments needed for the processor
        time_segments = [
            (h['start_time'], h['end_time']) for h in selected_highlights
        ]
        
        # Use the callback to ask the main app to start the creation thread
        self.start_creation_callback(time_segments)
        self.destroy()