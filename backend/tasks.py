from .database import SessionLocal
from .models import Document, ProcessingTask, TaskStatus
from .utils import extract_text_from_pdf_range, process_text, load_epub_manual, load_mobi_manual, process_image_file
import os
from .celery_app import celery_app
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def process_document_background(self, task_id: str = None, document_id: int = None, manual_boxes: dict = None, extract_images: bool = False, start_page: int = 1, force_ocr: bool = False):
    """
    Celery wrapper for background processing.
    """
    if not task_id: task_id = self.request.id
    process_document_core(task_id, document_id, manual_boxes, extract_images, start_page, force_ocr)

def process_document_core(task_id: str, document_id: int, manual_boxes: dict = None, extract_images: bool = False, start_page: int = 1, force_ocr: bool = False):
    """
    Core processing logic (Database-aware).
    """
    db: Session = SessionLocal()
    task_record = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
    
    if not task_record:
        logger.error(f"Task record not found for {task_id}")
        return

    try:
        task_record.status = TaskStatus.PROCESSING
        db.commit()

        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError("Document not found")

        path = doc.file_path
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

        extracted_text = ""
        extracted_images = []
        chapters = []

        file_type = doc.file_type.lower() if doc.file_type else "unknown"

        if file_type == "pdf":
            extracted_text, extracted_images = extract_text_from_pdf_range(
                path, start_page, end_page=None, manual_boxes=manual_boxes, force_ocr=force_ocr
            )
        elif file_type == "epub":
            extracted_text, chapters = load_epub_manual(path)
        elif file_type == "mobi":
            extracted_text, chapters = load_mobi_manual(path)
        elif file_type in ["jpg", "jpeg", "png", "webp", "image"]:
             extracted_text, extracted_images = process_image_file(path)
        elif file_type == "txt":
             try:
                 with open(path, "r", encoding="utf-8", errors="ignore") as f:
                     extracted_text = f.read()
             except Exception as e:
                 logger.error(f"TXT read error: {e}")
        else:
             # Basic text fallback detection
             pass 

        words = process_text(extracted_text)
        
        # Update Document Content
        doc.content = {
            "text": extracted_text,
            "words": words,
            "images": extracted_images,
            "chapters": chapters,
            "word_count": len(words)
        }
        
        task_record.status = TaskStatus.COMPLETED
        task_record.completed_at = func.now()
        db.commit()
        
        logger.info(f"Task {task_id} completed successfully. Words: {len(words)}")

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        task_record.status = TaskStatus.FAILED
        task_record.error_message = str(e)
        db.commit()
    finally:
        db.close()
