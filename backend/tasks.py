from celery_app import celery_app
from database import SessionLocal
from models import Document, ProcessingTask, TaskStatus
from utils import extract_text_from_pdf_range, process_text, load_epub_manual, extract_text_with_ocr
import os
import logging
from sqlalchemy.orm import Session
import json

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def process_pdf_task(self, document_id: int, manual_boxes: dict = None, extract_images: bool = False, start_page: int = 1, force_ocr: bool = False):
    """
    Background task to process a PDF or other document.
    """
    db: Session = SessionLocal()
    task_record = db.query(ProcessingTask).filter(ProcessingTask.id == self.request.id).first()
    
    if not task_record:
        # Should not happen ideally
        logger.error(f"Task record not found for {self.request.id}")
        return {"error": "Task record not found"}

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

        if doc.file_type == "pdf":
            extracted_text, extracted_images = extract_text_from_pdf_range(
                path, start_page, end_page=None, manual_boxes=manual_boxes, force_ocr=force_ocr
            )
        elif doc.file_type == "epub":
            extracted_text, chapters = load_epub_manual(path)
        else:
             # Basic text fallback (TODO: Add docx support here using utils)
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
        
        return {"status": "success", "word_count": len(words)}

    except Exception as e:
        logger.error(f"Task failed: {e}")
        task_record.status = TaskStatus.FAILED
        task_record.error_message = str(e)
        db.commit()
        raise e
    finally:
        db.close()
