"""Owner-scoped review operations. Each mutation commits once or rolls back fully."""
import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import case, func, select, update

from models.study import StudyDocument, StudyKnowledgeRun, StudyKnowledgeUnit as Unit


def owned_units(db, user_id):
    return db.query(Unit).join(StudyDocument, Unit.document_id == StudyDocument.id).filter(StudyDocument.user_id == user_id)


def get_unit(db, user_id, unit_id):
    unit = owned_units(db, user_id).filter(Unit.id == unit_id).populate_existing().first()
    if unit is None:
        raise HTTPException(404, "知识点不存在")
    return unit


def require_run(db, user_id, run_id):
    run = db.query(StudyKnowledgeRun.id).join(StudyDocument).filter(
        StudyKnowledgeRun.id == run_id, StudyDocument.user_id == user_id
    ).first()
    if run is None:
        raise HTTPException(404, "知识点处理记录不存在")


def learning_knowledge_query(db, user_id, run_id=None):
    """The shared eligibility gate for future card and quiz generation."""
    query = owned_units(db, user_id).filter(
        Unit.disposition == "usable", Unit.review_status == "confirmed", Unit.deleted_at.is_(None)
    )
    return query.filter(Unit.run_id == run_id) if run_id is not None else query


def review_statistics(db, user_id, run_id):
    active = Unit.deleted_at.is_(None)
    conditions = [active, active & (Unit.review_status == "pending"),
                  active & (Unit.review_status == "confirmed"), Unit.deleted_at.is_not(None)]
    row = owned_units(db, user_id).filter(Unit.run_id == run_id).with_entities(
        *[func.coalesce(func.sum(case((condition, 1), else_=0)), 0) for condition in conditions]
    ).one()
    return dict(zip(("active_count", "pending_count", "confirmed_count", "deleted_count"), row))


def _mutate(db, user_id, unit_id, version, action, *, content=None, confirm=False, run_id=None):
    unit = get_unit(db, user_id, unit_id)
    if run_id is not None and unit.run_id != run_id:
        raise HTTPException(404, "知识点不存在")
    if unit.version != version:
        raise HTTPException(409, "内容已更新，请刷新后重试")
    confirming = action == "confirm" or (action == "edit" and confirm)
    if confirming and (unit.deleted_at is not None or unit.disposition != "usable"):
        raise HTTPException(409, "仅可确认未删除且机器状态为 usable 的知识点")
    if action != "restore" and unit.deleted_at is not None:
        raise HTTPException(409, "知识点已删除，请先恢复")
    now = datetime.now(timezone.utc)
    values = {"version": Unit.version + 1, "updated_at": now}
    if action == "edit":
        values.update(content=content, content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest())
    if action in {"edit", "confirm", "unconfirm", "restore"}:
        values.update(review_status="confirmed" if confirming else "pending", confirmed_at=now if confirming else None)
    if action in {"delete", "restore"}:
        values["deleted_at"] = now if action == "delete" else None
    statement = update(Unit).where(
        Unit.id == unit_id, Unit.version == version,
        Unit.document_id.in_(select(StudyDocument.id).where(StudyDocument.user_id == user_id)),
    ).values(**values).execution_options(synchronize_session=False)
    if db.execute(statement).rowcount != 1:
        get_unit(db, user_id, unit_id)
        raise HTTPException(409, "内容已更新，请刷新后重试")


def mutate_unit(db, user_id, unit_id, version, action, **kwargs):
    try:
        _mutate(db, user_id, unit_id, version, action, **kwargs)
        result = get_unit(db, user_id, unit_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def confirm_batch(db, user_id, run_id, items):
    try:
        require_run(db, user_id, run_id)
        # Stable lock order avoids deadlocks for overlapping batches.
        for item in sorted(items, key=lambda item: item.id):
            _mutate(db, user_id, item.id, item.version, "confirm", run_id=run_id)
        result = [get_unit(db, user_id, item.id) for item in items]
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
