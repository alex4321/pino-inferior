# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/03_models.ipynb.

# %% auto 0
__all__ = ['aengine', 'Base', 'ParagraphMemoryRecord']

# %% ../nbs/03_models.ipynb 1
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, Text, String, JSON, DateTime, UniqueConstraint, create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from .core import SQLALCHEMY_CONNECTION_STRING

# %% ../nbs/03_models.ipynb 2
aengine = create_async_engine(url=SQLALCHEMY_CONNECTION_STRING)

# %% ../nbs/03_models.ipynb 3
Base = declarative_base()

# %% ../nbs/03_models.ipynb 4
class ParagraphMemoryRecord(Base):
    __tablename__ = "memory_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(Text)
    meta = Column(JSON)
    md5 = Column(String(64))
    created_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint('md5', 'text', name='_md5_text_uc'),
    )

