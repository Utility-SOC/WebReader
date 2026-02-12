# WebReader (Refactored)

A modern, containerized web application for speed reading PDF and EPUB files.

## Architecture

- **Frontend**: React + Vite (Port 5173)
- **Backend**: FastAPI + Python 3.9 (Port 8000)
- **Worker**: Celery + Redis (Background processing)
- **Database**: SQLite (Persisted in `./data`)

## Prerequisites

- Git
- Docker & Docker Compose

## Quick Start (Linux/Docker)

1. **Clone the repository** (Refactor branch):
   ```bash
   git clone -b refactor https://github.com/Utility-SOC/WebReader.git
   cd WebReader
   ```

2. **Run with Docker Compose**:
   ```bash
   docker-compose up --build -d
   ```

3. **Access the Application**:
   - Frontend: [http://localhost:5173](http://localhost:5173)
   - API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Troubleshooting

- **Permissions**: Ensure the `temp_uploads`, `layouts`, and `data` directories are writable by the container user.
  ```bash
  chmod -R 777 temp_uploads layouts data
  ```
- **Logs**: Check logs for specific services:
  ```bash
  docker-compose logs -f backend
  docker-compose logs -f worker
  ```
