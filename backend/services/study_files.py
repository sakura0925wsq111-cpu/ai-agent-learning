"""Streaming validation and private local storage for Study source files."""

from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from core.config import PROJECT_ROOT, settings
from core.exceptions import ValidationException


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")
_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StoredStudyFile:
    original_filename: str
    file_type: str
    suffix: str
    size: int
    sha256: str
    storage_path: str


def _clean_filename(filename: str | None) -> str:
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or "\x00" in name:
        raise ValidationException("文件名不能为空")
    if len(name) > 255:
        raise ValidationException("文件名不能超过 255 个字符")
    return name


def _validated_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".pptx"}:
        raise ValidationException("仅支持 PDF 或 PPTX 文件")
    return suffix


def _validate_file_structure(path: Path, suffix: str) -> None:
    with path.open("rb") as source:
        header = source.read(8)
    if suffix == ".pdf" and not header.startswith(b"%PDF-"):
        raise ValidationException("文件内容不是有效的 PDF 格式")
    if suffix == ".pptx":
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except (OSError, zipfile.BadZipFile) as exc:
            raise ValidationException("文件内容不是有效的 PPTX 格式") from exc
        if not {"[Content_Types].xml", "ppt/presentation.xml"}.issubset(names):
            raise ValidationException("文件内容不是有效的 PPTX 格式")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


class LocalStudyStorage:
    """Store uploads outside static assets using server-generated paths."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        configured = Path(base_dir or settings.study_upload_dir)
        self.base_dir = (
            configured if configured.is_absolute() else PROJECT_ROOT / configured
        ).resolve()

    @staticmethod
    def _check_segment(value: str) -> str:
        if not _SAFE_SEGMENT.fullmatch(value):
            raise ValueError("storage path segment contains unsupported characters")
        return value

    def _target(
        self,
        *,
        user_id: str,
        document_id: str,
        suffix: str,
    ) -> tuple[str, Path]:
        safe_user_id = self._check_segment(user_id)
        safe_document_id = self._check_segment(document_id)
        if suffix not in {".pdf", ".pptx"}:
            raise ValueError("unsupported study file suffix")
        relative_path = PurePosixPath(safe_user_id) / f"{safe_document_id}{suffix}"
        return relative_path.as_posix(), self.base_dir.joinpath(*relative_path.parts)

    async def store_upload(
        self,
        *,
        upload: UploadFile,
        user_id: str,
        document_id: str,
    ) -> StoredStudyFile:
        """Stream an upload to disk while enforcing size and calculating SHA-256."""
        original_filename = _clean_filename(upload.filename)
        suffix = _validated_suffix(original_filename)
        relative_path, target = self._target(
            user_id=user_id,
            document_id=document_id,
            suffix=suffix,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".uploading")
        digest = hashlib.sha256()
        total = 0

        try:
            with temporary.open("xb") as output:
                while chunk := await upload.read(_CHUNK_SIZE):
                    total += len(chunk)
                    if total > settings.study_upload_max_bytes:
                        limit_mb = settings.study_upload_max_bytes // (1024 * 1024)
                        raise ValidationException(f"学习资料不能超过 {limit_mb} MB")
                    digest.update(chunk)
                    output.write(chunk)
            if total == 0:
                raise ValidationException("上传文件为空")
            _validate_file_structure(temporary, suffix)
            if target.exists():
                raise FileExistsError("study upload target already exists")
            temporary.rename(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        return StoredStudyFile(
            original_filename=original_filename,
            file_type=suffix.removeprefix("."),
            suffix=suffix,
            size=total,
            sha256=digest.hexdigest(),
            storage_path=relative_path,
        )

    def resolve(self, relative_path: str) -> Path:
        target = (self.base_dir / Path(relative_path)).resolve()
        if target != self.base_dir and self.base_dir not in target.parents:
            raise ValueError("storage path escapes the configured directory")
        return target

    def delete(self, relative_path: str) -> None:
        self.resolve(relative_path).unlink(missing_ok=True)


__all__ = ["LocalStudyStorage", "StoredStudyFile", "sha256_file"]
