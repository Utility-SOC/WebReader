# Scientific Speed Reader - Setup Guide

## How to Install on a New Computer

1.  **Install Python**: Download and install Python 3.9+ from [python.org](https://www.python.org/downloads/).
    *   **Important**: Check the box **"Add Python to PATH"** during installation.
2.  **Copy Files**: Create a folder on the new computer (e.g., `WebReader`) and copy the following files into it:
    *   `backend.py` (The server code)
    *   `index.html` (The application interface)
    *   `requirements.txt` (List of dependencies)
    *   `run_windows.bat` (Launcher for Windows)
    *   `run_linux.sh` (Launcher for Linux/Mac)
    *   `README.md` (This guide)
    *   `layouts/` folder (Optional: preserve your saved PDF layouts)
3.  **Run**: Double-click `run_windows.bat`.
    *   The script will automatically set up the environment and install dependencies.
    *   It will open your web browser to the application.

## How to Change the Port (e.g., to 8182)

By default, the application runs on port `8000`. To change this:

1.  Right-click `run_windows.bat` and select **Edit**.
2.  Find the line near the bottom that says:
    ```bat
    set PORT=8000
    ```
3.  Change `8000` to your desired port (e.g., `8182`).
4.  Save the file and run it again.

## Troubleshooting

*   **OCR Issues**: If image text extraction fails, install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki).
*   **Audio Issues**: Windows uses built-in TTS. Linux requires `espeak` (`sudo apt install espeak`).

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

