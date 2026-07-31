# -*- coding: utf-8 -*-
"""Today Mode API — aggregated router.

All Today endpoints are mounted under /api/v1 via this single router.
Sub-routers are defined in sibling modules.
"""

from fastapi import APIRouter

from app.api.v1.today import courses, exams, overview, suggestion, sync, import_

router = APIRouter(tags=["today"])

router.include_router(courses.router,    prefix="/courses",  tags=["courses"])
router.include_router(exams.router,      prefix="/exams",    tags=["exams"])
router.include_router(overview.router,   prefix="/today",    tags=["today"])
router.include_router(suggestion.router, prefix="/today",    tags=["today"])
router.include_router(sync.router,       prefix="/today",    tags=["today"])
router.include_router(import_.router,    prefix="/today",    tags=["today"])
