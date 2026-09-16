"""Add independent choice-question tables without changing legacy card tables."""
from models.study import StudyChoiceQuestion, StudyChoiceQuestionRun


def migrate_study_choice_questions(engine):
    StudyChoiceQuestionRun.__table__.create(engine, checkfirst=True)
    StudyChoiceQuestion.__table__.create(engine, checkfirst=True)
