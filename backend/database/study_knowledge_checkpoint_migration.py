"""Create durable page checkpoints for resumable direct Study extraction."""
from models.study import StudyKnowledgePageCheckpoint


def migrate_study_knowledge_checkpoints(engine):
    StudyKnowledgePageCheckpoint.__table__.create(engine, checkfirst=True)
