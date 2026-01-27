# Scientific Speed Reader - Setup Guide

## How to Run

1.  **Install Python**: Download and install Python 3.9+ from [python.org](https://www.python.org/downloads/).
    *   **Important**: Check the box **"Add Python to PATH"** during installation.
2.  **Start the App**: Double-click `run_windows.bat` in this folder.
    *   The script will automatically set up the environment, install dependencies, and check for Tesseract OCR.
    *   It will open your web browser to the application automatically.

## Configuration

To change the port (default: 8182):

1.  Right-click `run_windows.ps1` (not the .bat file) and select **Edit**.
2.  Find the line: `$port = 8182`.
3.  Change the number to your desired port.
4.  Save and restart `run_windows.bat`.

## How to Use

1.  **Dashboard**: The main screen shows your library of recent files. Click a file to open it.
2.  **Reading a Text/PDF**:
    *   **Upload**: Drag and drop a PDF, EPUB, or Text file into the upload zone.
    *   **Speed Reader**: The text will be displayed one word at a time.
    *   **Controls**:
        *   **Spacebar**: Play / Pause
        *   **Up/Down Arrow**: Increase / Decrease WPM (Words Per Minute)
        *   **Left/Right Arrow**: Jump back / forward in text
3.  **PDF Layout Editor**:
    *   If a PDF has complex layouts (columns, sidebars), the app may ask you to confirm the reading order.
    *   Draw boxes around the text blocks in the order you want them read.
    *   Click "Save Layout" to process the file.

## Troubleshooting

*   **OCR Issues**: If image text extraction fails, install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki).
*   **Audio Issues**: Windows uses built-in TTS. Linux requires `espeak` (`sudo apt install espeak`).

## Academic Basis

This application is built upon research in cognitive psychology and reading mechanics:

*   **Forster, K. I. (1970)**. *Visual perception of rapidly presented word sequences*. Perception & Psychophysics, 8, 215–221. (Basis for RSVP)
*   **Rayner, K. (1998)**. *Eye movements in reading and information processing: 20 years of research*. Psychological Bulletin, 124(3), 372–422. (Optimal Recognition Point)
*   **Miller, G. A. (1956)**. *The magical number seven, plus or minus two: Some limits on our capacity for processing information*. Psychological Review, 63(2), 81–97. (Cognitive Chunking)
*   **Schotter, E. R., Angele, B., & Rayner, K. (2012)**. *Parafoveal processing in reading*. Attention, Perception, & Psychophysics, 74, 5–35. (Typographic Guidance)

## Open Source Attribution

This project leverages the following open source software. We gratefully acknowledge the contributions of their authors.

*   **FastAPI**: Modern, high-performance web framework for APIs. (TIANGOLO, MIT License)
*   **React**: A JavaScript library for building user interfaces. (Meta, MIT License)
*   **Tesseract OCR**: Optical Character Recognition engine. (Google, Apache 2.0)
*   **PDFPlumber**: Plumb a PDF for detailed information. (Jeremy Singer-Vine, MIT License)
*   **Tailwind CSS**: Utility-first CSS framework. (MIT License)
*   **Lucide Icons**: Beautiful & consistent icon toolkit. (ISC License)
*   **OpenDyslexic**: Typeface designed against some symptoms of dyslexia. (Abbie Gonzalez, SIL OFL)
*   **Google Fonts**: Atkinson Hyperlegible, Roboto, etc. (SIL OFL)

