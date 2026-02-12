from sqlalchemy import Column, Integer, String, DateTime, Enum, JSON, ForeignKey
from sqlalchemy.sql import func
from .database import Base
import enum

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_path = Column(String)
    file_type = Column(String) # pdf, epub, etc.
    upload_date = Column(DateTime(timezone=True), server_default=func.now())
    page_count = Column(Integer, default=0)
    
    # Metadata
    title = Column(String, nullable=True)
    author = Column(String, nullable=True)
    
    # Extracted Content (stored as JSON for simplicity in SQLite)
    # properly we might use a separate table for content, but JSON is fine for MVP
    content = Column(JSON, nullable=True) 

class ProcessingTask(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, index=True) # UUID from Celery
    document_id = Column(Integer, ForeignKey("documents.id"))
    status = Column(String, default=TaskStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)
