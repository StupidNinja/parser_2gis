import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox, filedialog
import threading
import logging
import datetime
import os
import re
from urllib.parse import urlparse

class ParserUI:
    def __init__(self, root):
        self.root = root
        self.root.title("2GIS Parser")
        self.root.geometry("900x650")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.parser = None
        self.parser_thread = None
        self.review_parser_thread = None
        self.reviews_active = False
        
        self._create_ui()
        self._configure_logging()
        
    def _create_ui(self):
        # Create frames
        self.frame_top = ttk.LabelFrame(self.root, text="Search Options", padding=10)
        self.frame_top.pack(fill=tk.X, padx=10, pady=5)
        
        self.frame_reviews = ttk.LabelFrame(self.root, text="Reviews Options", padding=10)
        self.frame_reviews.pack(fill=tk.X, padx=10, pady=5)
        
        self.frame_log = ttk.LabelFrame(self.root, text="Log", padding=10)
        self.frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.frame_status = ttk.Frame(self.root, padding=(5, 2))
        self.frame_status.pack(fill=tk.X, padx=10, pady=5)
        
        # Top frame elements - Search or Direct URL
        ttk.Label(self.frame_top, text="Search Query:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.entry_query = ttk.Entry(self.frame_top, width=50)
        self.entry_query.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        ttk.Label(self.frame_top, text="OR Direct URL:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.entry_url = ttk.Entry(self.frame_top, width=50)
        self.entry_url.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        self.btn_start = ttk.Button(self.frame_top, text="Start Parsing", command=self.start_parsing)
        self.btn_start.grid(row=0, column=2, rowspan=2, padx=5, pady=5, sticky=tk.N+tk.S)
        
        self.btn_stop = ttk.Button(self.frame_top, text="Stop", command=self.stop_parsing, state=tk.DISABLED)
        self.btn_stop.grid(row=0, column=3, rowspan=2, padx=5, pady=5, sticky=tk.N+tk.S)
        
        # Configure grid weights for top frame
        self.frame_top.columnconfigure(1, weight=1)
        
        # Reviews frame elements
        self.var_scrape_reviews = tk.BooleanVar(value=True)
        self.chk_scrape_reviews = ttk.Checkbutton(
            self.frame_reviews, 
            text="Scrape Reviews", 
            variable=self.var_scrape_reviews,
            command=self.toggle_review_options
        )
        self.chk_scrape_reviews.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(self.frame_reviews, text="Max reviews per place:").grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        self.entry_max_reviews = ttk.Entry(self.frame_reviews, width=5)
        self.entry_max_reviews.insert(0, "10")
        self.entry_max_reviews.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        
        # Dynamic reviews info that appears during review extraction
        self.review_info_frame = ttk.Frame(self.frame_reviews)
        self.review_info_frame.grid(row=1, column=0, columnspan=4, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(self.review_info_frame, text="Currently fetching reviews for:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.lbl_current_place = ttk.Label(self.review_info_frame, text="", font=("Arial", 10, "bold"))
        self.lbl_current_place.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(self.review_info_frame, text="Reviews found:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.lbl_reviews_count = ttk.Label(self.review_info_frame, text="0/0")
        self.lbl_reviews_count.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(self.review_info_frame, text="Adjust reviews to fetch:").grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        self.entry_adjust_reviews = ttk.Entry(self.review_info_frame, width=5)
        self.entry_adjust_reviews.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W)
        
        self.btn_adjust_reviews = ttk.Button(self.review_info_frame, text="Update", command=self.update_max_reviews)
        self.btn_adjust_reviews.grid(row=1, column=4, padx=5, pady=5, sticky=tk.W)
        
        self.btn_stop_reviews = ttk.Button(self.review_info_frame, text="Stop Reviews Only", command=self.stop_reviews_only)
        self.btn_stop_reviews.grid(row=1, column=5, padx=5, pady=5, sticky=tk.W)
        
        # Hide the review info frame initially
        self.review_info_frame.grid_remove()
        
        # Configure grid weights for reviews frame
        self.frame_reviews.columnconfigure(3, weight=1)
        
        # Log frame elements
        self.log_text = scrolledtext.ScrolledText(self.frame_log, state='disabled', height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Tags for coloring log messages
        self.log_text.tag_configure('info', foreground='black')
        self.log_text.tag_configure('warning', foreground='orange')
        self.log_text.tag_configure('error', foreground='red')
        self.log_text.tag_configure('success', foreground='green')
        
        # Status bar
        self.status_bar = ttk.Label(self.frame_status, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill=tk.X)
    
    def toggle_review_options(self):
        """Enable/disable review options based on checkbox"""
        state = "normal" if self.var_scrape_reviews.get() else "disabled"
        self.entry_max_reviews.config(state=state)
    
    def _configure_logging(self):
        """Configure logging to text widget"""
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        
        # Add handlers if they don't exist
        if not self.logger.handlers:
            # Text handler
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
            
            # File handler for persistent logs
            try:
                os.makedirs("logs", exist_ok=True)
                log_filename = f"logs/parser_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                file_handler = logging.FileHandler(log_filename)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            except:
                pass
    
    def log_to_ui(self, message, level='info'):
        """Add message to log text widget"""
        tag = level  # Use level as tag for coloring
        
        # Use after method to ensure thread safety
        self.root.after(0, self._append_to_log, message, tag)
    
    def _append_to_log(self, message, tag):
        """Thread-safe method to append text to log"""
        self.log_text.configure(state='normal')
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        self.log_text.insert(tk.END, f"{timestamp} - {message}\n", tag)
        self.log_text.configure(state='disabled')
        self.log_text.see(tk.END)  # Auto-scroll to the end
    
    def set_status(self, status):
        """Update status bar"""
        self.root.after(0, self._update_status, status)
    
    def _update_status(self, status):
        """Thread-safe method to update status"""
        self.status_bar.config(text=status)
    
    def update_reviews_info(self, place_name, current_count, max_count):
        """Update the reviews information display"""
        self.root.after(0, self._update_reviews_ui, place_name, current_count, max_count)
    
    def _update_reviews_ui(self, place_name, current_count, max_count):
        """Thread-safe method to update reviews UI"""
        # Show the review info frame if it's hidden
        if not self.review_info_frame.winfo_viewable():
            self.review_info_frame.grid()
        
        self.lbl_current_place.config(text=place_name)
        self.lbl_reviews_count.config(text=f"{current_count}/{max_count}")
        
        # Update the adjust entry with the current max if it's empty
        if not self.entry_adjust_reviews.get():
            self.entry_adjust_reviews.delete(0, tk.END)
            self.entry_adjust_reviews.insert(0, str(max_count))
    
    def update_max_reviews(self):
        """Update the maximum number of reviews to fetch"""
        if not self.parser or not self.reviews_active:
            return
        
        try:
            new_max = int(self.entry_adjust_reviews.get())
            if new_max < 1:
                raise ValueError("Reviews count must be positive")
                
            # Update the parser's max_reviews
            self.parser.max_reviews = new_max
            self.log_to_ui(f"Updated maximum reviews to fetch: {new_max}", "info")
            
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid positive number")
    
    def validate_inputs(self):
        """Validate user inputs before starting parser"""
        search_query = self.entry_query.get().strip()
        direct_url = self.entry_url.get().strip()
        
        # Either search query or direct URL must be provided
        if not search_query and not direct_url:
            messagebox.showerror("Error", "Please provide either a search query or a direct URL")
            return False
        
        # If direct URL is provided, validate it
        if direct_url:
            # Check if URL is valid
            try:
                parsed = urlparse(direct_url)
                if not parsed.scheme or not parsed.netloc or "2gis" not in parsed.netloc:
                    messagebox.showerror("Error", "Please enter a valid 2GIS URL")
                    return False
            except:
                messagebox.showerror("Error", "Invalid URL format")
                return False
        
        # Validate max reviews if review scraping is enabled
        if self.var_scrape_reviews.get():
            try:
                max_reviews = int(self.entry_max_reviews.get())
                if max_reviews < 1:
                    messagebox.showerror("Error", "Maximum reviews must be at least 1")
                    return False
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid number for maximum reviews")
                return False
        
        return True
    
    def start_parsing(self):
        """Start parsing process"""
        if not self.validate_inputs():
            return
            
        from parser_engine import Parser2GIS
        
        # Get inputs
        search_query = self.entry_query.get().strip()
        direct_url = self.entry_url.get().strip()
        scrape_reviews = self.var_scrape_reviews.get()
        
        try:
            max_reviews = int(self.entry_max_reviews.get()) if scrape_reviews else 0
        except ValueError:
            max_reviews = 10  # Default value
        
        # Update UI
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.entry_query.config(state=tk.DISABLED)
        self.entry_url.config(state=tk.DISABLED)
        self.chk_scrape_reviews.config(state=tk.DISABLED)
        self.entry_max_reviews.config(state=tk.DISABLED)
        
        # Clear log
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')
        
        # Configure review scraping callback
        def on_review_update(place_name, current_count, max_count):
            self.update_reviews_info(place_name, current_count, max_count)
            self.reviews_active = True
        
        # Create parser
        self.parser = Parser2GIS(
            search_query=search_query,
            on_log=self.log_to_ui,
            on_status_change=self.set_status,
            scrape_reviews=scrape_reviews,
            max_reviews=max_reviews, 
            direct_url=direct_url if direct_url else None,
            on_review_update=on_review_update
        )
        
        # Start parsing in a separate thread
        self.parser_thread = threading.Thread(target=self._run_parser_and_update_ui)
        self.parser_thread.daemon = True
        self.parser_thread.start()
    
    def _run_parser_and_update_ui(self):
        """Run the parser and update UI when finished"""
        try:
            self.parser.start()
        except Exception as e:
            self.log_to_ui(f"Error during parsing: {e}", "error")
        finally:
            self.root.after(0, self._update_ui_after_parsing)
    
    def _update_ui_after_parsing(self):
        """Update UI elements after parsing is complete or stopped"""
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.entry_query.config(state=tk.NORMAL)
        self.entry_url.config(state=tk.NORMAL)
        self.chk_scrape_reviews.config(state=tk.NORMAL)
        self.toggle_review_options()  # Reset review options based on checkbox
        
        # Hide review info frame
        self.review_info_frame.grid_remove()
        self.reviews_active = False
        
        # Ask if user wants to open the result
        if hasattr(self.parser, 'output_filename') and self.parser.output_filename:
            if messagebox.askyesno("Parsing Complete", "Do you want to open the results file?"):
                try:
                    os.startfile(self.parser.output_filename)
                except:
                    messagebox.showinfo("Info", f"The file was saved to: {self.parser.output_filename}")
    
    def stop_parsing(self):
        """Stop the parsing process"""
        if self.parser and self.parser.parsing_active:
            self.parser.stop()
            self.btn_stop.config(state=tk.DISABLED)
            self.set_status("Stopping...")
    
    def stop_reviews_only(self):
        """Stop only the review fetching process"""
        if self.parser and self.reviews_active:
            self.parser.stop_reviews()
            self.log_to_ui("Stopping review fetching...", "warning")
            self.btn_stop_reviews.config(state=tk.DISABLED)
    
    def on_closing(self):
        """Handle window closing"""
        if self.parser and self.parser.parsing_active:
            if messagebox.askyesno("Quit", "Parsing is still running. Stop and quit?"):
                self.parser.stop()
                self.root.destroy()
        else:
            self.root.destroy()