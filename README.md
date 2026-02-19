# WebReader - Scientific Speed Reader

A modern, containerized web application for speed reading PDFs, EPUBs, and Images using RSVP (Rapid Serial Visual Presentation) technology.

![WebReader UI](https://via.placeholder.com/800x450.png?text=WebReader+Preview)

## Features

- **RSVP Speed Reading**: Read faster by eliminating eye movement.
- **Format Support**: PDF, EPUB, TXT, DOCX, and **Images** (.png, .jpg, .webp).
- **OCR Integration**: Automatically extracts text from scanned PDFs and images using Tesseract.
- **Premium UI**: Modern, glassmorphism-based design with Dark Mode support.
- **Parallel Processing**: Uses Celery + Redis to handle heavy OCR tasks in the background without blocking the UI.
- **Image Gallery**: View and download images extracted from your documents.

## Architecture

- **Frontend**: React + Vite (Port 5173)
- **Backend**: FastAPI + Python 3.9 (Port 8000)
- **Worker**: Celery (Background Task Processing)
- **Broker**: Redis
- **Database**: SQLite (Persisted in `./data`)

## Installation

### Prerequisites

- **Docker & Docker Compose** (Recommended)
- *OR* Python 3.9+, Node.js, Redis, and Tesseract OCR (for local dev)

### 1. Clone the Repository

```bash
git clone -b testing https://github.com/Utility-SOC/WebReader.git
cd WebReader
# If you already cloned it:
git pull origin testing
```

## Running the Application

### Option A: Docker (Recommended)

This is the easiest way to run the full stack (Frontend, Backend, Worker, Redis).

1.  **Build and Start**:
    ```bash
    docker-compose up --build
    ```
    *Add `-d` to run in detached mode.*

2.  **Access**:
    - **App**: [http://localhost:5173](http://localhost:5173)
    - **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Option B: Local Development

If you prefer running services manually:

1.  **Start Redis**:
    Ensure a Redis server is running on `localhost:6379`.

2.  **Start Backend**:
    ```bash
    cd backend
    pip install -r requirements.txt
    python -m main
    ```

3.  **Start Celery Worker**:
    ```bash
    cd backend
    celery -A celery_app worker --loglevel=info
    ```
    *(On Windows, you may need `--pool=solo`)*.

4.  **Start Frontend**:
    ```bash
    cd frontend
    npm install
    npm run dev
    ```

## Usage

1.  **Upload**: Click "Select Document" to upload a PDF, EPUB, or Image.
2.  **Process**: The system will upload the file and start processing.
    - *Note: Large scanned PDFs may take a moment for OCR.*
3.  **Read**: Use the playback controls (Play/Pause) or arrow keys to control reading speed.
4.  **Gallery**: If images are detected in your document, click the "Image" icon to view the gallery.
5.  **Chapters**: For EPUBs, use the "Book" icon to navigate chapters.

## Troubleshooting

- **Upload Stuck?**: Ensure the `worker` container/process is running. The API delegates processing to Celery.
- **OCR Failed?**: Ensure `tesseract` is installed and in your system PATH (or configured in `backend/utils.py`). Docker image handles this automatically.
- **Permissions**: If running via Docker on Linux, ensure `./temp_uploads` and `./data` are writable.

## License

MIT
