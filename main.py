import tkinter as tk
import logging
import os
from ui import ParserUI

def main():
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    
    # Configure basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),  # Console handler
        ]
    )
    
    # Create the GUI
    root = tk.Tk()
    app = ParserUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()