"""SQLAlchemy models for run metadata and run events."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from .db import Base


class Run(Base):
    __tablename__ = "runs"

    id = Column(String(64), primary_key=True)
    status = Column(String(32), nullable=False, default="CREATED")
    verdict = Column(String(32), nullable=True)
    score = Column(Integer, nullable=True)
    repo_path = Column(String(512), nullable=False)
    base_commit = Column(String(64), nullable=True)
    issue_title = Column(String(512), nullable=False)
    issue_description = Column(Text, nullable=False, default="")
    repro_command = Column(String(1024), nullable=True)
    artifact_dir = Column(String(512), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)


class RunEvent(Base):
    __tablename__ = "run_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False)
    sequence = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)
    event_type = Column(String(32), nullable=False)
    step = Column(String(64), nullable=True)
    status = Column(String(16), nullable=True)
    message = Column(Text, nullable=False, default="")
    payload_json = Column(Text, nullable=True)

    __table_args__ = (Index("ix_run_events_run_sequence", "run_id", "sequence"),)
