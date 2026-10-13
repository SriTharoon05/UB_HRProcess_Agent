"""Bounded document validation, full-text extraction and private resume storage."""

from __future__ import annotations

import asyncio
import io
import os
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pymupdf as fitz
from azure.core.exceptions import AzureError
from azure.storage.blob import ContentSettings
from azure.storage.blob.aio import BlobServiceClient
from docx import Document
from docx.oxml.ns import qn

from app.errors import ConfigurationError, IntegrationError, ResumeValidationError


MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
REFERENCE = re.compile(r"^(local|azure):([a-f0-9]{32}\.(?:pdf|docx))$")


def sanitize_filename(filename: str) -> str:
    """Keep a human-readable filename for metadata; never use it as a storage path."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^\w. ()-]", "_", name, flags=re.UNICODE).strip(" .")
    if not name or len(name) > 255:
        raise ResumeValidationError("Resume filename must contain 1 to 255 safe characters.")
    return name


class ResumeService:
    def __init__(self, settings: Any, *, blob_client: Any = None):
        self.settings = settings
        self.blob_client = blob_client

    def _docx_archive(self, data: bytes) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 1000 or len({e.filename for e in entries}) != len(entries):
                    raise ResumeValidationError("DOCX contains too many or duplicate archive entries.")
                names = {entry.filename for entry in entries}
                if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                    raise ResumeValidationError("File is not a valid DOCX document.")
                maximum = getattr(self.settings, "max_resume_uncompressed_mb", 40) * 1024 * 1024
                if sum(entry.file_size for entry in entries) > maximum:
                    raise ResumeValidationError("DOCX expanded content exceeds the safe processing limit.")
                for entry in entries:
                    if entry.flag_bits & 1:
                        raise ResumeValidationError("Encrypted DOCX archives are not supported.")
                    if entry.filename.startswith("/") or ".." in Path(entry.filename).parts or "\\" in entry.filename:
                        raise ResumeValidationError("DOCX archive contains unsafe paths.")
                    if entry.file_size > 1024 * 1024 and entry.file_size / max(entry.compress_size, 1) > 200:
                        raise ResumeValidationError("DOCX compression ratio exceeds the safe processing limit.")
                    if entry.filename.lower().endswith(".bin") or "vbaproject" in entry.filename.lower():
                        raise ResumeValidationError("DOCX macros and embedded executable objects are not supported.")
                # Validate CRC and bounded decompression for every embedded part, not only document.xml.
                if archive.testzip() is not None:
                    raise ResumeValidationError("DOCX archive is corrupted.")
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            raise ResumeValidationError("DOCX document is corrupted or unreadable.") from exc

    def validate_upload(self, data: bytes, filename: str, content_type: str) -> str:
        filename = sanitize_filename(filename)
        extension = Path(filename).suffix.lower()
        if extension not in MIME_TYPES:
            raise ResumeValidationError("Upload a PDF or DOCX resume.")
        if not data:
            raise ResumeValidationError("Resume file is empty.")
        if len(data) > self.settings.max_resume_size_mb * 1024 * 1024:
            raise ResumeValidationError(f"Resume must be smaller than {self.settings.max_resume_size_mb} MB.")
        mime = content_type.partition(";")[0].strip().lower()
        if mime != MIME_TYPES[extension]:
            raise ResumeValidationError("Resume MIME type does not match its file extension.")
        if extension == ".pdf":
            if not data.startswith(b"%PDF-"):
                raise ResumeValidationError("File contents are not a PDF.")
            try:
                with fitz.open(stream=data, filetype="pdf") as document:
                    if document.is_encrypted:
                        raise ResumeValidationError("Password-protected PDF resumes are not supported.")
                    if document.page_count == 0 or document.page_count > 200:
                        raise ResumeValidationError("Resume PDF must contain between 1 and 200 pages.")
            except (fitz.FileDataError, RuntimeError, ValueError) as exc:
                if isinstance(exc, ResumeValidationError):
                    raise
                raise ResumeValidationError("PDF document is corrupted or unreadable.") from exc
        else:
            if not data.startswith(b"PK\x03\x04"):
                raise ResumeValidationError("File contents are not a DOCX archive.")
            self._docx_archive(data)
            try:
                Document(io.BytesIO(data))
            except Exception as exc:
                raise ResumeValidationError("DOCX document is corrupted or unreadable.") from exc
        return extension

    def extract(self, data: bytes, filename: str) -> str:
        extension = Path(sanitize_filename(filename)).suffix.lower()
        if extension not in MIME_TYPES:
            raise ResumeValidationError("Only PDF and DOCX extraction is supported.")
        self.validate_upload(data, filename, MIME_TYPES[extension])
        try:
            if extension == ".pdf":
                with fitz.open(stream=data, filetype="pdf") as document:
                    text = "\n\n".join(page.get_text("text", sort=True) for page in document)
            else:
                document = Document(io.BytesIO(data))
                chunks = list(_document_text(document))
                # Preserve content in headers and footers as well as paragraphs and tables.
                for section in document.sections:
                    chunks.extend(_document_text(section.header))
                    chunks.extend(_document_text(section.footer))
                text = "\n".join(chunks)
        except Exception as exc:
            raise ResumeValidationError("Resume text extraction failed; upload a readable PDF or DOCX.") from exc
        if not text.strip():
            raise ResumeValidationError("Resume has no extractable text. Scanned PDFs require OCR; upload a text-based document.")
        return text.strip()

    def _local_root(self) -> Path:
        if not self.settings.demo_mode:
            raise ConfigurationError("Local resume storage is allowed only in demo mode. Configure private Azure Blob Storage.")
        root = Path(self.settings.local_resume_dir)
        if root.is_symlink():
            raise ConfigurationError("Local resume storage must not be a symbolic link.")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root.resolve()

    async def _azure_operation(self, operation: str, key: str, data: bytes | None = None) -> Any:
        if not self.settings.azure_storage_connection_string and self.blob_client is None:
            raise ConfigurationError("Private Azure Blob Storage is required in connected mode.")

        async def perform(service: Any) -> Any:
            try:
                container = service.get_container_client(self.settings.azure_storage_container)
                properties = await container.get_container_properties()
                public_access = properties.get("public_access") if isinstance(properties, dict) else getattr(properties, "public_access", None)
                if public_access:
                    raise ConfigurationError("Resume storage container must have public access disabled.")
                blob = container.get_blob_client(key)
                if operation == "store":
                    await blob.upload_blob(
                        data, overwrite=False,
                        content_settings=ContentSettings(content_type=MIME_TYPES[Path(key).suffix]),
                    )
                    return None
                if operation == "read":
                    properties = await blob.get_blob_properties()
                    size = properties.get("size") if isinstance(properties, dict) else properties.size
                    if size > self.settings.max_resume_size_mb * 1024 * 1024:
                        raise IntegrationError("Stored resume exceeds the configured document size limit", retryable=False)
                    downloader = await blob.download_blob()
                    return await downloader.readall()
                await blob.delete_blob()
                return None
            except AzureError as exc:
                raise IntegrationError("Private resume storage operation failed") from exc

        if self.blob_client is not None:
            return await perform(self.blob_client)
        async with BlobServiceClient.from_connection_string(self.settings.azure_storage_connection_string) as service:
            return await perform(service)

    async def store(self, data: bytes, filename: str) -> str:
        extension = Path(sanitize_filename(filename)).suffix.lower()
        self.validate_upload(data, filename, MIME_TYPES.get(extension, ""))
        key = f"{uuid.uuid4().hex}{extension}"
        if self.settings.demo_mode and not self.settings.azure_storage_connection_string:
            root = self._local_root()

            def write() -> None:
                descriptor = os.open(root / key, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)

            await asyncio.to_thread(write)
            return f"local:{key}"
        await self._azure_operation("store", key, data)
        return f"azure:{key}"

    def _reference(self, reference: str) -> tuple[str, str]:
        match = REFERENCE.fullmatch(reference)
        if not match:
            raise ResumeValidationError("Resume storage reference is invalid.")
        return match.group(1), match.group(2)

    async def read(self, reference: str) -> bytes:
        adapter, key = self._reference(reference)
        if adapter == "azure":
            return await self._azure_operation("read", key)
        path = self._local_root() / key

        def read_local() -> bytes:
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(descriptor, "rb") as stream:
                    data = stream.read(self.settings.max_resume_size_mb * 1024 * 1024 + 1)
            except OSError as exc:
                raise IntegrationError("Stored resume is unavailable", retryable=False) from exc
            if len(data) > self.settings.max_resume_size_mb * 1024 * 1024:
                raise IntegrationError("Stored resume exceeds the configured document size limit", retryable=False)
            return data

        return await asyncio.to_thread(read_local)

    async def delete(self, reference: str) -> None:
        adapter, key = self._reference(reference)
        if adapter == "azure":
            await self._azure_operation("delete", key)
        else:
            await asyncio.to_thread((self._local_root() / key).unlink, missing_ok=True)


def _document_text(document: Any):
    # Traverse OOXML rather than only python-docx paragraphs: the high-level API
    # omits text boxes and content controls used by many formatted resumes.
    # Count a text node only in its nearest paragraph to avoid duplicating nested
    # text-box paragraphs. Body, table cells, drawings and controls retain order.
    paragraph_tag = qn("w:p")
    text_tag, break_tag, tab_tag = qn("w:t"), qn("w:br"), qn("w:tab")
    for paragraph in document._element.iter(paragraph_tag):
        fragments = []
        for element in paragraph.iter():
            if element.tag not in {text_tag, break_tag, tab_tag}:
                continue
            parent = element.getparent()
            while parent is not None and parent.tag != paragraph_tag:
                parent = parent.getparent()
            if parent is not paragraph:
                continue
            fragments.append(element.text or "" if element.tag == text_tag else "\n" if element.tag == break_tag else "\t")
        text = "".join(fragments)
        if text.strip():
            yield text
