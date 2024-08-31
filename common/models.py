# common/models.py
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

Base = declarative_base()

class ClipboardEntry(Base):
    __tablename__ = 'clipboard_entries'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)
    content_type = Column(String)
    text_content = Column(Text, nullable=True)
    image_path = Column(String, nullable=True)
    file_path = Column(String, nullable=True)

