# WebReader - Scientific Speed Reader

A modern web application for speed reading PDFs, EPUBs, and Images using RSVP (Rapid Serial Visual Presentation) technology.

![WebReader UI](https://via.placeholder.com/800x450.png?text=WebReader+Preview)

## Features

- **RSVP Speed Reading**: Read faster by eliminating eye movement.
- **Format Support**: PDF, EPUB, TXT, DOCX, and **Images** (.png, .jpg, .webp).
- **OCR Integration**: Automatically extracts text from scanned PDFs and images using Tesseract.
- **Text-to-Speech (TTS)**: Generate and download an MP3 audio version of your document.
- **Manual Layout Editor**: Select specific text boxes to read on PDF files, skipping headers/footers.
- **Premium UI**: Modern, glassmorphism-based design with Dark Mode support.
- **Image Gallery**: View and download images extracted from your documents.

## Installation

### Prerequisites

- Python 3.9+, Node.js, Redis, and Tesseract OCR

### 1. Clone the Repository

```bash
git clone https://github.com/Utility-SOC/WebReader.git
cd WebReader
```

## Running the Application

We've provided automated startup scripts to install dependencies and launch all necessary services (Backend, Frontend, and Celery Worker).

**For Windows:**
```powershell
# Open PowerShell and run:
.\run_windows.ps1

# Or simply double-click run_windows.bat
```

**For Linux / macOS:**
```bash
# Make the script executable and run:
chmod +x run_linux.sh
./run_linux.sh
```

*Note: Ensure Redis is running in the background before launching the application.*

## Basic Tutorial

WebReader is designed to be intuitive and fast. Here is how to use the core features:

### 1. Uploading a Document
- Click the **upload area** on the main screen to select a supported document (PDF, EPUB, TXT, DOCX, or Image).
- **PDF Manual Extraction**: If you upload a PDF, you'll be asked if you want to use the Manual Editor. This allows you to draw boxes around the text you want to read, automatically skipping headers, footers, and page numbers.

### 2. Reading with RSVP
- **Play/Pause**: Once processing is complete, press the large **Play** button (or click anywhere in the reading area) to start Rapid Serial Visual Presentation.
- **Navigation**: Use the **Left/Right arrows** to skip backward or forward by 50 words.
- **Progress Bar**: Drag the scrubber at the bottom to jump to any point in the text.

### 3. Customizing the Experience
- Click the **Gear icon** in the top right to open **Settings**.
- **Speed**: Adjust your target Words Per Minute (WPM) and the number of words shown at once (Chunk Size).
- **Appearance**: Change fonts, text size, and the width of the reading area.
- **Dynamic Punctuation**: WebReader slows down slightly at commas, periods, and paragraphs. You can tweak these delays in the settings.

### 4. Advanced Features
- **Chapters (Book Icon)**: When reading an EPUB, click the book icon to navigate directly to specific chapters.
- **Gallery (Image Icon)**: If your document contains illustrations or figures, click the image icon to view them in a dedicated gallery.
- **Downloads**: 
  - Click the **Document icon** to download a clean text transcript (`.txt`) of your file.
  - Click the **Volume icon** to generate and download an MP3 audiobook using Text-to-Speech (TTS).

## Troubleshooting

- **Upload Stuck?**: Ensure the worker process started correctly from the launch script. The API delegates heavy processing to Celery.
- **OCR Failed?**: Ensure `tesseract` is installed and in your system PATH.

## License

MIT
