from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile

from app.core.logging import get_logger
from app.core.paths import DATA_DIR

logger = get_logger(__name__)


class SampleResumeIngestionError(RuntimeError):
    pass


class SampleResumeIngestionService:
    def __init__(self) -> None:
        self.base_dir = DATA_DIR / "uploads" / "sample_resumes"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_and_extract(self, job_id: str, files: list[Any]) -> list[dict[str, str]]:
        saved: list[dict[str, str]] = []
        target_dir = self.base_dir / job_id
        target_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            if file is None or not getattr(file, "filename", None):
                continue
            content = await file.read()
            if not content:
                continue

            safe_name = self._safe_filename(str(file.filename))
            stored_name = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
            stored_path = target_dir / stored_name
            stored_path.write_bytes(content)
            logger.info("Saved sample resume upload for job %s -> %s", job_id, stored_path)

            extracted_text = self._extract_text(stored_path, content)
            saved.append(
                {
                    "filename": str(file.filename),
                    "stored_path": str(stored_path),
                    "content": extracted_text.strip(),
                }
            )

        return saved

    @staticmethod
    def _safe_filename(filename: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "_", filename)

    def _extract_text(self, path: Path, content: bytes) -> str:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".csv"}:
            return self._decode_text(content)
        if suffix == ".docx":
            return self._extract_docx(path)
        if suffix == ".pdf":
            return self._extract_pdf(path)
        return self._decode_text(content)

    @staticmethod
    def _decode_text(content: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

    @staticmethod
    def _extract_docx(path: Path) -> str:
        try:
            with ZipFile(path) as archive:
                xml_bytes = archive.read("word/document.xml")
        except Exception as exc:
            raise SampleResumeIngestionError(f"读取 DOCX 失败：{path.name}") from exc

        root = ElementTree.fromstring(xml_bytes)
        texts = [node.text.strip() for node in root.iter() if node.text and node.text.strip()]
        return "\n".join(texts)

    @staticmethod
    def _extract_pdf(path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise SampleResumeIngestionError("未安装 pypdf，暂时无法解析 PDF 简历。") from exc

        try:
            reader = PdfReader(str(path))
            texts = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(texts)
        except Exception as exc:
            raise SampleResumeIngestionError(f"读取 PDF 失败：{path.name}") from exc


sample_resume_ingestion_service = SampleResumeIngestionService()
