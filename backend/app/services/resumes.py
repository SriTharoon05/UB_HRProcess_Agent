"""Bounded document validation, full-text extraction and private resume storage."""

from __future__ import annotations

import asyncio
import io
import logging
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
from app.observability import log_event, traced


MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
REFERENCE = re.compile(r"^(local|azure):([a-f0-9]{32}\.(?:pdf|docx))$")


@traced("resume.filename_validation")
def sanitize_filename(filename: str) -> str:
    """Keep a human-readable filename for metadata; never use it as a storage path."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^\w. ()-]", "_", name, flags=re.UNICODE).strip(" .")
    if not name or len(name) > 255:
        log_event("resume.filename_validation", "rejected", level=logging.WARNING, reason="safe_filename_length_invalid")
        raise ResumeValidationError("Resume filename must contain 1 to 255 safe characters.")
    return name


class ResumeService:
    def __init__(self, settings: Any, *, blob_client: Any = None):
        self.settings = settings
        self.blob_client = blob_client

    @traced("resume.docx_archive_validation")
    def _docx_archive(self, data: bytes) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                log_event("resume.docx_archive_entries", "received", count=len(entries))
                if len(entries) > 1000 or len({e.filename for e in entries}) != len(entries):
                    log_event("resume.docx_archive_validation", "rejected", level=logging.WARNING, reason="archive_entry_limit_or_duplicates")
                    raise ResumeValidationError("DOCX contains too many or duplicate archive entries.")
                names = {entry.filename for entry in entries}
                if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                    log_event("resume.docx_archive_validation", "rejected", level=logging.WARNING, reason="required_document_parts_missing")
                    raise ResumeValidationError("File is not a valid DOCX document.")
                maximum = getattr(self.settings, "max_resume_uncompressed_mb", 40) * 1024 * 1024
                if sum(entry.file_size for entry in entries) > maximum:
                    log_event("resume.docx_archive_validation", "rejected", level=logging.WARNING, reason="uncompressed_size_limit")
                    raise ResumeValidationError("DOCX expanded content exceeds the safe processing limit.")
                for entry in entries:
                    if entry.flag_bits & 1:
                        log_event("resume.docx_archive_validation", "rejected", level=logging.WARNING, reason="encrypted_archive")
                        raise ResumeValidationError("Encrypted DOCX archives are not supported.")
                    if entry.filename.startswith("/") or ".." in Path(entry.filename).parts or "\\" in entry.filename:
                        log_event("resume.docx_archive_validation", "rejected", level=logging.WARNING, reason="unsafe_archive_path")
                        raise ResumeValidationError("DOCX archive contains unsafe paths.")
                    if entry.file_size > 1024 * 1024 and entry.file_size / max(entry.compress_size, 1) > 200:
                        log_event("resume.docx_archive_validation", "rejected", level=logging.WARNING, reason="compression_ratio_limit")
                        raise ResumeValidationError("DOCX compression ratio exceeds the safe processing limit.")
                    if entry.filename.lower().endswith(".bin") or "vbaproject" in entry.filename.lower():
                        log_event("resume.docx_archive_validation", "rejected", level=logging.WARNING, reason="embedded_executable_or_macro")
                        raise ResumeValidationError("DOCX macros and embedded executable objects are not supported.")
                # Validate CRC and bounded decompression for every embedded part, not only document.xml.
                if archive.testzip() is not None:
                    log_event("resume.docx_archive_validation", "rejected", level=logging.WARNING, reason="archive_checksum_failed")
                    raise ResumeValidationError("DOCX archive is corrupted.")
                log_event("resume.docx_archive_validation", "validated", count=len(entries), validated=True)
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            log_event("resume.docx_archive_validation", "failed", level=logging.WARNING, reason="archive_unreadable", exception_type=type(exc).__name__)
            raise ResumeValidationError("DOCX document is corrupted or unreadable.") from exc

    @traced("resume.upload_validation")
    def validate_upload(self, data: bytes, filename: str, content_type: str) -> str:
        log_event("resume.upload_limits", "start", bytes_count=len(data))
        filename = sanitize_filename(filename)
        extension = Path(filename).suffix.lower()
        if extension not in MIME_TYPES:
            log_event("resume.upload_limits", "rejected", level=logging.WARNING, reason="unsupported_extension")
            raise ResumeValidationError("Upload a PDF or DOCX resume.")
        if not data:
            log_event("resume.upload_limits", "rejected", level=logging.WARNING, reason="empty_document")
            raise ResumeValidationError("Resume file is empty.")
        if len(data) > self.settings.max_resume_size_mb * 1024 * 1024:
            log_event("resume.upload_limits", "rejected", level=logging.WARNING, reason="document_size_limit", bytes_count=len(data))
            raise ResumeValidationError(f"Resume must be smaller than {self.settings.max_resume_size_mb} MB.")
        mime = content_type.partition(";")[0].strip().lower()
        if mime != MIME_TYPES[extension]:
            log_event("resume.upload_limits", "rejected", level=logging.WARNING, reason="mime_extension_mismatch")
            raise ResumeValidationError("Resume MIME type does not match its file extension.")
        log_event("resume.upload_limits", "completed", bytes_count=len(data), validated=True, mode=extension.lstrip("."))
        if extension == ".pdf":
            log_event("resume.pdf_validation", "start")
            if not data.startswith(b"%PDF-"):
                log_event("resume.pdf_validation", "rejected", level=logging.WARNING, reason="pdf_signature_invalid")
                raise ResumeValidationError("File contents are not a PDF.")
            try:
                with fitz.open(stream=data, filetype="pdf") as document:
                    if document.is_encrypted:
                        log_event("resume.pdf_validation", "rejected", level=logging.WARNING, reason="pdf_encrypted")
                        raise ResumeValidationError("Password-protected PDF resumes are not supported.")
                    if document.page_count == 0 or document.page_count > 200:
                        log_event("resume.pdf_validation", "rejected", level=logging.WARNING, reason="pdf_page_limit", count=document.page_count)
                        raise ResumeValidationError("Resume PDF must contain between 1 and 200 pages.")
                    log_event("resume.pdf_validation", "completed", count=document.page_count, validated=True)
            except (fitz.FileDataError, RuntimeError, ValueError) as exc:
                log_event("resume.pdf_validation", "failed", level=logging.WARNING, exception_type=type(exc).__name__)
                if isinstance(exc, ResumeValidationError):
                    raise
                raise ResumeValidationError("PDF document is corrupted or unreadable.") from exc
        else:
            log_event("resume.docx_validation", "start")
            if not data.startswith(b"PK\x03\x04"):
                log_event("resume.docx_validation", "rejected", level=logging.WARNING, reason="docx_signature_invalid")
                raise ResumeValidationError("File contents are not a DOCX archive.")
            self._docx_archive(data)
            try:
                Document(io.BytesIO(data))
                log_event("resume.docx_validation", "completed", validated=True)
            except Exception as exc:
                log_event("resume.docx_validation", "failed", level=logging.WARNING, reason="docx_parse_failed", exception_type=type(exc).__name__)
                raise ResumeValidationError("DOCX document is corrupted or unreadable.") from exc
        return extension

    @traced("resume.text_extraction")
    def extract(self, data: bytes, filename: str) -> str:
        extension = Path(sanitize_filename(filename)).suffix.lower()
        if extension not in MIME_TYPES:
            raise ResumeValidationError("Only PDF and DOCX extraction is supported.")
        self.validate_upload(data, filename, MIME_TYPES[extension])
        log_event("resume.document_parse", "start", mode=extension.lstrip("."), bytes_count=len(data))
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
            log_event("resume.document_parse", "failed", level=logging.WARNING, exception_type=type(exc).__name__)
            raise ResumeValidationError("Resume text extraction failed; upload a readable PDF or DOCX.") from exc
        if not text.strip():
            log_event("resume.document_parse", "rejected", level=logging.WARNING, reason="no_extractable_text", text_chars=0)
            raise ResumeValidationError("Resume has no extractable text. Scanned PDFs require OCR; upload a text-based document.")
        log_event("resume.document_parse", "completed", mode=extension.lstrip("."), text_chars=len(text.strip()))
        return text.strip()

    @traced("resume.local_storage_validation")
    def _local_root(self) -> Path:
        if not self.settings.demo_mode:
            log_event("resume.local_storage_validation", "rejected", level=logging.ERROR, reason="local_storage_requires_demo_mode")
            raise ConfigurationError("Local resume storage is allowed only in demo mode. Configure private Azure Blob Storage.")
        root = Path(self.settings.local_resume_dir)
        if root.is_symlink():
            log_event("resume.local_storage_validation", "rejected", level=logging.ERROR, reason="storage_root_is_symlink")
            raise ConfigurationError("Local resume storage must not be a symbolic link.")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        return root.resolve()

    @traced("resume.azure_operation")
    async def _azure_operation(self, operation: str, key: str, data: bytes | None = None) -> Any:
        log_event("resume.storage_configuration", "start", storage="azure")
        if not self.settings.azure_storage_connection_string and self.blob_client is None:
            log_event("resume.storage_configuration", "failed", level=logging.ERROR, storage="azure", reason="private_blob_storage_not_configured")
            raise ConfigurationError("Private Azure Blob Storage is required in connected mode.")
        log_event("resume.storage_configuration", "completed", storage="azure")

        async def perform(service: Any) -> Any:
            operation_stage = "resume.private_container_validation"
            try:
                log_event("resume.private_container_validation", "start", storage="azure")
                container = service.get_container_client(self.settings.azure_storage_container)
                properties = await container.get_container_properties()
                public_access = properties.get("public_access") if isinstance(properties, dict) else getattr(properties, "public_access", None)
                if public_access:
                    log_event("resume.private_container_validation", "rejected", level=logging.ERROR, storage="azure", reason="container_public_access_enabled")
                    raise ConfigurationError("Resume storage container must have public access disabled.")
                log_event("resume.private_container_validation", "completed", storage="azure", validated=True)
                blob = container.get_blob_client(key)
                if operation == "store":
                    operation_stage = "resume.blob_store"
                    log_event("resume.blob_store", "start", storage="azure", bytes_count=len(data or b""))
                    await blob.upload_blob(
                        data, overwrite=False,
                        content_settings=ContentSettings(content_type=MIME_TYPES[Path(key).suffix]),
                    )
                    log_event("resume.blob_store", "completed", storage="azure", bytes_count=len(data or b""))
                    return None
                if operation == "read":
                    operation_stage = "resume.blob_read"
                    log_event("resume.blob_read", "start", storage="azure")
                    properties = await blob.get_blob_properties()
                    size = properties.get("size") if isinstance(properties, dict) else properties.size
                    if size > self.settings.max_resume_size_mb * 1024 * 1024:
                        log_event("resume.blob_read", "rejected", level=logging.WARNING, storage="azure", reason="stored_document_size_limit", bytes_count=size)
                        raise IntegrationError("Stored resume exceeds the configured document size limit", retryable=False)
                    downloader = await blob.download_blob()
                    loaded = await downloader.readall()
                    log_event("resume.blob_read", "completed", storage="azure", bytes_count=len(loaded))
                    return loaded
                operation_stage = "resume.blob_delete"
                log_event("resume.blob_delete", "start", storage="azure")
                await blob.delete_blob()
                log_event("resume.blob_delete", "completed", storage="azure")
                return None
            except AzureError as exc:
                log_event(operation_stage, "failed", level=logging.WARNING, storage="azure", exception_type=type(exc).__name__, status_code=getattr(exc, "status_code", None))
                raise IntegrationError("Private resume storage operation failed") from exc

        if self.blob_client is not None:
            return await perform(self.blob_client)
        async with BlobServiceClient.from_connection_string(self.settings.azure_storage_connection_string) as service:
            return await perform(service)

    @traced("resume.store")
    async def store(self, data: bytes, filename: str) -> str:
        extension = Path(sanitize_filename(filename)).suffix.lower()
        self.validate_upload(data, filename, MIME_TYPES.get(extension, ""))
        key = f"{uuid.uuid4().hex}{extension}"
        if self.settings.demo_mode and not self.settings.azure_storage_connection_string:
            log_event("resume.storage_selection", "completed", storage="local", mode="demo")
            root = self._local_root()

            def write() -> None:
                descriptor = os.open(root / key, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)

            log_event("resume.local_write", "start", storage="local", bytes_count=len(data))
            await asyncio.to_thread(write)
            log_event("resume.local_write", "completed", storage="local", bytes_count=len(data))
            return f"local:{key}"
        log_event("resume.storage_selection", "completed", storage="azure")
        await self._azure_operation("store", key, data)
        return f"azure:{key}"

    @traced("resume.reference_validation")
    def _reference(self, reference: str) -> tuple[str, str]:
        match = REFERENCE.fullmatch(reference)
        if not match:
            log_event("resume.reference_validation", "rejected", level=logging.WARNING, reason="storage_reference_invalid")
            raise ResumeValidationError("Resume storage reference is invalid.")
        return match.group(1), match.group(2)

    @traced("resume.read")
    async def read(self, reference: str) -> bytes:
        adapter, key = self._reference(reference)
        log_event("resume.storage_selection", "completed", storage=adapter)
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

        log_event("resume.local_read", "start", storage="local")
        data = await asyncio.to_thread(read_local)
        log_event("resume.local_read", "completed", storage="local", bytes_count=len(data))
        return data

    @traced("resume.delete")
    async def delete(self, reference: str) -> None:
        adapter, key = self._reference(reference)
        log_event("resume.storage_selection", "completed", storage=adapter)
        if adapter == "azure":
            await self._azure_operation("delete", key)
        else:
            log_event("resume.local_delete", "start", storage="local")
            await asyncio.to_thread((self._local_root() / key).unlink, missing_ok=True)
            log_event("resume.local_delete", "completed", storage="local")


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
