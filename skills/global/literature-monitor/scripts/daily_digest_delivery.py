#!/usr/bin/env python3
"""Prepare, validate, attest, and stream a single HTML + PDF arXiv delivery."""

from __future__ import annotations

import argparse
import base64
import email.policy
import email.utils
import hmac
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from pathlib import Path
from typing import Any, BinaryIO, Iterator

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import daily_digest_runtime as runtime


HTML_MAX_BYTES = 90_000
PDF_MAX_BYTES = 10 * 1024 * 1024
MIME_CHUNK_BYTES = 24_000
DELIVERY_FORMAT = "html_pdf_single"
COVERAGE_POLICY = runtime.DAILY_COVERAGE_POLICY
BODY_BEGIN = "DAILY_ARXIV_BODY_BEGIN"
BODY_END = "DAILY_ARXIV_BODY_END"
def pdf_required_sections(digest: dict[str, Any]) -> tuple[str, ...]:
    config = runtime._require_public_configuration()
    if (digest.get("report_category") != config["report_category"]
            or digest.get("public_profile_sha256") != config["_config_sha256"]):
        raise DeliveryValidationError("Report category or profile differs from the bound configuration")
    return (
        "每日总览", "重点推荐论文", "潜在关注论文",
        f"{config['report_category']} Top 50",
        f"其余 {config['report_category']} 更新",
        "已配置分类检索覆盖", "检索和筛选统计",
    )
SELECTED_PAPER_LABELS = (
    "一句话核心结论：",
    "主要研究问题：",
    "方法概述：",
    "主要贡献：",
    "与当前研究的具体关系：",
    "可迁移内容：",
    "局限或验证点：",
    "是否值得精读：",
    "建议 follow：",
)

DELIVERY_MANIFEST_NAME_RE = re.compile(
    r"arxiv-daily-(\d{4}-\d{2}-\d{2})-delivery\.json"
)
FOCUS_PAPER_LABELS = SELECTED_PAPER_LABELS
WATCH_PAPER_LABELS = SELECTED_PAPER_LABELS
SUMMARY_MAX_BYTES = HTML_MAX_BYTES
TRUNCATION_MARKERS = (
    "tokens truncated",
    "characters truncated",
    "chars truncated",
    "content truncated",
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_TRAILER = b"IEND\xaeB`\x82"
GMAIL_RAW_FRAME_MAGIC = "DAXGMR1"
GMAIL_RAW_LINE_FRAME_MAGIC = "DAXGMR2"
RECEIPT_FRAME_MAGIC = "DAXRCP1"
GMAIL_RAW_ATTESTATION_SCHEMA = 1
GMAIL_RAW_VALIDATOR = "gmail_raw_mime_v1"
GMAIL_RAW_METADATA_MAX_BYTES = 4096
GMAIL_RAW_ABSOLUTE_MAX_BYTES = 24 * 1024 * 1024
GMAIL_RAW_MAX_PARTS = 32
GMAIL_RAW_MAX_DEPTH = 8
GMAIL_RAW_LINE_MAX_BYTES = 8 * 1024
FAILURE_DETAIL_MAX_CHARS = 512
MAX_SEND_ATTEMPTS = 2
SEND_AUTHORIZATION_SCOPE = "daily_arxiv_email_to_authenticated_self"
SEND_PROOF_SCHEMA = "daily_arxiv_send_proof_v1"
SEND_REAUTHORIZATION_SCHEMA = "daily_arxiv_send_reauthorization_v1"
SEND_REAUTHORIZATION_DECISION = "send_same_verified_draft_once"
LEGACY_SEND_REAUTHORIZATION_SCHEMA = (
    "daily_arxiv_legacy_send_reauthorization_v1"
)
LEGACY_SEND_REAUTHORIZATION_DECISION = (
    "recover_legacy_unknown_once_after_exact_sent_zero"
)
LEGACY_SEND_REAUTHORIZATION_ORIGIN = "interactive_legacy_unreleased"
LEGACY_RECOVERY_FENCE_SCHEMA = "daily_arxiv_legacy_recovery_fence_v1"
SEND_STATE_SCHEMA = 1
SEND_PROOF_TTL_SECONDS = 900
SEND_REAUTHORIZATION_TTL_SECONDS = 900
GMAIL_SEND_LEASE_TTL_SECONDS = 3600
GMAIL_SEND_WAIT_MAX_SECONDS = 600.0
SEND_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32,256}")
RECEIPT_FAILURE_CODES = frozenset(
    {
        "frame_bad_magic",
        "frame_header_invalid",
        "frame_length_invalid",
        "frame_unexpected_eof",
        "raw_too_large",
        "raw_base64url_invalid",
        "manifest_path_invalid",
        "manifest_invalid",
        "manifest_identity_changed",
        "gmail_connector_tool_missing",
        "gmail_connector_call_error",
        "gmail_connector_is_error",
        "gmail_connector_error_payload",
        "gmail_connector_result_missing",
        "gmail_connector_validation_failed",
        "gmail_connector_pre_dispatch_denied",
        "gmail_send_automatic_retry_blocked",
        "gmail_send_outcome_unknown",
        "local_attestation_process_error",
        "gmail_message_id_mismatch",
        "gmail_label_draft_missing",
        "gmail_label_sent_missing",
        "subject_missing",
        "subject_multiple",
        "subject_mismatch",
        "recipient_missing",
        "recipient_mismatch",
        "mime_parse_defect",
        "mime_part_limit_exceeded",
        "mime_unexpected_leaf",
        "mime_shape_mismatch",
        "mime_header_invalid",
        "html_part_missing",
        "html_part_multiple",
        "html_decode_failed",
        "html_charset_mismatch",
        "html_size_mismatch",
        "html_sha256_mismatch",
        "html_markers_invalid",
        "html_expected_id_missing",
        "html_label_missing",
        "html_truncation_marker",
        "attachment_count_mismatch",
        "pdf_part_missing",
        "pdf_part_multiple",
        "pdf_filename_mismatch",
        "pdf_mime_mismatch",
        "pdf_disposition_mismatch",
        "pdf_decode_failed",
        "pdf_size_mismatch",
        "pdf_sha256_mismatch",
    }
)
CONNECTOR_FAILURE_CODES = frozenset(
    {
        "gmail_connector_tool_missing",
        "gmail_connector_call_error",
        "gmail_connector_is_error",
        "gmail_connector_error_payload",
        "gmail_connector_result_missing",
        "gmail_connector_validation_failed",
        "gmail_connector_pre_dispatch_denied",
        "gmail_send_automatic_retry_blocked",
        "local_attestation_process_error",
    }
)
SEND_REAUTHORIZATION_FAILURE_CODES = frozenset(
    {
        "gmail_connector_pre_dispatch_denied",
        "gmail_send_automatic_retry_blocked",
        "gmail_send_outcome_unknown",
    }
)
SEND_WRITE_AHEAD_FAILURE_CODES = frozenset(
    {"gmail_send_automatic_retry_blocked"}
)
SEND_DISPOSITION_REFINEMENT_FAILURE_CODES = frozenset(
    {
        "gmail_connector_pre_dispatch_denied",
        "gmail_send_outcome_unknown",
    }
)
SEND_DISPOSITION_FAILURE_CODES = frozenset(
    SEND_WRITE_AHEAD_FAILURE_CODES | SEND_DISPOSITION_REFINEMENT_FAILURE_CODES
)
ATTESTATION_BOOL_FIELDS = frozenset(
    {
        "message_id_match",
        "label_verified",
        "subject_verified",
        "recipient_verified",
    }
)
ATTESTATION_INT_FIELDS = frozenset(
    {
        "mime_part_count",
        "html_part_count",
        "html_bytes",
        "attachment_count",
        "pdf_part_count",
        "pdf_bytes",
    }
)
ATTESTATION_TEXT_FIELDS = frozenset(
    {
        "validator",
        "attestation_stage",
        "required_label",
        "html_sha256",
        "pdf_filename",
        "pdf_mime_type",
        "pdf_disposition",
        "pdf_sha256",
    }
)
ATTESTATION_FIELDS = (
    ATTESTATION_BOOL_FIELDS | ATTESTATION_INT_FIELDS | ATTESTATION_TEXT_FIELDS
)


class DeliveryValidationError(runtime.DigestValidationError):
    """Raised when a delivery artifact is incomplete or unsafe to send."""


class GmailRawFrameError(DeliveryValidationError):
    """Raised when a bounded stdin frame cannot be decoded safely."""

    def __init__(self, failure_code: str, detail: str) -> None:
        super().__init__(detail)
        self.failure_code = failure_code


class GmailRawAttestationError(DeliveryValidationError):
    """Raised internally to produce a compact, content-free attestation failure."""

    def __init__(self, failure_code: str, detail: str) -> None:
        super().__init__(detail)
        self.failure_code = failure_code


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _subject(digest: dict[str, Any]) -> str:
    selected = [*digest["focus_papers"], *digest["watch_papers"]]
    title = "今日无高相关论文"
    if selected:
        title = " ".join(str(selected[0]["title"]).split())
        if len(title) > 48:
            title = title[:47].rstrip() + "…"
    return f"[arXiv Daily] {digest['date']}｜重点 {len(digest['focus_papers'])} 篇｜最高相关：{title}"


def _font_paths() -> tuple[Path, Path]:
    candidates = (
        (Path(r"C:\Windows\Fonts\Deng.ttf"), Path(r"C:\Windows\Fonts\Dengb.ttf")),
        (Path(r"C:\Windows\Fonts\msyh.ttc"), Path(r"C:\Windows\Fonts\msyhbd.ttc")),
    )
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            return regular, bold
    raise DeliveryValidationError("DengXian or Microsoft YaHei Chinese fonts are unavailable")


def delivery_preflight() -> dict[str, Any]:
    runtime_preflight = runtime.runtime_environment_preflight()
    missing = list(runtime_preflight["missing"])
    try:
        regular, bold = _font_paths()
    except DeliveryValidationError:
        regular = bold = None
        missing.append("Chinese TrueType font")
    pdftoppm = shutil.which("pdftoppm")
    pdfinfo = shutil.which("pdfinfo")
    if not pdftoppm:
        missing.append("pdftoppm")
    if not pdfinfo:
        missing.append("pdfinfo")
    return {
        "schema_version": runtime.SCHEMA_VERSION,
        "ready": not missing,
        "missing": missing,
        "delivery_format": DELIVERY_FORMAT,
        "message_count": 1,
        "html_max_bytes": HTML_MAX_BYTES,
        "pdf_max_bytes": PDF_MAX_BYTES,
        "mime_chunk_bytes": MIME_CHUNK_BYTES,
        "python_executable": runtime_preflight["python_executable"],
        "python_version": runtime_preflight["python_version"],
        "runtime_fingerprint": runtime_preflight["runtime_fingerprint"],
        "timezone": runtime_preflight["announcement_timezone"],
        "timezone_ready": runtime_preflight["timezone_ready"],
        "timezone_source": runtime_preflight["timezone_source"],
        "timezone_failure_code": runtime_preflight["timezone_failure_code"],
        "font_regular": str(regular) if regular else None,
        "font_bold": str(bold) if bold else None,
        "pdftoppm": pdftoppm,
        "pdfinfo": pdfinfo,
    }


def _register_pdf_fonts() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    regular, bold = _font_paths()
    regular_name = "DailyArxivDeng"
    bold_name = "DailyArxivDengBold"
    if regular_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(regular_name, str(regular)))
    if bold_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(bold_name, str(bold)))
    return regular_name, bold_name


def _paragraph(text: Any) -> str:
    return html.escape(" ".join(str(text or "").split()))


def _build_pdf(digest: dict[str, Any], output: Path) -> None:
    sections = pdf_required_sections(digest)
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    regular, bold = _register_pdf_fonts()
    title = ParagraphStyle("title", fontName=bold, fontSize=20, leading=28, textColor=colors.HexColor("#172033"), alignment=TA_CENTER, spaceAfter=12)
    heading = ParagraphStyle("heading", fontName=bold, fontSize=14, leading=20, textColor=colors.HexColor("#243b64"), spaceBefore=12, spaceAfter=7)
    paper_heading = ParagraphStyle("paper", fontName=bold, fontSize=11, leading=16, textColor=colors.HexColor("#2457c5"), spaceBefore=7, spaceAfter=4)
    body = ParagraphStyle("body", fontName=regular, fontSize=9.5, leading=15, textColor=colors.HexColor("#172033"), spaceAfter=3)
    meta = ParagraphStyle("meta", fontName=regular, fontSize=8.5, leading=13, textColor=colors.HexColor("#667085"), spaceAfter=4)
    label = ParagraphStyle("label", fontName=regular, fontSize=9.2, leading=14, leftIndent=6, spaceAfter=2)
    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title=f"arXiv Daily {digest['date']}", author="VibeResearch literature-monitor")
    story: list[Any] = [Paragraph(f"arXiv Daily · {_paragraph(digest['date'])}", title)]
    story.extend((Paragraph("每日总览", heading), Paragraph(_paragraph(digest["overview"]), body)))
    selected_fields = (
        ("一句话核心结论", "core_conclusion"), ("主要研究问题", "research_problem"),
        ("方法概述", "method_overview"), ("主要贡献", "contributions"),
        ("与当前研究的具体关系", "research_relation"), ("可迁移内容", "transferable_ideas"),
        ("局限或验证点", "limitations"), ("是否值得精读", "worth_reading"),
        ("建议 follow", "follow_up"),
    )
    for section, papers in (("重点推荐论文", digest["focus_papers"]), ("潜在关注论文", digest["watch_papers"])):
        story.append(Paragraph(section, heading))
        if not papers:
            story.append(Paragraph("本次没有达到该阈值的论文。", body))
        for index, paper in enumerate(papers, 1):
            story.append(Paragraph(f"{index}. {_paragraph(paper['title'])}", paper_heading))
            story.append(Paragraph(f"arXiv:{_paragraph(paper['arxiv_id'])} · 相关度 {paper['relevance_score']}/100 · <link href='{_paragraph(paper['arxiv_url'])}'>arXiv 链接</link>", meta))
            for field_label, field in selected_fields:
                story.append(Paragraph(f"<b>{field_label}：</b>{_paragraph(paper[field])}", label))
    story.extend((Paragraph("今日研究趋势", heading), Paragraph("<br/>".join(f"• {_paragraph(value)}" for value in digest["trends"]), body)))
    story.extend((Paragraph("对当前研究的可执行启发", heading), Paragraph("<br/>".join(f"• {_paragraph(value)}" for value in digest["actionable_insights"]), body)))
    story.append(PageBreak())
    story.append(Paragraph(sections[3], heading))
    for index, paper in enumerate(digest["cs_cv_report"]["detailed"], 1):
        story.append(Paragraph(f"{index}. {_paragraph(paper['title'])}", paper_heading))
        story.append(Paragraph(f"arXiv:{_paragraph(paper['arxiv_id'])} · 相关度 {paper['relevance_score']}/100 · <link href='{_paragraph(paper['arxiv_url'])}'>arXiv 链接</link>", meta))
        for field_label, field in (("核心结论", "core_conclusion"), ("研究问题", "research_problem"), ("方法概述", "method_overview"), ("主要贡献", "contributions")):
            story.append(Paragraph(f"<b>{field_label}：</b>{_paragraph(paper[field])}", label))
    story.append(Paragraph(sections[4], heading))
    for index, paper in enumerate(digest["cs_cv_report"]["compact"], len(digest["cs_cv_report"]["detailed"]) + 1):
        story.append(Paragraph(f"{index}. {_paragraph(paper['title'])} · arXiv:{_paragraph(paper['arxiv_id'])} · {paper['relevance_score']}/100", paper_heading))
        story.append(Paragraph(f"{_paragraph(paper['core_conclusion'])} · <link href='{_paragraph(paper['arxiv_url'])}'>arXiv 链接</link>", body))
    story.append(PageBreak())
    story.append(Paragraph(sections[5], heading))
    for entry in digest["retrieval_coverage"]:
        story.append(Paragraph(f"{_paragraph(entry['category'])}：raw={entry['raw_count']}，unique={entry['unique_count']}，complete=true", body))
    story.append(Paragraph("检索和筛选统计", heading))
    stats = digest["stats"]
    story.append(Paragraph("；".join(f"{_paragraph(key)}={value}" for key, value in stats.items()), body))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"覆盖策略：{_paragraph(digest['coverage_policy'])}", meta))
    doc.build(story)


def _all_pdf_ids(digest: dict[str, Any]) -> list[str]:
    papers = [
        *digest["focus_papers"], *digest["watch_papers"],
        *digest["cs_cv_report"]["detailed"], *digest["cs_cv_report"]["compact"],
    ]
    return [str(paper["arxiv_id"]) for paper in papers]


def _smoke_render_pdf_page(pdftoppm: str, pdf_path: Path, number: int) -> None:
    completed = subprocess.run(
        [
            pdftoppm,
            "-f", str(number),
            "-l", str(number),
            "-png",
            "-singlefile",
            "-r", "96",
            str(pdf_path),
        ],
        capture_output=True,
        timeout=45,
        check=False,
    )
    rendered = completed.stdout
    if (
        completed.returncode != 0
        or not rendered.startswith(PNG_SIGNATURE)
        or not rendered.endswith(PNG_TRAILER)
    ):
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        detail = f": {stderr[:300]}" if stderr else ""
        raise DeliveryValidationError(
            f"Poppler failed to render PDF page {number}{detail}"
        )


def _validate_pdf(digest: dict[str, Any], pdf_path: Path, *, smoke_render: bool = True) -> dict[str, Any]:
    from pypdf import PdfReader

    if not pdf_path.is_file() or pdf_path.stat().st_size <= 0:
        raise DeliveryValidationError("PDF attachment is missing or empty")
    if pdf_path.stat().st_size > PDF_MAX_BYTES:
        raise DeliveryValidationError(f"PDF attachment exceeds {PDF_MAX_BYTES} bytes")
    try:
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise DeliveryValidationError(f"PDF cannot be reopened: {exc}") from exc
    if page_count < 1:
        raise DeliveryValidationError("PDF has no pages")
    for section in pdf_required_sections(digest):
        if section not in extracted:
            raise DeliveryValidationError(f"PDF is missing section: {section}")
    for arxiv_id in _all_pdf_ids(digest):
        if arxiv_id not in extracted:
            raise DeliveryValidationError(f"PDF is missing arXiv ID {arxiv_id}")
    rendered_pages: list[int] = []
    if smoke_render:
        pdftoppm = shutil.which("pdftoppm")
        if not pdftoppm:
            raise DeliveryValidationError("pdftoppm is required for PDF render smoke testing")
        page_numbers = sorted({1, max(1, (page_count + 1) // 2), page_count})
        for number in page_numbers:
            _smoke_render_pdf_page(pdftoppm, pdf_path, number)
            rendered_pages.append(number)
    return {
        "pdf_path": str(pdf_path.resolve()),
        "pdf_bytes": pdf_path.stat().st_size,
        "pdf_sha256": _sha256(pdf_path),
        "pdf_pages": page_count,
        "pdf_rendered_pages": rendered_pages,
        "pdf_filename": pdf_path.name,
    }


def _validate_html(digest: dict[str, Any], path: Path) -> dict[str, Any]:
    sections = pdf_required_sections(digest)
    if not path.is_file() or path.stat().st_size <= 0:
        raise DeliveryValidationError("HTML body is missing or empty")
    if path.stat().st_size > HTML_MAX_BYTES:
        raise DeliveryValidationError(f"HTML body exceeds {HTML_MAX_BYTES} UTF-8 bytes")
    text = path.read_text(encoding="utf-8")
    if BODY_BEGIN not in text or BODY_END not in text or text.index(BODY_BEGIN) >= text.index(BODY_END):
        raise DeliveryValidationError("HTML body completeness markers are missing or reversed")
    if 'content="html-pdf-single-v4"' not in text and "content='html-pdf-single-v4'" not in text:
        raise DeliveryValidationError("HTML body format marker is missing")
    if f"<h2>{sections[3]}</h2>" not in text:
        raise DeliveryValidationError("HTML report category heading differs from the bound configuration")
    lowered = text.lower()
    for marker in TRUNCATION_MARKERS:
        if marker in lowered:
            raise DeliveryValidationError(f"HTML body contains truncation marker: {marker}")
    selected = [*digest["focus_papers"], *digest["watch_papers"]]
    for paper in [*selected, *digest["cs_cv_report"]["detailed"]]:
        arxiv_id = str(paper["arxiv_id"])
        if text.count(f"data-arxiv-id='{arxiv_id}'") != 1:
            raise DeliveryValidationError(f"HTML body must contain one card for {arxiv_id}")
    for label in SELECTED_PAPER_LABELS:
        expected = len(selected)
        if label in {"方法概述：", "主要贡献："}:
            expected += len(digest["cs_cv_report"]["detailed"])
        if text.count(label) != expected:
            raise DeliveryValidationError(f"HTML field {label} count must equal selected-paper count")
    return {
        "html_path": str(path.resolve()),
        "html_bytes": path.stat().st_size,
        "html_chars": len(text),
        "html_sha256": _sha256(path),
        "body_begin_marker": BODY_BEGIN,
        "body_end_marker": BODY_END,
    }


def _validate_local_reports(digest: dict[str, Any]) -> None:
    for field in ("inventory_json", "inventory_markdown"):
        path = Path(str(digest["local_reports"][field]))
        if not path.is_file() or path.stat().st_size <= 0:
            raise DeliveryValidationError(f"missing local inventory report: {path}")


def _manifest_value(digest: dict[str, Any], html_record: dict[str, Any], pdf_record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": runtime.SCHEMA_VERSION,
        "coverage_policy": COVERAGE_POLICY,
        "delivery_format": DELIVERY_FORMAT,
        "message_count": 1,
        "validated": True,
        "report_date": digest["date"],
        "subject": _subject(digest),
        "recipient": "me",
        "attachment_count": 1,
        **html_record,
        **pdf_record,
        "inventory_count": int(digest["inventory_summary"]["inventory_count"]),
        "focus": len(digest["focus_papers"]),
        "watch": len(digest["watch_papers"]),
        "cv_top50": len(digest["cs_cv_report"]["detailed"]),
        "cv_compact": len(digest["cs_cv_report"]["compact"]),
        "expected_html_ids": [str(paper["arxiv_id"]) for paper in [*digest["focus_papers"], *digest["watch_papers"], *digest["cs_cv_report"]["detailed"]]],
        "expected_pdf_ids": _all_pdf_ids(digest),
        "selected_field_labels": list(SELECTED_PAPER_LABELS),
        "mime_chunk_bytes": MIME_CHUNK_BYTES,
    }


def validate_delivery_artifacts(
    digest: dict[str, Any], *, summary_html: Path, pdf_path: Path, smoke_render: bool = True
) -> dict[str, Any]:
    """Validate a complete v4 body and attachment without exposing their contents."""

    digest = runtime.canonicalize_digest(digest)
    runtime.validate_digest(digest)
    _validate_local_reports(digest)
    return _manifest_value(
        digest,
        _validate_html(digest, summary_html),
        _validate_pdf(digest, pdf_path, smoke_render=smoke_render),
    )


def prepare_delivery(root: Path, digest: dict[str, Any], *, output_dir: Path | None = None) -> dict[str, Any]:
    runtime.configure_public_runtime(root)
    digest = runtime.canonicalize_digest(digest)
    runtime.validate_digest(digest)
    if digest.get("schema_version") != runtime.SCHEMA_VERSION or digest.get("coverage_policy") != COVERAGE_POLICY:
        raise DeliveryValidationError("single HTML + PDF delivery requires the v4 coverage contract")
    preflight = delivery_preflight()
    if not preflight["ready"]:
        raise DeliveryValidationError("delivery preflight failed: " + ", ".join(preflight["missing"]))
    root = root.resolve()
    output_dir = output_dir.resolve() if output_dir else root / "deliveries"
    output_dir.mkdir(parents=True, exist_ok=True)
    basename = f"arxiv-daily-{digest['date']}"
    html_path = output_dir / f"{basename}.html"
    pdf_path = output_dir / f"{basename}.pdf"
    manifest_path = output_dir / f"{basename}-delivery.json"
    runtime.atomic_write_text(html_path, runtime.render_html(digest))
    _build_pdf(digest, pdf_path)
    _validate_local_reports(digest)
    manifest = _manifest_value(digest, _validate_html(digest, html_path), _validate_pdf(digest, pdf_path))
    runtime.atomic_write_json(manifest_path, manifest)
    runtime.atomic_write_text(output_dir / "latest.html", html_path.read_text(encoding="utf-8"))
    runtime.atomic_write_json(output_dir / "latest-delivery.json", manifest)
    result = copy_manifest(manifest)
    result["manifest"] = str(manifest_path.resolve())
    return result


def copy_manifest(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False))


def attest_existing_delivery(root: Path, digest: dict[str, Any]) -> dict[str, Any]:
    runtime.configure_public_runtime(root)
    digest = runtime.canonicalize_digest(digest)
    runtime.validate_digest(digest)
    output_dir = root.resolve() / "deliveries"
    basename = f"arxiv-daily-{digest['date']}"
    manifest_path = output_dir / f"{basename}-delivery.json"
    if not manifest_path.is_file():
        raise DeliveryValidationError(f"missing delivery manifest: {manifest_path}")
    stored = runtime.read_json(manifest_path)
    html_record = _validate_html(digest, Path(str(stored.get("html_path", ""))))
    pdf_record = _validate_pdf(digest, Path(str(stored.get("pdf_path", ""))))
    attested = _manifest_value(digest, html_record, pdf_record)
    for key in ("html_sha256", "html_bytes", "pdf_sha256", "pdf_bytes", "pdf_pages", "subject"):
        if stored.get(key) != attested.get(key):
            raise DeliveryValidationError(f"stored delivery manifest mismatch: {key}")
    runtime.atomic_write_json(manifest_path, attested)
    runtime.atomic_write_json(output_dir / "latest-delivery.json", attested)
    result = copy_manifest(attested)
    result["manifest"] = str(manifest_path.resolve())
    return result


def read_attested_chunk(path: Path, *, expected_size: int, expected_sha256: str, offset: int, max_bytes: int = MIME_CHUNK_BYTES) -> dict[str, Any]:
    path = path.resolve()
    if max_bytes != MIME_CHUNK_BYTES:
        raise DeliveryValidationError(f"MIME chunks must use exactly {MIME_CHUNK_BYTES} bytes")
    if not path.is_file() or path.stat().st_size != expected_size or _sha256(path) != expected_sha256:
        raise DeliveryValidationError("attested MIME source identity mismatch")
    if offset < 0 or offset > expected_size or offset % MIME_CHUNK_BYTES != 0:
        raise DeliveryValidationError("invalid attested MIME chunk offset")
    with path.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(max_bytes)
    next_offset = offset + len(data)
    return {
        "offset": offset,
        "bytes": len(data),
        "next_offset": next_offset,
        "eof": next_offset == expected_size,
        "base64": base64.b64encode(data).decode("ascii"),
    }


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    value = bytearray()
    while len(value) < size:
        chunk = stream.read(size - len(value))
        if not chunk:
            raise GmailRawFrameError(
                "frame_unexpected_eof",
                f"framed stdin ended after {len(value)} of {size} bytes",
            )
        value.extend(chunk)
    return bytes(value)


def _read_until_marker(stream: BinaryIO, marker: bytes, limit: int) -> bytes:
    value = bytearray()
    while len(value) <= limit:
        chunk = stream.read(1)
        if not chunk:
            raise GmailRawFrameError(
                "frame_unexpected_eof", "framed stdin ended before its marker"
            )
        if chunk == marker:
            return bytes(value)
        value.extend(chunk)
    raise GmailRawFrameError(
        "frame_header_invalid", "framed stdin marker exceeded its size bound"
    )


def _read_exact_segment(stream: BinaryIO, size: int) -> bytes:
    """Read one exact PTY segment, ignoring CR/LF flush bytes before it."""

    first = stream.read(1)
    separators = 0
    while first in {b"\r", b"\n"}:
        separators += 1
        if separators > 2:
            raise GmailRawFrameError(
                "frame_length_invalid",
                "framed stdin contains excess transport separators",
            )
        first = stream.read(1)
    if not first:
        raise GmailRawFrameError(
            "frame_unexpected_eof", "framed stdin ended before its next segment"
        )
    if size == 1:
        return first
    return first + _read_exact(stream, size - 1)


def read_gmail_raw_frame(
    stream: BinaryIO, *, max_raw_bytes: int = GMAIL_RAW_ABSOLUTE_MAX_BYTES
) -> dict[str, Any]:
    """Read one length-bounded metadata + Gmail raw frame without waiting for EOF."""

    prefix = _read_exact(stream, len(GMAIL_RAW_FRAME_MAGIC))
    line_framed = prefix == GMAIL_RAW_LINE_FRAME_MAGIC.encode("ascii")
    if line_framed:
        # ConPTY turns write_stdin's newline into CR and may withhold it from a
        # byte-oriented child.  A printable semicolon therefore terminates the
        # header; CR/LF are only transport flush bytes between exact segments.
        header = prefix + _read_until_marker(stream, b";", 120)
    else:
        header = prefix + stream.readline(128 - len(prefix))
        if not header.endswith(b"\n"):
            raise GmailRawFrameError(
                "frame_header_invalid", "Gmail raw frame header is missing its newline"
            )
    try:
        decoded_header = header.decode("ascii").rstrip("\r\n")
    except UnicodeDecodeError as exc:
        raise GmailRawFrameError(
            "frame_header_invalid", "Gmail raw frame header must be ASCII"
        ) from exc
    contiguous_match = re.fullmatch(r"(\S+) (\d+) (\d+)", decoded_header)
    line_match = re.fullmatch(r"(\S+) (\d+) (\d+) (\d+)", decoded_header)
    if contiguous_match is None and line_match is None:
        raise GmailRawFrameError(
            "frame_header_invalid", "Gmail raw frame header has an invalid shape"
        )
    match = line_match if line_match is not None else contiguous_match
    expected_magic = GMAIL_RAW_LINE_FRAME_MAGIC if line_framed else GMAIL_RAW_FRAME_MAGIC
    if line_framed != (line_match is not None):
        raise GmailRawFrameError(
            "frame_header_invalid", "Gmail raw frame version and shape disagree"
        )
    if match.group(1) != expected_magic:
        raise GmailRawFrameError(
            "frame_bad_magic", "Gmail raw frame magic does not match"
        )
    metadata_size = int(match.group(2))
    raw_size = int(match.group(3))
    if not (1 <= metadata_size <= GMAIL_RAW_METADATA_MAX_BYTES) or raw_size < 1:
        raise GmailRawFrameError(
            "frame_length_invalid", "Gmail raw frame lengths are outside bounds"
        )
    if raw_size > min(max_raw_bytes, GMAIL_RAW_ABSOLUTE_MAX_BYTES):
        raise GmailRawFrameError(
            "raw_too_large", "Gmail raw payload exceeds the attested size bound"
        )
    if not line_framed:
        metadata_bytes = _read_exact(stream, metadata_size)
        raw_bytes = _read_exact(stream, raw_size)
    else:
        raw_line_size = int(line_match.group(4))
        if raw_line_size != GMAIL_RAW_LINE_MAX_BYTES:
            raise GmailRawFrameError(
                "frame_length_invalid", "Gmail raw line size does not match the protocol"
            )

        metadata_bytes = _read_exact_segment(stream, metadata_size)
        raw_parts: list[bytes] = []
        remaining = raw_size
        while remaining:
            expected_size = min(raw_line_size, remaining)
            raw_parts.append(_read_exact_segment(stream, expected_size))
            remaining -= expected_size
        raw_bytes = b"".join(raw_parts)
    try:
        metadata = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GmailRawFrameError(
            "frame_header_invalid", "Gmail raw metadata is not valid JSON"
        ) from exc
    if not isinstance(metadata, dict):
        raise GmailRawFrameError(
            "frame_header_invalid", "Gmail raw metadata must be one object"
        )
    allowed = {
        "message_id",
        "expected_message_id",
        "draft_id",
        "label_ids",
        "profile_email",
    }
    if set(metadata) - allowed:
        raise GmailRawFrameError(
            "frame_header_invalid", "Gmail raw metadata contains unknown fields"
        )
    try:
        raw = raw_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise GmailRawFrameError(
            "raw_base64url_invalid", "Gmail raw payload must be ASCII base64url"
        ) from exc
    return {"metadata": metadata, "raw": raw}


def _bounded_failure_detail(value: Any, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise DeliveryValidationError("ambiguous receipt requires failure_detail")
        return None
    if not isinstance(value, str):
        raise DeliveryValidationError("failure_detail must be a string")
    text = value.strip()
    if not text:
        if required:
            raise DeliveryValidationError("ambiguous receipt requires failure_detail")
        return None
    if len(text) > FAILURE_DETAIL_MAX_CHARS or any(
        ord(character) < 32 for character in text
    ):
        raise DeliveryValidationError(
            f"failure_detail must be one safe line of at most {FAILURE_DETAIL_MAX_CHARS} characters"
        )
    return text


def _normalize_attestation(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - ATTESTATION_FIELDS:
        raise DeliveryValidationError("attestation contains unsupported fields")
    normalized: dict[str, Any] = {}
    for field in ATTESTATION_BOOL_FIELDS:
        observed = value.get(field)
        if observed is not None and not isinstance(observed, bool):
            raise DeliveryValidationError(f"attestation.{field} must be boolean or null")
        normalized[field] = observed
    for field in ATTESTATION_INT_FIELDS:
        observed = value.get(field)
        if observed is not None and (
            isinstance(observed, bool) or not isinstance(observed, int) or observed < 0
        ):
            raise DeliveryValidationError(
                f"attestation.{field} must be a non-negative integer or null"
            )
        normalized[field] = observed
    for field in ATTESTATION_TEXT_FIELDS:
        observed = value.get(field)
        if observed is not None:
            if not isinstance(observed, str) or not observed or len(observed) > 255:
                raise DeliveryValidationError(
                    f"attestation.{field} must be a bounded non-empty string or null"
                )
            if any(ord(character) < 32 for character in observed):
                raise DeliveryValidationError(
                    f"attestation.{field} contains control characters"
                )
        normalized[field] = observed
    if normalized.get("validator") != GMAIL_RAW_VALIDATOR:
        raise DeliveryValidationError("attestation validator is unsupported")
    if normalized.get("attestation_stage") not in {"draft", "sent"}:
        raise DeliveryValidationError("attestation stage is unsupported")
    if normalized.get("required_label") not in {"DRAFT", "SENT"}:
        raise DeliveryValidationError("attestation required_label is unsupported")
    for field in ("html_sha256", "pdf_sha256"):
        observed = normalized.get(field)
        if observed is not None and re.fullmatch(r"[0-9a-f]{64}", observed) is None:
            raise DeliveryValidationError(f"attestation.{field} must be lowercase SHA-256")
    filename = normalized.get("pdf_filename")
    if filename is not None and (Path(filename).name != filename or "/" in filename or "\\" in filename):
        raise DeliveryValidationError("attestation.pdf_filename must be a basename")
    return normalized


def _safe_attestation_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Project untrusted MIME observations to the strict receipt-safe schema."""

    projected: dict[str, Any] = {}
    for field in ATTESTATION_BOOL_FIELDS:
        observed = value.get(field)
        projected[field] = observed if isinstance(observed, bool) else None
    for field in ATTESTATION_INT_FIELDS:
        observed = value.get(field)
        projected[field] = (
            observed
            if isinstance(observed, int)
            and not isinstance(observed, bool)
            and observed >= 0
            else None
        )
    for field in ATTESTATION_TEXT_FIELDS:
        observed = value.get(field)
        projected[field] = (
            observed
            if isinstance(observed, str)
            and 0 < len(observed) <= 255
            and not any(ord(character) < 32 for character in observed)
            else None
        )
    filename = projected.get("pdf_filename")
    if filename is not None and (
        Path(filename).name != filename or "/" in filename or "\\" in filename
    ):
        projected["pdf_filename"] = None
    for field in ("html_sha256", "pdf_sha256"):
        digest = projected.get(field)
        if digest is not None and re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            projected[field] = None
    # These are validator-owned values and must always survive the projection.
    projected["validator"] = GMAIL_RAW_VALIDATOR
    projected["attestation_stage"] = value.get("attestation_stage")
    projected["required_label"] = value.get("required_label")
    normalized = _normalize_attestation(projected)
    if normalized is None:  # pragma: no cover - projected is always one object
        raise AssertionError("attestation projection unexpectedly returned null")
    return normalized


def _verified_attestation_matches(
    manifest: dict[str, Any],
    stage: str,
    attestation_schema_version: Any,
    attestation: dict[str, Any] | None,
) -> bool:
    expected_stage = "draft" if stage == "draft_verified" else "sent"
    required_label = "DRAFT" if expected_stage == "draft" else "SENT"
    return bool(
        attestation_schema_version == GMAIL_RAW_ATTESTATION_SCHEMA
        and not isinstance(attestation_schema_version, bool)
        and isinstance(attestation, dict)
        and attestation.get("validator") == GMAIL_RAW_VALIDATOR
        and attestation.get("attestation_stage") == expected_stage
        and attestation.get("required_label") == required_label
        and attestation.get("message_id_match") is True
        and attestation.get("label_verified") is True
        and attestation.get("subject_verified") is True
        and attestation.get("recipient_verified") is True
        and isinstance(attestation.get("mime_part_count"), int)
        and not isinstance(attestation.get("mime_part_count"), bool)
        and attestation["mime_part_count"] >= 3
        and attestation.get("html_part_count") == 1
        and attestation.get("html_bytes") == manifest.get("html_bytes")
        and attestation.get("html_sha256") == manifest.get("html_sha256")
        and attestation.get("attachment_count") == manifest.get("attachment_count")
        and attestation.get("pdf_part_count") == 1
        and attestation.get("pdf_filename") == manifest.get("pdf_filename")
        and attestation.get("pdf_mime_type") == "application/pdf"
        and attestation.get("pdf_disposition") == "attachment"
        and attestation.get("pdf_bytes") == manifest.get("pdf_bytes")
        and attestation.get("pdf_sha256") == manifest.get("pdf_sha256")
    )


def _gmail_raw_manifest(root: Path, manifest_path: Path) -> tuple[dict[str, Any], Path]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    delivery_dir = (root / "deliveries").resolve()
    manifest_name_match = DELIVERY_MANIFEST_NAME_RE.fullmatch(manifest_path.name)
    if manifest_path.parent != delivery_dir or manifest_name_match is None:
        raise GmailRawAttestationError(
            "manifest_path_invalid", "manifest is not the dated delivery manifest"
        )
    if not manifest_path.is_file():
        raise GmailRawAttestationError("manifest_invalid", "manifest is missing")
    try:
        manifest = runtime.read_json(manifest_path)
    except Exception as exc:
        raise GmailRawAttestationError(
            "manifest_invalid", "manifest is not valid JSON"
        ) from exc
    if not isinstance(manifest, dict):
        raise GmailRawAttestationError(
            "manifest_invalid", "manifest root must be one object"
        )
    if manifest.get("report_date") is not None and (
        manifest.get("report_date") != manifest_name_match.group(1)
    ):
        raise GmailRawAttestationError(
            "manifest_invalid", "manifest report_date does not match its filename"
        )
    required = {
        "schema_version": runtime.SCHEMA_VERSION,
        "coverage_policy": COVERAGE_POLICY,
        "delivery_format": DELIVERY_FORMAT,
        "message_count": 1,
        "attachment_count": 1,
        "validated": True,
    }
    if any(manifest.get(field) != expected for field, expected in required.items()):
        raise GmailRawAttestationError(
            "manifest_invalid", "manifest does not satisfy the v4 delivery contract"
        )
    for field in ("subject", "pdf_filename"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise GmailRawAttestationError(
                "manifest_invalid", f"manifest field {field} is invalid"
            )
    for field in ("html_bytes", "pdf_bytes"):
        if isinstance(manifest.get(field), bool) or not isinstance(
            manifest.get(field), int
        ) or manifest[field] <= 0:
            raise GmailRawAttestationError(
                "manifest_invalid", f"manifest field {field} is invalid"
            )
    if manifest["html_bytes"] > HTML_MAX_BYTES or manifest["pdf_bytes"] > PDF_MAX_BYTES:
        raise GmailRawAttestationError(
            "manifest_invalid", "manifest artifact size exceeds the delivery limits"
        )
    if (
        Path(manifest["pdf_filename"]).name != manifest["pdf_filename"]
        or "/" in manifest["pdf_filename"]
        or "\\" in manifest["pdf_filename"]
    ):
        raise GmailRawAttestationError(
            "manifest_invalid", "manifest PDF filename must be a basename"
        )
    for field in ("html_sha256", "pdf_sha256"):
        if re.fullmatch(r"[0-9a-f]{64}", str(manifest.get(field) or "")) is None:
            raise GmailRawAttestationError(
                "manifest_invalid", f"manifest field {field} is invalid"
            )
    for field in ("expected_html_ids", "expected_pdf_ids", "selected_field_labels"):
        if not isinstance(manifest.get(field), list) or not all(
            isinstance(item, str) and item for item in manifest[field]
        ):
            raise GmailRawAttestationError(
                "manifest_invalid", f"manifest field {field} is invalid"
            )
    for prefix in ("html", "pdf"):
        try:
            artifact = Path(str(manifest.get(f"{prefix}_path") or "")).resolve()
            artifact_matches = bool(
                artifact.parent == delivery_dir
                and artifact.is_file()
                and artifact.stat().st_size == manifest[f"{prefix}_bytes"]
                and _sha256(artifact) == manifest[f"{prefix}_sha256"]
                and (
                    prefix != "pdf" or artifact.name == manifest["pdf_filename"]
                )
            )
        except (OSError, RuntimeError, ValueError):
            artifact_matches = False
        if not artifact_matches:
            raise GmailRawAttestationError(
                "manifest_identity_changed",
                f"local {prefix} artifact no longer matches the manifest",
            )
    return manifest, manifest_path


def _decoded_gmail_raw(value: Any) -> bytes:
    if not isinstance(value, str) or not value or re.fullmatch(
        r"[A-Za-z0-9_-]+={0,2}", value
    ) is None:
        raise GmailRawAttestationError(
            "raw_base64url_invalid", "Gmail raw is not strict base64url"
        )
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.b64decode(
            (value + padding).encode("ascii"), altchars=b"-_", validate=True
        )
    except (ValueError, UnicodeEncodeError) as exc:
        raise GmailRawAttestationError(
            "raw_base64url_invalid", "Gmail raw base64url decoding failed"
        ) from exc


def _bounded_mime_parts(message: Any) -> list[Any]:
    parts: list[Any] = []

    def visit(part: Any, depth: int) -> None:
        if depth > GMAIL_RAW_MAX_DEPTH or len(parts) >= GMAIL_RAW_MAX_PARTS:
            raise GmailRawAttestationError(
                "mime_part_limit_exceeded", "Gmail MIME structure exceeds bounds"
            )
        if getattr(part, "defects", None):
            raise GmailRawAttestationError(
                "mime_parse_defect", "Gmail MIME structure contains parser defects"
            )
        if part.get_content_type() == "message/rfc822":
            raise GmailRawAttestationError(
                "mime_part_limit_exceeded", "nested message/rfc822 is not allowed"
            )
        parts.append(part)
        if part.is_multipart():
            payload = part.get_payload()
            if not isinstance(payload, list):
                raise GmailRawAttestationError(
                    "mime_parse_defect", "multipart payload is malformed"
                )
            for child in payload:
                visit(child, depth + 1)

    visit(message, 0)
    return parts


def _validate_mime_headers(parts: list[Any]) -> None:
    for part in parts:
        for name in ("Content-Type", "Content-Transfer-Encoding", "Content-Disposition"):
            if len(part.get_all(name, [])) > 1:
                raise GmailRawAttestationError(
                    "mime_header_invalid", f"Gmail MIME has duplicate {name} headers"
                )
        for header in part.values():
            if getattr(header, "defects", None):
                raise GmailRawAttestationError(
                    "mime_header_invalid", "Gmail MIME contains a defective header"
                )


def _attestation_result(
    manifest: dict[str, Any],
    metadata: dict[str, Any],
    stage: str,
    observed: dict[str, Any],
    *,
    failure: GmailRawAttestationError | GmailRawFrameError | None,
    body_verified: bool,
    attachment_verified: bool,
) -> dict[str, Any]:
    message_id = str(metadata.get("message_id") or "").strip()
    draft_id = str(metadata.get("draft_id") or "").strip()
    ok = failure is None and body_verified and attachment_verified
    return {
        "schema_version": runtime.SCHEMA_VERSION,
        "attestation_schema_version": GMAIL_RAW_ATTESTATION_SCHEMA,
        "ok": ok,
        "stage": ("draft_verified" if stage == "draft" else "sent_verified")
        if ok
        else "ambiguous",
        "subject": manifest.get("subject"),
        "html_sha256": manifest.get("html_sha256"),
        "pdf_sha256": manifest.get("pdf_sha256"),
        "gmail_draft_id": draft_id or None,
        "gmail_draft_message_id": message_id if stage == "draft" and message_id else None,
        "gmail_message_id": message_id if stage == "sent" and message_id else None,
        "body_verified": body_verified,
        "attachment_verified": attachment_verified,
        "failure_code": failure.failure_code if failure is not None else None,
        "failure_detail": str(failure) if failure is not None else None,
        "attestation": _safe_attestation_projection(observed),
    }


def _empty_raw_attestation(stage: str) -> dict[str, Any]:
    required_label = "DRAFT" if stage == "draft" else "SENT"
    return {
        "validator": GMAIL_RAW_VALIDATOR,
        "attestation_stage": stage,
        "required_label": required_label,
        "message_id_match": None,
        "label_verified": None,
        "subject_verified": None,
        "recipient_verified": None,
        "mime_part_count": None,
        "html_part_count": None,
        "html_bytes": None,
        "html_sha256": None,
        "attachment_count": None,
        "pdf_part_count": None,
        "pdf_filename": None,
        "pdf_mime_type": None,
        "pdf_disposition": None,
        "pdf_bytes": None,
        "pdf_sha256": None,
    }


def attest_gmail_raw(
    root: Path,
    manifest_path: Path,
    stage: str,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    """Deterministically verify Gmail RFC 2822 raw MIME against one manifest."""
    runtime.configure_public_runtime(root)

    if stage not in {"draft", "sent"}:
        raise DeliveryValidationError("Gmail raw stage must be draft or sent")
    manifest: dict[str, Any] = {}
    metadata = envelope if isinstance(envelope, dict) else {}
    required_label = "DRAFT" if stage == "draft" else "SENT"
    observed = _empty_raw_attestation(stage)
    body_verified = False
    attachment_verified = False
    try:
        manifest, _ = _gmail_raw_manifest(root, manifest_path)
        if not isinstance(envelope, dict):
            raise GmailRawAttestationError(
                "frame_header_invalid", "Gmail raw envelope must be an object"
            )
        message_id = str(envelope.get("message_id") or "").strip()
        expected_message_id = str(
            envelope.get("expected_message_id") or ""
        ).strip()
        observed["message_id_match"] = bool(
            message_id and message_id == expected_message_id
        )
        if observed["message_id_match"] is not True:
            raise GmailRawAttestationError(
                "gmail_message_id_mismatch",
                "Gmail readback message ID does not match the requested ID",
            )
        labels = envelope.get("label_ids")
        opposite_label = "SENT" if stage == "draft" else "DRAFT"
        observed["label_verified"] = bool(
            isinstance(labels, list)
            and required_label in labels
            and opposite_label not in labels
        )
        if observed["label_verified"] is not True:
            raise GmailRawAttestationError(
                "gmail_label_draft_missing"
                if stage == "draft"
                else "gmail_label_sent_missing",
                f"Gmail readback is missing the required {required_label} label",
            )
        raw_bytes = _decoded_gmail_raw(envelope.get("raw"))
        try:
            message = BytesParser(policy=email.policy.default).parsebytes(raw_bytes)
        except Exception as exc:
            raise GmailRawAttestationError(
                "mime_parse_defect", "Gmail raw MIME parsing failed"
            ) from exc
        parts = _bounded_mime_parts(message)
        _validate_mime_headers(parts)
        observed["mime_part_count"] = len(parts)
        leaf_parts = [part for part in parts if not part.is_multipart()]
        if len(leaf_parts) != 2:
            raise GmailRawAttestationError(
                "mime_unexpected_leaf",
                f"Gmail MIME has {len(leaf_parts)} leaf parts; expected exactly 2",
            )
        root_payload = message.get_payload()
        if (
            message.get_content_type() != "multipart/mixed"
            or not isinstance(root_payload, list)
            or len(root_payload) != 2
            or any(part.is_multipart() for part in root_payload)
        ):
            raise GmailRawAttestationError(
                "mime_shape_mismatch",
                "Gmail MIME is not the canonical mixed HTML-plus-PDF tree",
            )

        subjects = message.get_all("Subject", [])
        if not subjects:
            raise GmailRawAttestationError("subject_missing", "Gmail Subject is missing")
        if len(subjects) != 1:
            raise GmailRawAttestationError(
                "subject_multiple", "Gmail message has multiple Subject headers"
            )
        observed["subject_verified"] = str(subjects[0]) == manifest["subject"]
        if observed["subject_verified"] is not True:
            raise GmailRawAttestationError(
                "subject_mismatch", "Gmail Subject does not match the manifest"
            )
        profile_email = str(envelope.get("profile_email") or "").strip().lower()
        recipients = [
            address.lower()
            for _, address in email.utils.getaddresses(message.get_all("To", []))
            if address
        ]
        if not recipients:
            raise GmailRawAttestationError(
                "recipient_missing", "Gmail To recipient is missing"
            )
        copied_recipients = [
            address
            for header in ("Cc", "Bcc", "Resent-To", "Resent-Cc", "Resent-Bcc")
            for _, address in email.utils.getaddresses(message.get_all(header, []))
            if address
        ]
        observed["recipient_verified"] = bool(
            profile_email
            and recipients == [profile_email]
            and not copied_recipients
        )
        if observed["recipient_verified"] is not True:
            raise GmailRawAttestationError(
                "recipient_mismatch",
                "Gmail recipients are not exactly the authenticated profile",
            )

        html_parts = [
            part
            for part in parts
            if not part.is_multipart()
            and part.get_content_type() == "text/html"
            and part.get_content_disposition() != "attachment"
        ]
        observed["html_part_count"] = len(html_parts)
        if not html_parts:
            raise GmailRawAttestationError(
                "html_part_missing", "Gmail HTML body is missing"
            )
        if len(html_parts) != 1:
            raise GmailRawAttestationError(
                "html_part_multiple", "Gmail has multiple HTML body parts"
            )
        if (
            str(html_parts[0].get_content_charset() or "").lower() != "utf-8"
            or html_parts[0].get_content_disposition() != "inline"
        ):
            raise GmailRawAttestationError(
                "html_charset_mismatch",
                "Gmail HTML must be inline UTF-8 content",
            )
        try:
            html_bytes = html_parts[0].get_payload(decode=True)
        except Exception as exc:
            raise GmailRawAttestationError(
                "html_decode_failed", "Gmail HTML transfer decoding failed"
            ) from exc
        if not isinstance(html_bytes, bytes):
            raise GmailRawAttestationError(
                "html_decode_failed", "Gmail HTML body has no decoded bytes"
            )
        observed["html_bytes"] = len(html_bytes)
        observed["html_sha256"] = hashlib.sha256(html_bytes).hexdigest()
        if len(html_bytes) != manifest["html_bytes"]:
            raise GmailRawAttestationError(
                "html_size_mismatch",
                f"expected {manifest['html_bytes']} HTML bytes; observed {len(html_bytes)}",
            )
        if observed["html_sha256"] != manifest["html_sha256"]:
            raise GmailRawAttestationError(
                "html_sha256_mismatch", "Gmail HTML SHA-256 does not match the manifest"
            )
        # The local delivery validator already proved markers, IDs, selected
        # labels, and truncation absence before writing the manifest.  Exact
        # decoded size + SHA-256 transfers that complete semantic attestation
        # without re-implementing it (notably for valid zero-selected days).
        body_verified = True

        attachments = [
            part
            for part in parts
            if not part.is_multipart()
            and (
                part.get_content_disposition() == "attachment"
                or bool(part.get_filename())
            )
        ]
        observed["attachment_count"] = len(attachments)
        if len(attachments) != manifest["attachment_count"]:
            raise GmailRawAttestationError(
                "attachment_count_mismatch",
                f"expected {manifest['attachment_count']} attachment; observed {len(attachments)}",
            )
        pdf_candidates = [
            part
            for part in attachments
            if part.get_content_type() == "application/pdf"
            or part.get_filename() == manifest["pdf_filename"]
        ]
        observed["pdf_part_count"] = len(pdf_candidates)
        if not pdf_candidates:
            raise GmailRawAttestationError(
                "pdf_part_missing", "Gmail PDF attachment is missing"
            )
        if len(pdf_candidates) != 1:
            raise GmailRawAttestationError(
                "pdf_part_multiple", "Gmail has multiple PDF attachment candidates"
            )
        pdf_part = pdf_candidates[0]
        observed["pdf_filename"] = pdf_part.get_filename()
        observed["pdf_mime_type"] = pdf_part.get_content_type()
        observed["pdf_disposition"] = pdf_part.get_content_disposition()
        if observed["pdf_filename"] != manifest["pdf_filename"]:
            raise GmailRawAttestationError(
                "pdf_filename_mismatch", "Gmail PDF filename does not match the manifest"
            )
        if observed["pdf_mime_type"] != "application/pdf":
            raise GmailRawAttestationError(
                "pdf_mime_mismatch", "Gmail PDF MIME type is not application/pdf"
            )
        if observed["pdf_disposition"] != "attachment":
            raise GmailRawAttestationError(
                "pdf_disposition_mismatch", "Gmail PDF is not an attachment part"
            )
        try:
            pdf_bytes = pdf_part.get_payload(decode=True)
        except Exception as exc:
            raise GmailRawAttestationError(
                "pdf_decode_failed", "Gmail PDF transfer decoding failed"
            ) from exc
        if not isinstance(pdf_bytes, bytes):
            raise GmailRawAttestationError(
                "pdf_decode_failed", "Gmail PDF has no decoded bytes"
            )
        observed["pdf_bytes"] = len(pdf_bytes)
        observed["pdf_sha256"] = hashlib.sha256(pdf_bytes).hexdigest()
        if len(pdf_bytes) != manifest["pdf_bytes"]:
            raise GmailRawAttestationError(
                "pdf_size_mismatch",
                f"expected {manifest['pdf_bytes']} PDF bytes; observed {len(pdf_bytes)}",
            )
        if observed["pdf_sha256"] != manifest["pdf_sha256"]:
            raise GmailRawAttestationError(
                "pdf_sha256_mismatch",
                f"expected PDF SHA-256 {manifest['pdf_sha256']}; observed {observed['pdf_sha256']}",
            )
        attachment_verified = True
        return _attestation_result(
            manifest,
            metadata,
            stage,
            observed,
            failure=None,
            body_verified=body_verified,
            attachment_verified=attachment_verified,
        )
    except GmailRawAttestationError as failure:
        return _attestation_result(
            manifest,
            metadata,
            stage,
            observed,
            failure=failure,
            body_verified=body_verified,
            attachment_verified=attachment_verified,
        )


def delivery_receipt_path(root: Path, manifest_path: Path) -> Path:
    """Return the immutable per-announcement-date receipt path."""
    runtime.configure_public_runtime(root)

    match = DELIVERY_MANIFEST_NAME_RE.fullmatch(manifest_path.resolve().name)
    if match is None:
        raise DeliveryValidationError(
            "delivery manifest filename must bind one YYYY-MM-DD announcement date"
        )
    return (
        root.resolve()
        / "deliveries"
        / f"arxiv-daily-{match.group(1)}-receipt-v4.json"
    )


def _preserve_legacy_receipt(root: Path, legacy_path: Path) -> None:
    """Migrate the global receipt alias before it is advanced to a new date."""

    if not legacy_path.is_file():
        return
    prior = runtime.read_json(legacy_path)
    try:
        prior_manifest = Path(str(prior.get("manifest") or "")).resolve()
        archived_path = delivery_receipt_path(root, prior_manifest)
    except (DeliveryValidationError, OSError, RuntimeError, ValueError):
        return
    if archived_path.is_file():
        archived = runtime.read_json(archived_path)
        if archived != prior:
            same_identity = all(
                archived.get(field) == prior.get(field)
                for field in ("manifest", "subject", "html_sha256", "pdf_sha256")
            )
            archived_draft = str(archived.get("gmail_draft_id") or "").strip()
            prior_draft = str(prior.get("gmail_draft_id") or "").strip()
            archived_draft_message = str(
                archived.get("gmail_draft_message_id") or ""
            ).strip()
            prior_draft_message = str(
                prior.get("gmail_draft_message_id") or ""
            ).strip()
            archived_message = str(archived.get("gmail_message_id") or "").strip()
            prior_message = str(prior.get("gmail_message_id") or "").strip()
            identity_conflict = bool(
                (archived_draft and prior_draft and archived_draft != prior_draft)
                or (
                    archived_draft_message
                    and prior_draft_message
                    and archived_draft_message != prior_draft_message
                )
                or (
                    archived_message
                    and prior_message
                    and archived_message != prior_message
                )
            )
            stale_alias_after_dated_write = bool(
                same_identity
                and not identity_conflict
                and not (
                    prior.get("stage") == "sent_verified"
                    and (
                        archived.get("stage") != "sent_verified"
                        or archived_message != prior_message
                    )
                )
            )
            if not stale_alias_after_dated_write:
                raise DeliveryValidationError(
                    "per-date receipt conflicts with the legacy receipt alias"
                )
        return
    runtime.atomic_write_json(archived_path, prior)


def _gmail_send_state_paths(root: Path, manifest_path: Path) -> tuple[Path, Path]:
    match = DELIVERY_MANIFEST_NAME_RE.fullmatch(manifest_path.resolve().name)
    if match is None:
        raise DeliveryValidationError(
            "delivery manifest filename must bind one YYYY-MM-DD announcement date"
        )
    prefix = f"arxiv-daily-{match.group(1)}-gmail-send-state-v1"
    delivery_root = root.resolve() / "deliveries"
    return delivery_root / f"{prefix}.json", delivery_root / f"{prefix}.lock"


@contextmanager
def _gmail_send_state_lock(
    root: Path,
    manifest_path: Path,
    *,
    timeout_seconds: float = 10.0,
) -> Iterator[None]:
    """Serialize every receipt/state read-check-write across processes."""

    _, lock_path = _gmail_send_state_paths(root, manifest_path)
    manager = runtime._exclusive_gate_state_lock(
        lock_path, timeout_seconds=timeout_seconds
    )
    try:
        manager.__enter__()
    except runtime.DigestValidationError as exc:
        raise DeliveryValidationError(str(exc)) from exc
    try:
        yield
    finally:
        manager.__exit__(None, None, None)


@contextmanager
def _delivery_receipt_alias_lock(
    root: Path, *, timeout_seconds: float = 10.0
) -> Iterator[None]:
    """Serialize the shared compatibility alias across announcement dates."""

    lock_path = root.resolve() / "deliveries" / "delivery-receipt-v4.lock"
    manager = runtime._exclusive_gate_state_lock(
        lock_path, timeout_seconds=timeout_seconds
    )
    try:
        manager.__enter__()
    except runtime.DigestValidationError as exc:
        raise DeliveryValidationError(str(exc)) from exc
    try:
        yield
    finally:
        manager.__exit__(None, None, None)


def _send_current_time(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise DeliveryValidationError("Gmail send state time must be timezone-aware")
    return current.astimezone(timezone.utc)


def _send_timestamp(value: datetime) -> str:
    return (
        _send_current_time(value)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _parse_send_timestamp(value: Any, label: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DeliveryValidationError(f"invalid {label}") from exc
    if parsed.tzinfo is None:
        raise DeliveryValidationError(f"invalid {label}")
    return parsed.astimezone(timezone.utc)


def _send_token_hash(token: str, label: str) -> str:
    normalized = str(token or "").strip()
    if SEND_TOKEN_RE.fullmatch(normalized) is None:
        raise DeliveryValidationError(f"{label} is invalid")
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


def _new_send_token() -> str:
    return secrets.token_urlsafe(32)


def _send_binding_sha256(binding: dict[str, Any]) -> str:
    encoded = json.dumps(
        binding,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _gmail_send_state_default() -> dict[str, Any]:
    return {
        "schema_version": SEND_STATE_SCHEMA,
        "pending_reauthorization": None,
        "pending_proof": None,
        "reauthorization_proof_state": None,
        "active_lease": None,
        "last_released_lease": None,
        "legacy_recovery_fence": None,
    }


def _validate_hashed_token(value: Any, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
        raise DeliveryValidationError(f"{label} is invalid")
    return normalized


def _normalize_legacy_recovery_fence(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DeliveryValidationError("legacy recovery fence must be an object")
    required = {
        "fence_schema",
        "status",
        "reauthorization_schema",
        "reauthorization_id",
        "manifest",
        "manifest_sha256",
        "report_date",
        "blocked_receipt_sha256",
        "grant_binding_sha256",
        "authorization_scope",
        "authorization_decision",
        "authorization_origin",
        "destination",
        "exact_sent_zero_required",
        "issued_at",
        "expires_at",
        "finalized_at",
    }
    optional = {"token_rotation_count"}
    if not required.issubset(value) or not set(value).issubset(required | optional):
        raise DeliveryValidationError("legacy recovery fence fields are invalid")
    if value.get("fence_schema") != LEGACY_RECOVERY_FENCE_SCHEMA:
        raise DeliveryValidationError("legacy recovery fence schema is invalid")
    status = value.get("status")
    if status not in {"issued", "consumed", "expired"}:
        raise DeliveryValidationError("legacy recovery fence status is invalid")
    if value.get("reauthorization_schema") != LEGACY_SEND_REAUTHORIZATION_SCHEMA:
        raise DeliveryValidationError(
            "legacy recovery fence reauthorization schema is invalid"
        )
    reauthorization_id = str(value.get("reauthorization_id") or "").strip()
    if re.fullmatch(r"[0-9a-f]{32}", reauthorization_id) is None:
        raise DeliveryValidationError("legacy recovery fence id is invalid")
    manifest = str(value.get("manifest") or "").strip()
    if not manifest or "\r" in manifest or "\n" in manifest:
        raise DeliveryValidationError("legacy recovery fence manifest is invalid")
    report_date = str(value.get("report_date") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date) is None:
        raise DeliveryValidationError("legacy recovery fence date is invalid")
    manifest_sha256 = _validate_hashed_token(
        value.get("manifest_sha256"), "legacy recovery manifest hash"
    )
    blocked_receipt_sha256 = _validate_hashed_token(
        value.get("blocked_receipt_sha256"), "legacy recovery receipt hash"
    )
    grant_binding_sha256 = _validate_hashed_token(
        value.get("grant_binding_sha256"), "legacy recovery grant binding hash"
    )
    if value.get("authorization_scope") != SEND_AUTHORIZATION_SCOPE:
        raise DeliveryValidationError("legacy recovery fence scope is invalid")
    if (
        value.get("authorization_decision")
        != LEGACY_SEND_REAUTHORIZATION_DECISION
    ):
        raise DeliveryValidationError("legacy recovery fence decision is invalid")
    if value.get("authorization_origin") != LEGACY_SEND_REAUTHORIZATION_ORIGIN:
        raise DeliveryValidationError("legacy recovery fence origin is invalid")
    destination = str(value.get("destination") or "").strip()
    if email.utils.parseaddr(destination)[1] != destination or "@" not in destination:
        raise DeliveryValidationError("legacy recovery fence destination is invalid")
    if value.get("exact_sent_zero_required") is not True:
        raise DeliveryValidationError(
            "legacy recovery fence must require exact SENT zero"
        )
    token_rotation_count = value.get("token_rotation_count", 0)
    if (
        isinstance(token_rotation_count, bool)
        or not isinstance(token_rotation_count, int)
        or token_rotation_count not in {0, 1}
    ):
        raise DeliveryValidationError(
            "legacy recovery fence token rotation count is invalid"
        )
    issued_at = _send_timestamp(
        _parse_send_timestamp(value.get("issued_at"), "legacy recovery issue time")
    )
    expires_at = _send_timestamp(
        _parse_send_timestamp(value.get("expires_at"), "legacy recovery expiry")
    )
    finalized_value = value.get("finalized_at")
    finalized_at = (
        None
        if finalized_value is None
        else _send_timestamp(
            _parse_send_timestamp(
                finalized_value, "legacy recovery finalization time"
            )
        )
    )
    if (status == "issued") != (finalized_at is None):
        raise DeliveryValidationError(
            "legacy recovery fence finalization does not match its status"
        )
    return {
        "fence_schema": LEGACY_RECOVERY_FENCE_SCHEMA,
        "status": status,
        "reauthorization_schema": LEGACY_SEND_REAUTHORIZATION_SCHEMA,
        "reauthorization_id": reauthorization_id,
        "manifest": manifest,
        "manifest_sha256": manifest_sha256,
        "report_date": report_date,
        "blocked_receipt_sha256": blocked_receipt_sha256,
        "grant_binding_sha256": grant_binding_sha256,
        "authorization_scope": SEND_AUTHORIZATION_SCOPE,
        "authorization_decision": LEGACY_SEND_REAUTHORIZATION_DECISION,
        "authorization_origin": LEGACY_SEND_REAUTHORIZATION_ORIGIN,
        "destination": destination,
        "exact_sent_zero_required": True,
        "token_rotation_count": token_rotation_count,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "finalized_at": finalized_at,
    }


def _read_gmail_send_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _gmail_send_state_default()
    state = runtime.read_json(path)
    if state.get("schema_version") != SEND_STATE_SCHEMA:
        raise DeliveryValidationError("unsupported Gmail send state schema")
    for field in (
        "pending_reauthorization",
        "pending_proof",
        "reauthorization_proof_state",
        "active_lease",
        "last_released_lease",
        "legacy_recovery_fence",
    ):
        item = state.get(field)
        if item is not None and not isinstance(item, dict):
            raise DeliveryValidationError(f"Gmail send state {field} must be an object")
    reauthorization = state.get("pending_reauthorization")
    if reauthorization is not None:
        if reauthorization.get("reauthorization_schema") not in {
            SEND_REAUTHORIZATION_SCHEMA,
            LEGACY_SEND_REAUTHORIZATION_SCHEMA,
        }:
            raise DeliveryValidationError("unsupported pending Gmail send reauthorization")
        _validate_hashed_token(
            reauthorization.get("token_sha256"), "reauthorization token hash"
        )
        _validate_hashed_token(
            reauthorization.get("binding_sha256"),
            "reauthorization binding hash",
        )
        _parse_send_timestamp(
            reauthorization.get("expires_at"), "reauthorization expiry"
        )
        if not isinstance(reauthorization.get("binding"), dict):
            raise DeliveryValidationError(
                "pending Gmail send reauthorization binding is invalid"
            )
        binding = reauthorization["binding"]
        if reauthorization.get("reauthorization_schema") == LEGACY_SEND_REAUTHORIZATION_SCHEMA:
            if (
                binding.get("reauthorization_schema")
                != LEGACY_SEND_REAUTHORIZATION_SCHEMA
                or binding.get("authorization_decision")
                != LEGACY_SEND_REAUTHORIZATION_DECISION
                or binding.get("authorization_origin")
                != LEGACY_SEND_REAUTHORIZATION_ORIGIN
                or binding.get("exact_sent_zero_required") is not True
            ):
                raise DeliveryValidationError(
                    "pending legacy Gmail send reauthorization binding is invalid"
                )
    proof = state.get("pending_proof")
    if proof is not None:
        if proof.get("proof_schema") != SEND_PROOF_SCHEMA:
            raise DeliveryValidationError("unsupported pending Gmail send proof")
        _validate_hashed_token(proof.get("token_sha256"), "proof token hash")
        _validate_hashed_token(proof.get("proof_sha256"), "proof binding hash")
        _parse_send_timestamp(proof.get("expires_at"), "proof expiry")
        if not isinstance(proof.get("binding"), dict):
            raise DeliveryValidationError("pending Gmail send proof binding is invalid")
    reauthorization_proof_state = state.get("reauthorization_proof_state")
    if reauthorization_proof_state is not None:
        if re.fullmatch(
            r"[0-9a-f]{32}",
            str(reauthorization_proof_state.get("reauthorization_id") or ""),
        ) is None:
            raise DeliveryValidationError(
                "reauthorization proof state id is invalid"
            )
        _validate_hashed_token(
            reauthorization_proof_state.get("proof_sha256"),
            "reauthorization proof state hash",
        )
        lease_acquired_at = reauthorization_proof_state.get("lease_acquired_at")
        if lease_acquired_at is not None:
            _parse_send_timestamp(
                lease_acquired_at, "reauthorization proof lease acquisition time"
            )
        reissue_count = reauthorization_proof_state.get("reissue_count")
        if (
            isinstance(reissue_count, bool)
            or not isinstance(reissue_count, int)
            or not (0 <= reissue_count <= 16)
        ):
            raise DeliveryValidationError(
                "reauthorization proof reissue count is invalid"
            )
    lease = state.get("active_lease")
    if lease is not None:
        _validate_hashed_token(lease.get("token_sha256"), "lease token hash")
        _validate_hashed_token(lease.get("proof_sha256"), "lease proof hash")
        _parse_send_timestamp(lease.get("expires_at"), "lease expiry")
        if not str(lease.get("owner") or "").strip():
            raise DeliveryValidationError("active Gmail send lease owner is invalid")
        if not isinstance(lease.get("binding"), dict):
            raise DeliveryValidationError("active Gmail send lease binding is invalid")
    last_released_lease = state.get("last_released_lease")
    if last_released_lease is not None:
        released_token_hash = last_released_lease.get("token_sha256")
        if released_token_hash is not None:
            _validate_hashed_token(
                released_token_hash, "released lease token hash"
            )
        _validate_hashed_token(
            last_released_lease.get("proof_sha256"), "released lease proof hash"
        )
        _validate_hashed_token(
            last_released_lease.get("receipt_sha256"), "released lease receipt hash"
        )
        _parse_send_timestamp(
            last_released_lease.get("released_at"), "lease release time"
        )
        if not isinstance(last_released_lease.get("binding"), dict):
            raise DeliveryValidationError("released lease binding is invalid")
    state["legacy_recovery_fence"] = _normalize_legacy_recovery_fence(
        state.get("legacy_recovery_fence")
    )
    return state


def _expire_gmail_send_state(
    state: dict[str, Any], current: datetime
) -> bool:
    changed = False
    reauthorization = state.get("pending_reauthorization")
    if reauthorization is not None and _parse_send_timestamp(
        reauthorization.get("expires_at"), "reauthorization expiry"
    ) <= current:
        if (
            reauthorization.get("reauthorization_schema")
            == LEGACY_SEND_REAUTHORIZATION_SCHEMA
        ):
            fence = _normalize_legacy_recovery_fence(
                state.get("legacy_recovery_fence")
            )
            binding = reauthorization.get("binding")
            if (
                fence is not None
                and fence["status"] == "issued"
                and isinstance(binding, dict)
                and fence["reauthorization_id"]
                == binding.get("reauthorization_id")
                and fence["grant_binding_sha256"]
                == reauthorization.get("binding_sha256")
            ):
                state["legacy_recovery_fence"] = {
                    **fence,
                    "status": "expired",
                    "finalized_at": _send_timestamp(current),
                }
        state["pending_reauthorization"] = None
        state["expired_reauthorization_at"] = _send_timestamp(current)
        changed = True
    proof = state.get("pending_proof")
    if proof is not None and _parse_send_timestamp(
        proof.get("expires_at"), "proof expiry"
    ) <= current:
        state["pending_proof"] = None
        changed = True
    lease = state.get("active_lease")
    if lease is not None and _parse_send_timestamp(
        lease.get("expires_at"), "lease expiry"
    ) <= current:
        state["active_lease"] = None
        state["expired_lease_at"] = _send_timestamp(current)
        changed = True
    return changed


def _write_gmail_send_state(path: Path, state: dict[str, Any], current: datetime) -> None:
    state["schema_version"] = SEND_STATE_SCHEMA
    state["updated_at"] = _send_timestamp(current)
    runtime.atomic_write_json(path, state)


def _active_send_lease_matches(
    state: dict[str, Any], send_lease_token: str | None
) -> bool:
    active = state.get("active_lease")
    if active is None or send_lease_token is None:
        return False
    supplied_hash = _send_token_hash(send_lease_token, "Gmail send lease token")
    return hmac.compare_digest(str(active["token_sha256"]), supplied_hash)


def _require_receipt_mutation_lease(
    state: dict[str, Any], send_lease_token: str | None
) -> None:
    active = state.get("active_lease")
    if active is None:
        if send_lease_token is not None:
            raise DeliveryValidationError("Gmail send lease is not active")
        return
    if not _active_send_lease_matches(state, send_lease_token):
        raise DeliveryValidationError(
            "active Gmail send lease rejects receipt mutation without its owner token"
        )


def _legacy_send_attempt_count(value: dict[str, Any] | None) -> int:
    if not isinstance(value, dict):
        return 0
    raw = value.get("send_attempt_count")
    if raw is not None:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise DeliveryValidationError("send_attempt_count must be an integer")
        if raw < 0 or raw > MAX_SEND_ATTEMPTS:
            raise DeliveryValidationError(
                f"send_attempt_count must be between 0 and {MAX_SEND_ATTEMPTS}"
            )
        return raw
    if (
        value.get("stage") == "ambiguous"
        and value.get("failure_code") == "gmail_send_outcome_unknown"
    ):
        # Receipts written before send_attempt_count existed already crossed one
        # send write-ahead boundary.  Treating them as zero would grant an extra
        # send after every process restart.
        return 1
    return 0


def _normalize_send_reauthorization_audit(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DeliveryValidationError("send reauthorization audit must be an object")
    required = {
        "reauthorization_schema",
        "reauthorization_id",
        "authorization_scope",
        "authorization_decision",
        "authorization_reason",
        "destination",
        "prior_failure_code",
        "blocked_receipt_sha256",
        "grant_binding_sha256",
        "authorized_at",
        "consumed_at",
    }
    if set(value) != required:
        raise DeliveryValidationError("send reauthorization audit fields are invalid")
    reauthorization_schema = value.get("reauthorization_schema")
    if reauthorization_schema not in {
        SEND_REAUTHORIZATION_SCHEMA,
        LEGACY_SEND_REAUTHORIZATION_SCHEMA,
    }:
        raise DeliveryValidationError("send reauthorization audit schema is invalid")
    if value.get("authorization_scope") != SEND_AUTHORIZATION_SCOPE:
        raise DeliveryValidationError("send reauthorization audit scope is invalid")
    expected_decision = (
        LEGACY_SEND_REAUTHORIZATION_DECISION
        if reauthorization_schema == LEGACY_SEND_REAUTHORIZATION_SCHEMA
        else SEND_REAUTHORIZATION_DECISION
    )
    if value.get("authorization_decision") != expected_decision:
        raise DeliveryValidationError("send reauthorization audit decision is invalid")
    authorization_reason = _bounded_failure_detail(
        value.get("authorization_reason"), required=True
    )
    reauthorization_id = str(value.get("reauthorization_id") or "").strip()
    if re.fullmatch(r"[0-9a-f]{32}", reauthorization_id) is None:
        raise DeliveryValidationError("send reauthorization audit id is invalid")
    destination = str(value.get("destination") or "").strip()
    if email.utils.parseaddr(destination)[1] != destination or "@" not in destination:
        raise DeliveryValidationError("send reauthorization audit destination is invalid")
    if value.get("prior_failure_code") not in SEND_REAUTHORIZATION_FAILURE_CODES:
        raise DeliveryValidationError("send reauthorization prior failure is invalid")
    blocked_receipt_sha256 = _validate_hashed_token(
        value.get("blocked_receipt_sha256"), "blocked receipt hash"
    )
    grant_binding_sha256 = _validate_hashed_token(
        value.get("grant_binding_sha256"), "reauthorization grant binding hash"
    )
    authorized_at = _send_timestamp(
        _parse_send_timestamp(value.get("authorized_at"), "authorization time")
    )
    consumed_at = _send_timestamp(
        _parse_send_timestamp(value.get("consumed_at"), "reauthorization consumption time")
    )
    return {
        "reauthorization_schema": reauthorization_schema,
        "reauthorization_id": reauthorization_id,
        "authorization_scope": SEND_AUTHORIZATION_SCOPE,
        "authorization_decision": expected_decision,
        "authorization_reason": authorization_reason,
        "destination": destination,
        "prior_failure_code": value["prior_failure_code"],
        "blocked_receipt_sha256": blocked_receipt_sha256,
        "grant_binding_sha256": grant_binding_sha256,
        "authorized_at": authorized_at,
        "consumed_at": consumed_at,
    }


def _record_delivery_receipt_value_locked(
    root: Path,
    manifest_path: Path,
    value: dict[str, Any],
    *,
    allow_send_disposition_refinement: bool = False,
    allow_explicit_reauthorization: bool = False,
    reauthorization_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    receipt_path = delivery_receipt_path(root, manifest_path)
    report_date = DELIVERY_MANIFEST_NAME_RE.fullmatch(manifest_path.name).group(1)
    manifest = runtime.read_json(manifest_path)
    prior = runtime.read_json(receipt_path) if receipt_path.is_file() else None
    if prior is None:
        legacy_path = root / "deliveries" / "delivery-receipt-v4.json"
        if legacy_path.is_file():
            legacy = runtime.read_json(legacy_path)
            try:
                legacy_manifest = Path(str(legacy.get("manifest") or "")).resolve()
            except (OSError, RuntimeError, ValueError):
                legacy_manifest = None
            if legacy_manifest == manifest_path:
                # The compatibility alias is authoritative for the same manifest
                # when the dated file is missing.  Load it before any attempt-count,
                # reauthorization, or downgrade checks so it cannot be overwritten
                # as though this were a new delivery.
                prior = legacy
                runtime.atomic_write_json(receipt_path, prior)
    prior_reauthorization_audit = _normalize_send_reauthorization_audit(
        prior.get("send_reauthorization") if prior is not None else None
    )
    supplied_reauthorization_audit = _normalize_send_reauthorization_audit(
        reauthorization_audit
    )
    if (
        supplied_reauthorization_audit is not None
        and prior_reauthorization_audit is not None
        and supplied_reauthorization_audit != prior_reauthorization_audit
    ):
        raise DeliveryValidationError("send reauthorization audit cannot be replaced")
    effective_reauthorization_audit = (
        supplied_reauthorization_audit or prior_reauthorization_audit
    )
    prior_send_attempt_count = _legacy_send_attempt_count(prior)
    if manifest.get("delivery_format") != DELIVERY_FORMAT or manifest.get("message_count") != 1:
        raise DeliveryValidationError("receipt requires an attested single-message v4 manifest")
    if not isinstance(value, dict):
        raise DeliveryValidationError("delivery receipt input must be one object")
    stage = value.get("stage")
    if stage not in {"draft_verified", "sent_verified", "ambiguous"}:
        raise DeliveryValidationError("receipt stage must be draft_verified, sent_verified, or ambiguous")
    required_identity = {
        "subject": manifest["subject"],
        "html_sha256": manifest["html_sha256"],
        "pdf_sha256": manifest["pdf_sha256"],
    }
    for field, expected in required_identity.items():
        if value.get(field) != expected:
            raise DeliveryValidationError(f"delivery receipt identity mismatch: {field}")
    draft_id = str(value.get("gmail_draft_id") or "").strip()
    draft_message_id = str(value.get("gmail_draft_message_id") or "").strip()
    message_id = str(value.get("gmail_message_id") or "").strip()
    if prior is not None:
        prior_draft_id = str(prior.get("gmail_draft_id") or "").strip()
        prior_draft_message_id = str(
            prior.get("gmail_draft_message_id") or ""
        ).strip()
        prior_message_id = str(prior.get("gmail_message_id") or "").strip()
        if prior_draft_id and draft_id and prior_draft_id != draft_id:
            raise DeliveryValidationError("known Gmail Draft ID cannot be replaced")
        if prior_message_id and message_id and prior_message_id != message_id:
            raise DeliveryValidationError("known Gmail message ID cannot be replaced")
        if (
            prior_draft_message_id
            and draft_message_id
            and prior_draft_message_id != draft_message_id
        ):
            raise DeliveryValidationError(
                "known Gmail Draft message ID cannot be replaced"
            )
        draft_id = draft_id or prior_draft_id
        draft_message_id = draft_message_id or prior_draft_message_id
        message_id = message_id or prior_message_id
    if stage == "draft_verified" and not draft_id:
        raise DeliveryValidationError("verified Draft receipt requires gmail_draft_id")
    if stage == "draft_verified" and not draft_message_id:
        raise DeliveryValidationError(
            "verified Draft receipt requires gmail_draft_message_id"
        )
    if stage == "sent_verified" and not message_id:
        raise DeliveryValidationError("verified SENT receipt requires gmail_message_id")
    if stage != "ambiguous" and (
        value.get("body_verified") is not True
        or value.get("attachment_verified") is not True
    ):
        raise DeliveryValidationError("verified receipt requires body and attachment attestation")
    failure_code_value = value.get("failure_code")
    failure_code = (
        str(failure_code_value).strip() if failure_code_value is not None else None
    )
    failure_detail = _bounded_failure_detail(
        value.get("failure_detail"), required=stage == "ambiguous"
    )
    requested_send_attempt_count = value.get("send_attempt_count")
    if requested_send_attempt_count is None:
        send_attempt_count = prior_send_attempt_count
    else:
        send_attempt_count = _legacy_send_attempt_count(value)
        if send_attempt_count < prior_send_attempt_count:
            raise DeliveryValidationError("send_attempt_count cannot decrease")
        if send_attempt_count > prior_send_attempt_count + 1:
            raise DeliveryValidationError("send_attempt_count cannot skip an attempt")
    is_send_write_ahead = bool(
        stage == "ambiguous"
        and failure_code in SEND_WRITE_AHEAD_FAILURE_CODES
        and send_attempt_count == prior_send_attempt_count + 1
    )
    if send_attempt_count > prior_send_attempt_count and not is_send_write_ahead:
        raise DeliveryValidationError(
            "only a Gmail send write-ahead may increment send_attempt_count"
        )
    if stage == "ambiguous":
        if not failure_code:
            raise DeliveryValidationError("ambiguous receipt requires failure_code")
        if failure_code not in RECEIPT_FAILURE_CODES:
            raise DeliveryValidationError("ambiguous receipt failure_code is unsupported")
    elif failure_code is not None or failure_detail is not None:
        raise DeliveryValidationError(
            "verified receipt cannot contain failure diagnostics"
        )
    is_send_disposition_refinement = bool(
        allow_send_disposition_refinement
        and prior is not None
        and prior.get("stage") == "ambiguous"
        and prior.get("failure_code") == "gmail_send_automatic_retry_blocked"
        and stage == "ambiguous"
        and failure_code in SEND_DISPOSITION_REFINEMENT_FAILURE_CODES
        and send_attempt_count == prior_send_attempt_count
    )
    is_explicit_reauthorization = bool(
        allow_explicit_reauthorization
        and prior is not None
        and prior.get("stage") == "ambiguous"
        and prior.get("failure_code") in SEND_REAUTHORIZATION_FAILURE_CODES
        and stage == "draft_verified"
        and send_attempt_count == prior_send_attempt_count
    )
    is_same_lease_outcome_unknown_retry_write_ahead = bool(
        allow_send_disposition_refinement
        and prior is not None
        and prior.get("stage") == "ambiguous"
        and prior.get("failure_code") == "gmail_send_outcome_unknown"
        and is_send_write_ahead
        and stage == "ambiguous"
        and failure_code == "gmail_send_automatic_retry_blocked"
        and send_attempt_count == prior_send_attempt_count + 1
    )
    if (
        prior is not None
        and prior.get("stage") == "ambiguous"
        and prior.get("failure_code") == "gmail_send_outcome_unknown"
        and not (
            stage == "sent_verified"
            or is_same_lease_outcome_unknown_retry_write_ahead
            or is_explicit_reauthorization
        )
    ):
        raise DeliveryValidationError(
            "Gmail send outcome unknown requires a same-lease retry write-ahead or explicit send reauthorization"
        )
    if (
        prior is not None
        and prior.get("stage") == "ambiguous"
        and prior.get("failure_code") in SEND_REAUTHORIZATION_FAILURE_CODES
        and not (
            stage == "sent_verified"
            or is_send_disposition_refinement
            or is_same_lease_outcome_unknown_retry_write_ahead
            or is_explicit_reauthorization
        )
    ):
        raise DeliveryValidationError(
            "Gmail send retry block requires explicit send reauthorization"
        )
    if (
        stage == "ambiguous"
        and failure_code in SEND_DISPOSITION_FAILURE_CODES
        and not (is_send_write_ahead or is_send_disposition_refinement)
    ):
        raise DeliveryValidationError(
            "Gmail send disposition must be a leased write-ahead or same-lease refinement"
        )
    attestation_schema_version = value.get("attestation_schema_version")
    attestation = _normalize_attestation(value.get("attestation"))
    if stage != "ambiguous":
        if not _verified_attestation_matches(
            manifest, stage, attestation_schema_version, attestation
        ):
            raise DeliveryValidationError(
                "verified receipt requires complete raw MIME attestation"
            )
    elif (attestation_schema_version is None) != (attestation is None):
        raise DeliveryValidationError(
            "ambiguous receipt attestation version and evidence must appear together"
        )
    elif attestation is not None and (
        attestation_schema_version != GMAIL_RAW_ATTESTATION_SCHEMA
        or isinstance(attestation_schema_version, bool)
    ):
        raise DeliveryValidationError("ambiguous receipt attestation schema is unsupported")
    if is_send_write_ahead:
        expected_send_attempt_count = prior_send_attempt_count + 1
        if send_attempt_count != expected_send_attempt_count:
            raise DeliveryValidationError(
                "Gmail send write-ahead must increment send_attempt_count exactly once"
            )
        if (
            not draft_id
            or not draft_message_id
            or value.get("body_verified") is not True
            or value.get("attachment_verified") is not True
            or not _verified_attestation_matches(
                manifest,
                "draft_verified",
                attestation_schema_version,
                attestation,
            )
        ):
            raise DeliveryValidationError(
                "Gmail send write-ahead requires complete verified Draft attestation"
            )
    if stage == "ambiguous" and failure_code not in CONNECTOR_FAILURE_CODES:
        if attestation is None:
            raise DeliveryValidationError(
                "raw MIME failure receipt requires validator attestation"
            )
        if failure_code.startswith("html_") and value.get("body_verified") is True:
            raise DeliveryValidationError(
                "HTML failure code contradicts body_verified"
            )
        if (
            failure_code.startswith("pdf_")
            or failure_code == "attachment_count_mismatch"
        ) and value.get("attachment_verified") is True:
            raise DeliveryValidationError(
                "attachment failure code contradicts attachment_verified"
            )
    receipt = {
        "schema_version": runtime.SCHEMA_VERSION,
        "delivery_format": DELIVERY_FORMAT,
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "report_date": report_date,
        "stage": stage,
        **required_identity,
        "gmail_draft_id": draft_id or None,
        "gmail_draft_message_id": draft_message_id or None,
        "gmail_message_id": message_id or None,
        "send_attempt_count": send_attempt_count,
        "body_verified": value.get("body_verified") is True,
        "attachment_verified": value.get("attachment_verified") is True,
        "failure_code": failure_code,
        "failure_detail": failure_detail,
        "attestation_schema_version": attestation_schema_version,
        "attestation": attestation,
        "recorded_at": runtime.utc_now(),
    }
    if effective_reauthorization_audit is not None:
        receipt["send_reauthorization"] = effective_reauthorization_audit
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path = root / "deliveries" / "delivery-receipt-v4.json"
    _preserve_legacy_receipt(root, legacy_path)
    if prior is not None:
        if prior.get("stage") == "sent_verified" and (
            stage != "sent_verified"
            or prior.get("gmail_message_id") != receipt["gmail_message_id"]
        ):
            raise DeliveryValidationError("verified SENT receipt cannot be downgraded or replaced")
    if stage == "sent_verified":
        for other_path in sorted(
            (root / "deliveries").glob("arxiv-daily-*-receipt-v4.json")
        ):
            if other_path.resolve() == receipt_path.resolve():
                continue
            other = runtime.read_json(other_path)
            if (
                other.get("stage") == "sent_verified"
                and other.get("gmail_message_id") == message_id
            ):
                raise DeliveryValidationError(
                    "each announcement date requires a distinct Gmail message ID"
                )
    runtime.atomic_write_json(receipt_path, receipt)
    # Compatibility alias only; the dated receipt above is authoritative and is
    # never replaced by another announcement date.
    runtime.atomic_write_json(legacy_path, receipt)
    result = copy_manifest(receipt)
    result["receipt"] = str(receipt_path)
    return result


def _record_delivery_receipt_value(
    root: Path,
    manifest_path: Path,
    value: dict[str, Any],
    *,
    send_lease_token: str | None = None,
) -> dict[str, Any]:
    """Atomically validate state, authorize mutation, and replace a receipt."""

    root = root.resolve()
    manifest_path = manifest_path.resolve()
    current = _send_current_time()
    state_path, _ = _gmail_send_state_paths(root, manifest_path)
    with _gmail_send_state_lock(root, manifest_path):
        state = _read_gmail_send_state(state_path)
        if _expire_gmail_send_state(state, current):
            _write_gmail_send_state(state_path, state, current)
        _require_receipt_mutation_lease(state, send_lease_token)
        is_send_disposition = bool(
            isinstance(value, dict)
            and value.get("stage") == "ambiguous"
            and value.get("failure_code") in SEND_DISPOSITION_FAILURE_CODES
        )
        active_owner = _active_send_lease_matches(state, send_lease_token)
        if is_send_disposition:
            if state.get("active_lease") is None:
                raise DeliveryValidationError(
                    "Gmail send disposition requires an active send lease"
                )
            if not active_owner:
                raise DeliveryValidationError(
                    "Gmail send disposition requires the active send lease owner token"
                )
        if active_owner:
            renewed_at = current + timedelta(seconds=GMAIL_SEND_LEASE_TTL_SECONDS)
            state["active_lease"]["expires_at"] = _send_timestamp(renewed_at)
            state["active_lease"]["renewed_at"] = _send_timestamp(current)
            _write_gmail_send_state(state_path, state, current)
        with _delivery_receipt_alias_lock(root):
            return _record_delivery_receipt_value_locked(
                root,
                manifest_path,
                value,
                allow_send_disposition_refinement=active_owner,
            )


def record_delivery_receipt(
    root: Path,
    manifest_path: Path,
    input_path: Path,
    *,
    send_lease_token: str | None = None,
) -> dict[str, Any]:
    """Persist only small Gmail Draft/SENT recovery evidence, never message bodies."""
    runtime.configure_public_runtime(root)

    return _record_delivery_receipt_value(
        root,
        manifest_path,
        runtime.read_json(input_path.resolve()),
        send_lease_token=send_lease_token,
    )


def _live_verified_draft_binding(
    root: Path,
    manifest_path: Path,
    *,
    allow_reauthorized: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = manifest_path.resolve()
    receipt_path = delivery_receipt_path(root, manifest_path)
    if not manifest_path.is_file() or not receipt_path.is_file():
        raise DeliveryValidationError(
            "send proof requires a live per-date verified Draft receipt"
        )
    manifest = runtime.read_json(manifest_path)
    receipt = runtime.read_json(receipt_path)
    try:
        recorded_manifest = Path(str(receipt.get("manifest") or "")).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise DeliveryValidationError("verified Draft receipt manifest is invalid") from exc
    if (
        manifest.get("delivery_format") != DELIVERY_FORMAT
        or manifest.get("message_count") != 1
        or receipt.get("stage") != "draft_verified"
        or recorded_manifest != manifest_path
        or receipt.get("manifest_sha256") != _sha256(manifest_path)
        or receipt.get("subject") != manifest.get("subject")
        or receipt.get("html_sha256") != manifest.get("html_sha256")
        or receipt.get("pdf_sha256") != manifest.get("pdf_sha256")
        or receipt.get("body_verified") is not True
        or receipt.get("attachment_verified") is not True
        or receipt.get("failure_code") not in (None, "")
        or receipt.get("failure_detail") not in (None, "")
    ):
        raise DeliveryValidationError(
            "send proof requires a current internally consistent verified Draft receipt"
        )
    draft_id = str(receipt.get("gmail_draft_id") or "").strip()
    draft_message_id = str(receipt.get("gmail_draft_message_id") or "").strip()
    if not draft_id or not draft_message_id:
        raise DeliveryValidationError("verified Draft receipt identity is incomplete")
    send_attempt_count = _legacy_send_attempt_count(receipt)
    if send_attempt_count >= MAX_SEND_ATTEMPTS:
        raise DeliveryValidationError("Gmail send attempt budget is exhausted")
    attestation = _normalize_attestation(receipt.get("attestation"))
    if not _verified_attestation_matches(
        manifest,
        "draft_verified",
        receipt.get("attestation_schema_version"),
        attestation,
    ):
        raise DeliveryValidationError(
            "send proof requires complete verified Draft raw MIME attestation"
        )
    reauthorization_audit = _normalize_send_reauthorization_audit(
        receipt.get("send_reauthorization")
    )
    if reauthorization_audit is not None and not allow_reauthorized:
        raise DeliveryValidationError(
            "reauthorized Draft requires its one-use reauthorization proof"
        )
    binding = {
        "proof_schema": SEND_PROOF_SCHEMA,
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "report_date": str(receipt.get("report_date") or ""),
        "subject": receipt["subject"],
        "gmail_draft_id": draft_id,
        "gmail_draft_message_id": draft_message_id,
        "html_sha256": receipt["html_sha256"],
        "pdf_sha256": receipt["pdf_sha256"],
        "send_attempt_count": send_attempt_count,
    }
    if reauthorization_audit is not None:
        binding["reauthorization_id"] = reauthorization_audit[
            "reauthorization_id"
        ]
        binding["reauthorization_schema"] = reauthorization_audit[
            "reauthorization_schema"
        ]
        binding["authorization_decision"] = reauthorization_audit[
            "authorization_decision"
        ]
        if (
            reauthorization_audit["reauthorization_schema"]
            == LEGACY_SEND_REAUTHORIZATION_SCHEMA
        ):
            binding["authorization_origin"] = LEGACY_SEND_REAUTHORIZATION_ORIGIN
            binding["exact_sent_zero_required"] = True
    return receipt, binding


def _normalize_send_proof_input(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DeliveryValidationError("send proof input must be one object")
    required = {
        "authorization_scope",
        "destination",
        "subject",
        "gmail_draft_id",
        "gmail_draft_message_id",
        "html_sha256",
        "pdf_sha256",
        "send_attempt_count",
    }
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    if missing:
        raise DeliveryValidationError(
            f"send proof input is missing fields: {', '.join(missing)}"
        )
    if extra:
        raise DeliveryValidationError(
            f"send proof input has unsupported fields: {', '.join(extra)}"
        )
    authorization_scope = str(value.get("authorization_scope") or "").strip()
    if authorization_scope != SEND_AUTHORIZATION_SCOPE:
        raise DeliveryValidationError("send proof authorization scope is invalid")
    destination = str(value.get("destination") or "").strip()
    parsed_destination = email.utils.parseaddr(destination)[1]
    if (
        not destination
        or len(destination) > 320
        or "\r" in destination
        or "\n" in destination
        or parsed_destination != destination
        or "@" not in destination
    ):
        raise DeliveryValidationError("send proof destination is invalid")
    normalized: dict[str, Any] = {
        "authorization_scope": authorization_scope,
        "destination": destination,
    }
    for field in (
        "subject",
        "gmail_draft_id",
        "gmail_draft_message_id",
        "html_sha256",
        "pdf_sha256",
    ):
        field_value = str(value.get(field) or "").strip()
        if not field_value or "\r" in field_value or "\n" in field_value:
            raise DeliveryValidationError(f"send proof {field} is invalid")
        normalized[field] = field_value
    count = value.get("send_attempt_count")
    if isinstance(count, bool) or not isinstance(count, int):
        raise DeliveryValidationError("send proof send_attempt_count must be an integer")
    normalized["send_attempt_count"] = count
    return normalized


def _blocked_send_reauthorization_binding(
    root: Path, manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    receipt_path = delivery_receipt_path(root, manifest_path)
    if not manifest_path.is_file() or not receipt_path.is_file():
        raise DeliveryValidationError(
            "send reauthorization requires the dated manifest and receipt"
        )
    manifest = runtime.read_json(manifest_path)
    receipt = runtime.read_json(receipt_path)
    match = DELIVERY_MANIFEST_NAME_RE.fullmatch(manifest_path.name)
    report_date = match.group(1) if match is not None else ""
    try:
        recorded_manifest = Path(str(receipt.get("manifest") or "")).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise DeliveryValidationError("blocked receipt manifest is invalid") from exc
    count = _legacy_send_attempt_count(receipt)
    draft_id = str(receipt.get("gmail_draft_id") or "").strip()
    draft_message_id = str(receipt.get("gmail_draft_message_id") or "").strip()
    attestation = _normalize_attestation(receipt.get("attestation"))
    if (
        manifest.get("delivery_format") != DELIVERY_FORMAT
        or manifest.get("message_count") != 1
        or receipt.get("stage") != "ambiguous"
        or receipt.get("failure_code") not in SEND_REAUTHORIZATION_FAILURE_CODES
        or count != 1
        or recorded_manifest != manifest_path
        or receipt.get("manifest_sha256") != _sha256(manifest_path)
        or receipt.get("report_date") != report_date
        or receipt.get("subject") != manifest.get("subject")
        or receipt.get("html_sha256") != manifest.get("html_sha256")
        or receipt.get("pdf_sha256") != manifest.get("pdf_sha256")
        or receipt.get("body_verified") is not True
        or receipt.get("attachment_verified") is not True
        or not draft_id
        or not draft_message_id
        or not _verified_attestation_matches(
            manifest,
            "draft_verified",
            receipt.get("attestation_schema_version"),
            attestation,
        )
    ):
        raise DeliveryValidationError(
            "send reauthorization requires one intact blocked first-attempt Draft receipt"
        )
    if receipt.get("send_reauthorization") is not None:
        raise DeliveryValidationError("send reauthorization cannot replace prior authorization")
    binding = {
        "reauthorization_schema": SEND_REAUTHORIZATION_SCHEMA,
        "reauthorization_id": secrets.token_hex(16),
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "receipt": str(receipt_path),
        "blocked_receipt_sha256": _sha256(receipt_path),
        "report_date": report_date,
        "subject": receipt["subject"],
        "gmail_draft_id": draft_id,
        "gmail_draft_message_id": draft_message_id,
        "html_sha256": receipt["html_sha256"],
        "pdf_sha256": receipt["pdf_sha256"],
        "send_attempt_count": count,
        "prior_failure_code": receipt["failure_code"],
    }
    return receipt, binding


def _normalize_send_reauthorization_input(
    value: dict[str, Any],
    *,
    expected_decision: str = SEND_REAUTHORIZATION_DECISION,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DeliveryValidationError("send reauthorization input must be one object")
    required = {
        "authorization_scope",
        "authorization_decision",
        "authorization_reason",
        "destination",
        "report_date",
        "subject",
        "gmail_draft_id",
        "gmail_draft_message_id",
        "html_sha256",
        "pdf_sha256",
        "send_attempt_count",
        "prior_failure_code",
    }
    if set(value) != required:
        raise DeliveryValidationError("send reauthorization input fields are invalid")
    if value.get("authorization_scope") != SEND_AUTHORIZATION_SCOPE:
        raise DeliveryValidationError("send reauthorization scope is invalid")
    if value.get("authorization_decision") != expected_decision:
        raise DeliveryValidationError("send reauthorization decision is invalid")
    reason = _bounded_failure_detail(value.get("authorization_reason"), required=True)
    destination = str(value.get("destination") or "").strip()
    parsed_destination = email.utils.parseaddr(destination)[1]
    if (
        not destination
        or len(destination) > 320
        or parsed_destination != destination
        or "@" not in destination
        or "\r" in destination
        or "\n" in destination
    ):
        raise DeliveryValidationError("send reauthorization destination is invalid")
    normalized: dict[str, Any] = {
        "authorization_scope": SEND_AUTHORIZATION_SCOPE,
        "authorization_decision": expected_decision,
        "authorization_reason": reason,
        "destination": destination,
    }
    for field in (
        "report_date",
        "subject",
        "gmail_draft_id",
        "gmail_draft_message_id",
        "html_sha256",
        "pdf_sha256",
        "prior_failure_code",
    ):
        field_value = str(value.get(field) or "").strip()
        if not field_value or "\r" in field_value or "\n" in field_value:
            raise DeliveryValidationError(f"send reauthorization {field} is invalid")
        normalized[field] = field_value
    count = value.get("send_attempt_count")
    if isinstance(count, bool) or not isinstance(count, int):
        raise DeliveryValidationError(
            "send reauthorization send_attempt_count must be an integer"
        )
    normalized["send_attempt_count"] = count
    return normalized


def _released_lease_matches_blocked_binding(
    released: Any,
    binding: dict[str, Any],
    *,
    authorization_scope: str | None = None,
    destination: str | None = None,
) -> bool:
    released_binding = (
        released.get("binding") if isinstance(released, dict) else None
    )
    released_destination = (
        str(released_binding.get("destination") or "").strip()
        if isinstance(released_binding, dict)
        else ""
    )
    return bool(
        isinstance(released, dict)
        and isinstance(released_binding, dict)
        and released.get("receipt_sha256") == binding["blocked_receipt_sha256"]
        and released.get("receipt_stage") == "ambiguous"
        and released.get("receipt_failure_code") == binding["prior_failure_code"]
        and released.get("receipt_send_attempt_count")
        == binding["send_attempt_count"]
        and released_binding.get("manifest") == binding["manifest"]
        and released_binding.get("gmail_draft_id") == binding["gmail_draft_id"]
        and released_binding.get("gmail_draft_message_id")
        == binding["gmail_draft_message_id"]
        and released_binding.get("html_sha256") == binding["html_sha256"]
        and released_binding.get("pdf_sha256") == binding["pdf_sha256"]
        and released_binding.get("authorization_scope") == SEND_AUTHORIZATION_SCOPE
        and email.utils.parseaddr(released_destination)[1] == released_destination
        and "@" in released_destination
        and (
            authorization_scope is None
            or released_binding.get("authorization_scope") == authorization_scope
        )
        and (
            destination is None
            or released_binding.get("destination") == destination
        )
        and not isinstance(released_binding.get("send_attempt_count"), bool)
        and isinstance(released_binding.get("send_attempt_count"), int)
        and released_binding.get("send_attempt_count") + 1
        == binding["send_attempt_count"]
    )


def issue_send_reauthorization(
    root: Path,
    manifest_path: Path,
    value: dict[str, Any],
    *,
    now: datetime | None = None,
    ttl_seconds: int = SEND_REAUTHORIZATION_TTL_SECONDS,
) -> dict[str, Any]:
    """Issue a one-use, audited grant without changing the blocked receipt."""
    runtime.configure_public_runtime(root)

    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, int)
        or not (1 <= ttl_seconds <= 900)
    ):
        raise DeliveryValidationError(
            "send reauthorization TTL must be between 1 and 900 seconds"
        )
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    normalized = _normalize_send_reauthorization_input(value)
    current = _send_current_time(now)
    state_path, _ = _gmail_send_state_paths(root, manifest_path)
    with _gmail_send_state_lock(root, manifest_path):
        state = _read_gmail_send_state(state_path)
        _expire_gmail_send_state(state, current)
        if any(
            state.get(field) is not None
            for field in ("pending_reauthorization", "pending_proof", "active_lease")
        ):
            raise DeliveryValidationError(
                "cannot issue reauthorization while another Gmail send capability is live"
            )
        _, binding = _blocked_send_reauthorization_binding(root, manifest_path)
        released = state.get("last_released_lease")
        if not _released_lease_matches_blocked_binding(
            released,
            binding,
            authorization_scope=normalized["authorization_scope"],
            destination=normalized["destination"],
        ):
            raise DeliveryValidationError(
                "send reauthorization requires a normally released matching send lease"
            )
        for field in (
            "report_date",
            "subject",
            "gmail_draft_id",
            "gmail_draft_message_id",
            "html_sha256",
            "pdf_sha256",
            "send_attempt_count",
            "prior_failure_code",
        ):
            if normalized[field] != binding[field]:
                raise DeliveryValidationError(
                    f"send reauthorization does not match blocked receipt: {field}"
                )
        binding.update(normalized)
        token = _new_send_token()
        token_sha256 = _send_token_hash(token, "send reauthorization token")
        binding_sha256 = _send_binding_sha256(binding)
        expires_at = current + timedelta(seconds=ttl_seconds)
        state["pending_reauthorization"] = {
            "reauthorization_schema": SEND_REAUTHORIZATION_SCHEMA,
            "token_sha256": token_sha256,
            "binding_sha256": binding_sha256,
            "binding": binding,
            "authorized_at": _send_timestamp(current),
            "expires_at": _send_timestamp(expires_at),
        }
        _write_gmail_send_state(state_path, state, current)
        return {
            "issued": True,
            **binding,
            "reauthorization_token": token,
            "reauthorization_token_sha256": token_sha256,
            "reauthorization_binding_sha256": binding_sha256,
            "reauthorization_expires_at": _send_timestamp(expires_at),
        }


def _legacy_recovery_fence_matches_grant(
    fence: dict[str, Any] | None,
    binding: dict[str, Any],
    binding_sha256: str,
    *,
    required_status: str,
) -> bool:
    return bool(
        fence is not None
        and fence.get("status") == required_status
        and fence.get("reauthorization_schema")
        == LEGACY_SEND_REAUTHORIZATION_SCHEMA
        and fence.get("reauthorization_id") == binding.get("reauthorization_id")
        and fence.get("manifest") == binding.get("manifest")
        and fence.get("manifest_sha256") == binding.get("manifest_sha256")
        and fence.get("report_date") == binding.get("report_date")
        and fence.get("blocked_receipt_sha256")
        == binding.get("blocked_receipt_sha256")
        and fence.get("grant_binding_sha256") == binding_sha256
        and fence.get("authorization_scope") == binding.get("authorization_scope")
        and fence.get("authorization_decision")
        == LEGACY_SEND_REAUTHORIZATION_DECISION
        and fence.get("authorization_origin")
        == LEGACY_SEND_REAUTHORIZATION_ORIGIN
        and fence.get("destination") == binding.get("destination")
        and fence.get("exact_sent_zero_required") is True
        and binding.get("exact_sent_zero_required") is True
    )


def issue_legacy_send_reauthorization(
    root: Path,
    manifest_path: Path,
    value: dict[str, Any],
    *,
    now: datetime | None = None,
    ttl_seconds: int = SEND_REAUTHORIZATION_TTL_SECONDS,
) -> dict[str, Any]:
    """Issue the sole grant for an intact pre-fence legacy unknown-send receipt."""
    runtime.configure_public_runtime(root)

    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, int)
        or not (1 <= ttl_seconds <= 900)
    ):
        raise DeliveryValidationError(
            "legacy send reauthorization TTL must be between 1 and 900 seconds"
        )
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    normalized = _normalize_send_reauthorization_input(
        value,
        expected_decision=LEGACY_SEND_REAUTHORIZATION_DECISION,
    )
    current = _send_current_time(now)
    state_path, _ = _gmail_send_state_paths(root, manifest_path)
    with _gmail_send_state_lock(root, manifest_path):
        state_existed = state_path.is_file()
        state = _read_gmail_send_state(state_path)
        if _expire_gmail_send_state(state, current):
            _write_gmail_send_state(state_path, state, current)
            state_existed = True
        if state.get("legacy_recovery_fence") is not None:
            raise DeliveryValidationError(
                "legacy Gmail recovery authorization was already issued for this date"
            )
        if state_existed:
            raise DeliveryValidationError(
                "legacy Gmail recovery requires pristine pre-fence send state"
            )
        if any(
            state.get(field) is not None
            for field in (
                "pending_reauthorization",
                "pending_proof",
                "reauthorization_proof_state",
                "active_lease",
                "last_released_lease",
            )
        ):
            raise DeliveryValidationError(
                "legacy Gmail recovery rejects existing send capabilities or lease history"
            )
        receipt, binding = _blocked_send_reauthorization_binding(
            root, manifest_path
        )
        if (
            receipt.get("stage") != "ambiguous"
            or receipt.get("failure_code") != "gmail_send_outcome_unknown"
            or "send_attempt_count" in receipt
            or _legacy_send_attempt_count(receipt) != 1
        ):
            raise DeliveryValidationError(
                "legacy Gmail recovery requires one intact implicit first attempt"
            )
        for field in (
            "report_date",
            "subject",
            "gmail_draft_id",
            "gmail_draft_message_id",
            "html_sha256",
            "pdf_sha256",
            "send_attempt_count",
            "prior_failure_code",
        ):
            if normalized[field] != binding[field]:
                raise DeliveryValidationError(
                    f"legacy send reauthorization does not match blocked receipt: {field}"
                )
        binding.update(normalized)
        binding.update(
            {
                "reauthorization_schema": LEGACY_SEND_REAUTHORIZATION_SCHEMA,
                "reauthorization_id": secrets.token_hex(16),
                "authorization_origin": LEGACY_SEND_REAUTHORIZATION_ORIGIN,
                "exact_sent_zero_required": True,
            }
        )
        token = _new_send_token()
        token_sha256 = _send_token_hash(
            token, "legacy send reauthorization token"
        )
        binding_sha256 = _send_binding_sha256(binding)
        expires_at = current + timedelta(seconds=ttl_seconds)
        state["pending_reauthorization"] = {
            "reauthorization_schema": LEGACY_SEND_REAUTHORIZATION_SCHEMA,
            "token_sha256": token_sha256,
            "binding_sha256": binding_sha256,
            "binding": binding,
            "authorized_at": _send_timestamp(current),
            "expires_at": _send_timestamp(expires_at),
        }
        state["legacy_recovery_fence"] = {
            "fence_schema": LEGACY_RECOVERY_FENCE_SCHEMA,
            "status": "issued",
            "reauthorization_schema": LEGACY_SEND_REAUTHORIZATION_SCHEMA,
            "reauthorization_id": binding["reauthorization_id"],
            "manifest": binding["manifest"],
            "manifest_sha256": binding["manifest_sha256"],
            "report_date": binding["report_date"],
            "blocked_receipt_sha256": binding["blocked_receipt_sha256"],
            "grant_binding_sha256": binding_sha256,
            "authorization_scope": binding["authorization_scope"],
            "authorization_decision": LEGACY_SEND_REAUTHORIZATION_DECISION,
            "authorization_origin": LEGACY_SEND_REAUTHORIZATION_ORIGIN,
            "destination": binding["destination"],
            "exact_sent_zero_required": True,
            "token_rotation_count": 0,
            "issued_at": _send_timestamp(current),
            "expires_at": _send_timestamp(expires_at),
            "finalized_at": None,
        }
        _write_gmail_send_state(state_path, state, current)
        return {
            "issued": True,
            **binding,
            "reauthorization_token": token,
            "reauthorization_token_sha256": token_sha256,
            "reauthorization_binding_sha256": binding_sha256,
            "reauthorization_expires_at": _send_timestamp(expires_at),
        }


def rotate_legacy_send_reauthorization_token(
    root: Path,
    manifest_path: Path,
    reauthorization_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Rotate one lost legacy grant bearer without changing its authorization."""
    runtime.configure_public_runtime(root)

    normalized_id = str(reauthorization_id or "").strip()
    if re.fullmatch(r"[0-9a-f]{32}", normalized_id) is None:
        raise DeliveryValidationError(
            "legacy send reauthorization id is invalid"
        )
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    current = _send_current_time(now)
    state_path, _ = _gmail_send_state_paths(root, manifest_path)
    with _gmail_send_state_lock(root, manifest_path):
        state = _read_gmail_send_state(state_path)
        grant = state.get("pending_reauthorization")
        if (
            not isinstance(grant, dict)
            or grant.get("reauthorization_schema")
            != LEGACY_SEND_REAUTHORIZATION_SCHEMA
        ):
            raise DeliveryValidationError(
                "pending legacy send reauthorization is unavailable"
            )
        expires_at = _parse_send_timestamp(
            grant.get("expires_at"), "legacy send reauthorization expiry"
        )
        if expires_at <= current:
            if _expire_gmail_send_state(state, current):
                _write_gmail_send_state(state_path, state, current)
            raise DeliveryValidationError(
                "pending legacy send reauthorization is expired"
            )
        if any(
            state.get(field) is not None
            for field in (
                "pending_proof",
                "reauthorization_proof_state",
                "active_lease",
                "last_released_lease",
            )
        ):
            raise DeliveryValidationError(
                "legacy send reauthorization token rotation rejects proof or lease state"
            )
        binding = dict(grant.get("binding") or {})
        binding_sha256 = str(grant.get("binding_sha256") or "").strip()
        if (
            binding.get("reauthorization_id") != normalized_id
            or grant.get("binding_sha256") != _send_binding_sha256(binding)
        ):
            raise DeliveryValidationError(
                "legacy send reauthorization id or binding hash is invalid"
            )
        fence = _normalize_legacy_recovery_fence(
            state.get("legacy_recovery_fence")
        )
        if not _legacy_recovery_fence_matches_grant(
            fence,
            binding,
            binding_sha256,
            required_status="issued",
        ):
            raise DeliveryValidationError(
                "legacy send reauthorization lost its issued recovery fence"
            )
        if fence["token_rotation_count"] != 0:
            raise DeliveryValidationError(
                "legacy send reauthorization token was already rotated"
            )
        current_receipt, current_binding = _blocked_send_reauthorization_binding(
            root, manifest_path
        )
        if (
            current_receipt.get("stage") != "ambiguous"
            or current_receipt.get("failure_code")
            != "gmail_send_outcome_unknown"
            or "send_attempt_count" in current_receipt
            or _legacy_send_attempt_count(current_receipt) != 1
        ):
            raise DeliveryValidationError(
                "legacy token rotation requires the unchanged implicit first attempt"
            )
        for field in (
            "manifest",
            "manifest_sha256",
            "receipt",
            "blocked_receipt_sha256",
            "report_date",
            "subject",
            "gmail_draft_id",
            "gmail_draft_message_id",
            "html_sha256",
            "pdf_sha256",
            "send_attempt_count",
            "prior_failure_code",
        ):
            if binding.get(field) != current_binding.get(field):
                raise DeliveryValidationError(
                    f"legacy token rotation detected blocked receipt drift: {field}"
                )
        token = _new_send_token()
        token_sha256 = _send_token_hash(
            token, "rotated legacy send reauthorization token"
        )
        state["pending_reauthorization"] = {
            **grant,
            "token_sha256": token_sha256,
        }
        state["legacy_recovery_fence"] = {
            **fence,
            "token_rotation_count": 1,
        }
        _write_gmail_send_state(state_path, state, current)
        return {
            "issued": True,
            "rotated": True,
            **binding,
            "reauthorization_token": token,
            "reauthorization_token_sha256": token_sha256,
            "reauthorization_binding_sha256": binding_sha256,
            "reauthorization_expires_at": _send_timestamp(expires_at),
            "token_rotation_count": 1,
        }


def prepare_reauthorized_send_proof(
    root: Path,
    manifest_path: Path,
    reauthorization_token: str,
    value: dict[str, Any],
    *,
    now: datetime | None = None,
    ttl_seconds: int = SEND_PROOF_TTL_SECONDS,
) -> dict[str, Any]:
    """Consume one grant, restore the same verified Draft, and mint one proof."""
    runtime.configure_public_runtime(root)

    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, int)
        or not (1 <= ttl_seconds <= 900)
    ):
        raise DeliveryValidationError("send proof TTL must be between 1 and 900 seconds")
    supplied_token_hash = _send_token_hash(
        reauthorization_token, "send reauthorization token"
    )
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    current = _send_current_time(now)
    state_path, _ = _gmail_send_state_paths(root, manifest_path)
    with _gmail_send_state_lock(root, manifest_path):
        state = _read_gmail_send_state(state_path)
        if _expire_gmail_send_state(state, current):
            _write_gmail_send_state(state_path, state, current)
        grant = state.get("pending_reauthorization")
        if grant is None or not hmac.compare_digest(
            str(grant.get("token_sha256") or ""), supplied_token_hash
        ):
            raise DeliveryValidationError(
                "send reauthorization is missing, expired, consumed, or superseded"
            )
        if state.get("pending_proof") is not None or state.get("active_lease") is not None:
            raise DeliveryValidationError(
                "send reauthorization cannot consume alongside another send capability"
            )
        binding = dict(grant["binding"])
        current_receipt, current_binding = _blocked_send_reauthorization_binding(
            root, manifest_path
        )
        for field in (
            "manifest",
            "manifest_sha256",
            "receipt",
            "blocked_receipt_sha256",
            "report_date",
            "subject",
            "gmail_draft_id",
            "gmail_draft_message_id",
            "html_sha256",
            "pdf_sha256",
            "send_attempt_count",
            "prior_failure_code",
        ):
            if binding.get(field) != current_binding.get(field):
                raise DeliveryValidationError(
                    f"send reauthorization is stale: {field}"
                )
        if grant.get("binding_sha256") != _send_binding_sha256(binding):
            raise DeliveryValidationError("send reauthorization binding hash is invalid")
        reauthorization_schema = grant.get("reauthorization_schema")
        if binding.get("reauthorization_schema") != reauthorization_schema:
            raise DeliveryValidationError(
                "send reauthorization schema changed inside its binding"
            )
        is_legacy_reauthorization = (
            reauthorization_schema == LEGACY_SEND_REAUTHORIZATION_SCHEMA
        )
        if is_legacy_reauthorization:
            fence = _normalize_legacy_recovery_fence(
                state.get("legacy_recovery_fence")
            )
            if (
                current_receipt.get("failure_code")
                != "gmail_send_outcome_unknown"
                or "send_attempt_count" in current_receipt
                or binding.get("authorization_decision")
                != LEGACY_SEND_REAUTHORIZATION_DECISION
                or binding.get("authorization_origin")
                != LEGACY_SEND_REAUTHORIZATION_ORIGIN
                or binding.get("exact_sent_zero_required") is not True
                or not _legacy_recovery_fence_matches_grant(
                    fence,
                    binding,
                    str(grant.get("binding_sha256") or ""),
                    required_status="issued",
                )
            ):
                raise DeliveryValidationError(
                    "legacy send reauthorization lost its one-shot recovery fence"
                )
        elif (
            reauthorization_schema != SEND_REAUTHORIZATION_SCHEMA
            or binding.get("authorization_decision")
            != SEND_REAUTHORIZATION_DECISION
            or "authorization_origin" in binding
            or "exact_sent_zero_required" in binding
        ):
            raise DeliveryValidationError(
                "ordinary send reauthorization binding is invalid"
            )
        draft_value = dict(value)
        if (
            draft_value.get("stage") != "draft_verified"
            or draft_value.get("subject") != binding["subject"]
            or draft_value.get("gmail_draft_id") != binding["gmail_draft_id"]
            or draft_value.get("gmail_draft_message_id")
            != binding["gmail_draft_message_id"]
            or draft_value.get("html_sha256") != binding["html_sha256"]
            or draft_value.get("pdf_sha256") != binding["pdf_sha256"]
        ):
            raise DeliveryValidationError(
                "reauthorization requires a fresh matching verified Draft attestation"
            )
        supplied_count = draft_value.get("send_attempt_count")
        if supplied_count is not None and supplied_count != binding["send_attempt_count"]:
            raise DeliveryValidationError(
                "reauthorized Draft send_attempt_count does not match the grant"
            )
        draft_value["send_attempt_count"] = binding["send_attempt_count"]
        draft_value["failure_code"] = None
        draft_value["failure_detail"] = None
        audit = {
            "reauthorization_schema": reauthorization_schema,
            "reauthorization_id": binding["reauthorization_id"],
            "authorization_scope": binding["authorization_scope"],
            "authorization_decision": binding["authorization_decision"],
            "authorization_reason": binding["authorization_reason"],
            "destination": binding["destination"],
            "prior_failure_code": binding["prior_failure_code"],
            "blocked_receipt_sha256": binding["blocked_receipt_sha256"],
            "grant_binding_sha256": grant["binding_sha256"],
            "authorized_at": grant["authorized_at"],
            "consumed_at": _send_timestamp(current),
        }
        proof_binding = {
            "proof_schema": SEND_PROOF_SCHEMA,
            "manifest": binding["manifest"],
            "manifest_sha256": binding["manifest_sha256"],
            "report_date": binding["report_date"],
            "subject": binding["subject"],
            "gmail_draft_id": binding["gmail_draft_id"],
            "gmail_draft_message_id": binding["gmail_draft_message_id"],
            "html_sha256": binding["html_sha256"],
            "pdf_sha256": binding["pdf_sha256"],
            "send_attempt_count": binding["send_attempt_count"],
            "reauthorization_id": binding["reauthorization_id"],
            "reauthorization_schema": reauthorization_schema,
            "authorization_decision": binding["authorization_decision"],
            "authorization_scope": binding["authorization_scope"],
            "destination": binding["destination"],
        }
        if is_legacy_reauthorization:
            proof_binding.update(
                {
                    "authorization_origin": LEGACY_SEND_REAUTHORIZATION_ORIGIN,
                    "exact_sent_zero_required": True,
                }
            )
        proof_token = _new_send_token()
        proof_token_sha256 = _send_token_hash(proof_token, "send proof token")
        proof_sha256 = _send_binding_sha256(proof_binding)
        proof_expires_at = current + timedelta(seconds=ttl_seconds)
        state["pending_reauthorization"] = None
        state["pending_proof"] = {
            "proof_schema": SEND_PROOF_SCHEMA,
            "token_sha256": proof_token_sha256,
            "proof_sha256": proof_sha256,
            "binding": proof_binding,
            "created_at": _send_timestamp(current),
            "expires_at": _send_timestamp(proof_expires_at),
        }
        state["reauthorization_proof_state"] = {
            "reauthorization_id": binding["reauthorization_id"],
            "proof_sha256": proof_sha256,
            "lease_acquired_at": None,
            "reissue_count": 0,
        }
        state["last_reauthorization"] = audit
        if is_legacy_reauthorization:
            state["legacy_recovery_fence"] = {
                **fence,
                "status": "consumed",
                "finalized_at": _send_timestamp(current),
            }
        _write_gmail_send_state(state_path, state, current)
        with _delivery_receipt_alias_lock(root):
            receipt = _record_delivery_receipt_value_locked(
                root,
                manifest_path,
                draft_value,
                allow_explicit_reauthorization=True,
                reauthorization_audit=audit,
            )
        return {
            "prepared": True,
            **proof_binding,
            "proof_token": proof_token,
            "proof_token_sha256": proof_token_sha256,
            "proof_sha256": proof_sha256,
            "proof_expires_at": _send_timestamp(proof_expires_at),
            "reauthorization_consumed": True,
            "reauthorized_receipt": receipt["receipt"],
        }


def prepare_send_proof(
    root: Path,
    manifest_path: Path,
    value: dict[str, Any],
    *,
    now: datetime | None = None,
    ttl_seconds: int = SEND_PROOF_TTL_SECONDS,
) -> dict[str, Any]:
    """Create a persistent, one-use proof from the live verified Draft receipt."""
    runtime.configure_public_runtime(root)

    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, int)
        or not (1 <= ttl_seconds <= 900)
    ):
        raise DeliveryValidationError("send proof TTL must be between 1 and 900 seconds")
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    normalized = _normalize_send_proof_input(value)
    current = _send_current_time(now)
    state_path, _ = _gmail_send_state_paths(root, manifest_path)
    with _gmail_send_state_lock(root, manifest_path):
        state = _read_gmail_send_state(state_path)
        _expire_gmail_send_state(state, current)
        if state.get("active_lease") is not None:
            raise DeliveryValidationError(
                "cannot prepare a send proof while a Gmail send lease is active"
            )
        if state.get("pending_proof") is not None:
            raise DeliveryValidationError(
                "cannot replace an unexpired one-use Gmail send proof"
            )
        if state.get("pending_reauthorization") is not None:
            raise DeliveryValidationError(
                "pending explicit reauthorization must be consumed or expire first"
            )
        receipt_path = delivery_receipt_path(root, manifest_path)
        stored_receipt = (
            runtime.read_json(receipt_path) if receipt_path.is_file() else {}
        )
        reauthorization_audit = _normalize_send_reauthorization_audit(
            stored_receipt.get("send_reauthorization")
        )
        stored_send_attempt_count = _legacy_send_attempt_count(stored_receipt)
        if stored_send_attempt_count > 0 and reauthorization_audit is None:
            raise DeliveryValidationError(
                "Draft with a prior Gmail send attempt requires active same-lease recovery or explicit reauthorization"
            )
        reauthorization_proof_state = state.get("reauthorization_proof_state")
        can_reissue_reauthorization_proof = bool(
            reauthorization_audit is not None
            and isinstance(reauthorization_proof_state, dict)
            and reauthorization_proof_state.get("reauthorization_id")
            == reauthorization_audit["reauthorization_id"]
            and reauthorization_proof_state.get("reissue_count", 0) < 16
        )
        _, receipt_binding = _live_verified_draft_binding(
            root,
            manifest_path,
            allow_reauthorized=can_reissue_reauthorization_proof,
        )
        if reauthorization_audit is not None:
            if not can_reissue_reauthorization_proof:
                raise DeliveryValidationError(
                    "reauthorized Draft proof was already leased and requires explicit recovery"
                )
            if (
                normalized["destination"] != reauthorization_audit["destination"]
                or normalized["authorization_scope"]
                != reauthorization_audit["authorization_scope"]
            ):
                raise DeliveryValidationError(
                    "reauthorized Draft proof destination or scope changed"
                )
        for field in (
            "subject",
            "gmail_draft_id",
            "gmail_draft_message_id",
            "html_sha256",
            "pdf_sha256",
            "send_attempt_count",
        ):
            if normalized[field] != receipt_binding[field]:
                raise DeliveryValidationError(
                    f"send proof does not match the live Draft receipt: {field}"
                )
        binding = {
            **receipt_binding,
            "authorization_scope": normalized["authorization_scope"],
            "destination": normalized["destination"],
        }
        proof_token = _new_send_token()
        proof_token_sha256 = _send_token_hash(proof_token, "send proof token")
        proof_sha256 = _send_binding_sha256(binding)
        expires_at = current + timedelta(seconds=ttl_seconds)
        state["pending_proof"] = {
            "proof_schema": SEND_PROOF_SCHEMA,
            "token_sha256": proof_token_sha256,
            "proof_sha256": proof_sha256,
            "binding": binding,
            "created_at": _send_timestamp(current),
            "expires_at": _send_timestamp(expires_at),
        }
        if can_reissue_reauthorization_proof:
            state["reauthorization_proof_state"] = {
                **reauthorization_proof_state,
                "proof_sha256": proof_sha256,
                "lease_acquired_at": None,
                "reissue_count": reauthorization_proof_state["reissue_count"] + 1,
            }
        _write_gmail_send_state(state_path, state, current)
        return {
            "prepared": True,
            **binding,
            "proof_token": proof_token,
            "proof_token_sha256": proof_token_sha256,
            "proof_sha256": proof_sha256,
            "proof_expires_at": _send_timestamp(expires_at),
        }


def _validate_proof_receipt_binding(
    root: Path, manifest_path: Path, binding: dict[str, Any]
) -> dict[str, Any]:
    receipt, current_binding = _live_verified_draft_binding(
        root,
        manifest_path,
        allow_reauthorized=bool(binding.get("reauthorization_id")),
    )
    for field, expected in current_binding.items():
        if binding.get(field) != expected:
            raise DeliveryValidationError(
                f"send proof is stale relative to the Draft receipt: {field}"
            )
    if binding.get("authorization_scope") != SEND_AUTHORIZATION_SCOPE:
        raise DeliveryValidationError("send proof authorization scope is invalid")
    destination = str(binding.get("destination") or "").strip()
    if not destination:
        raise DeliveryValidationError("send proof destination is invalid")
    return receipt


def acquire_gmail_send_lease(
    root: Path,
    manifest_path: Path,
    proof_token: str,
    owner: str,
    *,
    wait_seconds: float = 10.0,
    lease_seconds: int = GMAIL_SEND_LEASE_TTL_SECONDS,
) -> dict[str, Any]:
    """Consume one proof and acquire the persistent per-manifest send lease."""
    runtime.configure_public_runtime(root)

    normalized_owner = str(owner or "").strip()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}", normalized_owner) is None:
        raise DeliveryValidationError("Gmail send lease owner is invalid")
    if (
        isinstance(wait_seconds, bool)
        or not isinstance(wait_seconds, (int, float))
        or not (0 <= float(wait_seconds) <= GMAIL_SEND_WAIT_MAX_SECONDS)
    ):
        raise DeliveryValidationError(
            f"Gmail send lease wait must be between 0 and {GMAIL_SEND_WAIT_MAX_SECONDS:g} seconds"
        )
    if (
        isinstance(lease_seconds, bool)
        or not isinstance(lease_seconds, int)
        or not (1 <= lease_seconds <= 3600)
    ):
        raise DeliveryValidationError("Gmail send lease TTL must be between 1 and 3600 seconds")
    supplied_proof_hash = _send_token_hash(proof_token, "send proof token")
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    state_path, _ = _gmail_send_state_paths(root, manifest_path)
    deadline = time.monotonic() + float(wait_seconds)
    while True:
        current = _send_current_time()
        retry_after = 0.05
        with _gmail_send_state_lock(
            root,
            manifest_path,
            timeout_seconds=max(0.0, min(10.0, deadline - time.monotonic())),
        ):
            state = _read_gmail_send_state(state_path)
            state_changed = _expire_gmail_send_state(state, current)
            active = state.get("active_lease")
            if active is None:
                proof = state.get("pending_proof")
                if proof is None or not hmac.compare_digest(
                    str(proof.get("token_sha256") or ""), supplied_proof_hash
                ):
                    if state_changed:
                        _write_gmail_send_state(state_path, state, current)
                    raise DeliveryValidationError(
                        "send proof is missing, expired, consumed, or superseded"
                    )
                binding = dict(proof["binding"])
                try:
                    receipt = _validate_proof_receipt_binding(
                        root, manifest_path, binding
                    )
                    if proof.get("proof_sha256") != _send_binding_sha256(binding):
                        raise DeliveryValidationError("send proof binding hash is invalid")
                except DeliveryValidationError:
                    state["pending_proof"] = None
                    _write_gmail_send_state(state_path, state, current)
                    raise
                reauthorization_id = binding.get("reauthorization_id")
                if reauthorization_id is not None:
                    reauthorization_proof_state = state.get(
                        "reauthorization_proof_state"
                    )
                    if (
                        not isinstance(reauthorization_proof_state, dict)
                        or reauthorization_proof_state.get("reauthorization_id")
                        != reauthorization_id
                        or reauthorization_proof_state.get("proof_sha256")
                        != proof.get("proof_sha256")
                        or reauthorization_proof_state.get("lease_acquired_at")
                        is not None
                    ):
                        state["pending_proof"] = None
                        _write_gmail_send_state(state_path, state, current)
                        raise DeliveryValidationError(
                            "reauthorized proof is not the live unleased one-use proof"
                        )
                    reauthorization_proof_state["lease_acquired_at"] = (
                        _send_timestamp(current)
                    )
                lease_token = _new_send_token()
                lease_token_sha256 = _send_token_hash(
                    lease_token, "Gmail send lease token"
                )
                expires_at = current + timedelta(seconds=lease_seconds)
                state["pending_proof"] = None
                state["active_lease"] = {
                    "token_sha256": lease_token_sha256,
                    "proof_sha256": proof["proof_sha256"],
                    "binding": binding,
                    "owner": normalized_owner,
                    "acquired_at": _send_timestamp(current),
                    "expires_at": _send_timestamp(expires_at),
                }
                _write_gmail_send_state(state_path, state, current)
                return {
                    "acquired": True,
                    "lease_token": lease_token,
                    "lease_expires_at": _send_timestamp(expires_at),
                    "proof_sha256": proof["proof_sha256"],
                    "authorization_scope": binding["authorization_scope"],
                    "destination": binding["destination"],
                    "manifest": binding["manifest"],
                    "manifest_sha256": binding["manifest_sha256"],
                    "subject": binding["subject"],
                    "html_sha256": binding["html_sha256"],
                    "pdf_sha256": binding["pdf_sha256"],
                    "reauthorization_id": binding.get("reauthorization_id"),
                    "reauthorization_schema": binding.get(
                        "reauthorization_schema"
                    ),
                    "authorization_decision": binding.get(
                        "authorization_decision"
                    ),
                    "authorization_origin": binding.get("authorization_origin"),
                    "exact_sent_zero_required": binding.get(
                        "exact_sent_zero_required"
                    ),
                    "receipt_stage": receipt["stage"],
                    "send_attempt_count": _legacy_send_attempt_count(receipt),
                    "gmail_draft_id": receipt["gmail_draft_id"],
                    "gmail_draft_message_id": receipt["gmail_draft_message_id"],
                }
            retry_after = max(
                0.05,
                (
                    _parse_send_timestamp(active.get("expires_at"), "lease expiry")
                    - current
                ).total_seconds(),
            )
            if state_changed:
                _write_gmail_send_state(state_path, state, current)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DeliveryValidationError(
                "timed out waiting for the per-manifest Gmail send lease"
            )
        time.sleep(min(retry_after, remaining, 0.25))


def release_gmail_send_lease(
    root: Path,
    manifest_path: Path,
    lease_token: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Release only the active lease matching the caller's bearer token."""
    runtime.configure_public_runtime(root)

    supplied_hash = _send_token_hash(lease_token, "Gmail send lease token")
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    current = _send_current_time(now)
    state_path, _ = _gmail_send_state_paths(root, manifest_path)
    with _gmail_send_state_lock(root, manifest_path):
        state = _read_gmail_send_state(state_path)
        expired = _expire_gmail_send_state(state, current)
        active = state.get("active_lease")
        if active is None:
            if expired:
                _write_gmail_send_state(state_path, state, current)
            released = state.get("last_released_lease")
            if (
                isinstance(released, dict)
                and isinstance(released.get("token_sha256"), str)
                and hmac.compare_digest(released["token_sha256"], supplied_hash)
            ):
                return {
                    "released": True,
                    "owner": released["owner"],
                    "replayed": True,
                }
            raise DeliveryValidationError("Gmail send lease is not active")
        if not hmac.compare_digest(str(active["token_sha256"]), supplied_hash):
            raise DeliveryValidationError(
                "Gmail send lease token does not own the active lease"
            )
        receipt_path = delivery_receipt_path(root, manifest_path)
        if not receipt_path.is_file():
            raise DeliveryValidationError(
                "Gmail send lease cannot release without the dated receipt"
            )
        receipt = runtime.read_json(receipt_path)
        state["last_released_lease"] = {
            "token_sha256": active["token_sha256"],
            "proof_sha256": active["proof_sha256"],
            "binding": active["binding"],
            "owner": active["owner"],
            "released_at": _send_timestamp(current),
            "receipt_sha256": _sha256(receipt_path),
            "receipt_stage": receipt.get("stage"),
            "receipt_failure_code": receipt.get("failure_code"),
            "receipt_send_attempt_count": _legacy_send_attempt_count(receipt),
        }
        state["active_lease"] = None
        state["released_at"] = _send_timestamp(current)
        _write_gmail_send_state(state_path, state, current)
        return {"released": True, "owner": active["owner"]}


def read_receipt_stdin(stream: BinaryIO) -> dict[str, Any]:
    """Read one length-framed receipt without relying on PTY newline bytes."""

    try:
        prefix = _read_exact(stream, len(RECEIPT_FRAME_MAGIC))
        if prefix != RECEIPT_FRAME_MAGIC.encode("ascii"):
            raise DeliveryValidationError("receipt stdin frame magic is invalid")
        header = (prefix + _read_until_marker(stream, b";", 32)).decode("ascii")
        match = re.fullmatch(rf"{RECEIPT_FRAME_MAGIC} (\d+)", header)
        if match is None:
            raise DeliveryValidationError("receipt stdin frame header is invalid")
        size = int(match.group(1))
        if not (1 <= size <= 64 * 1024):
            raise DeliveryValidationError(
                "receipt stdin frame exceeds the 64 KiB bound"
            )
        line = _read_exact_segment(stream, size)
    except GmailRawFrameError as exc:
        raise DeliveryValidationError(str(exc)) from exc
    try:
        value = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeliveryValidationError("receipt stdin is not valid JSON") from exc
    if not isinstance(value, dict):
        raise DeliveryValidationError("receipt stdin must contain one object")
    return value


def prepare_framed_stdin() -> None:
    """Put a PTY in byte-oriented no-echo mode before framed secret input."""

    if sys.stdin.isatty():
        try:
            if os.name == "nt":
                import ctypes
                import msvcrt

                handle = msvcrt.get_osfhandle(sys.stdin.fileno())
                mode = ctypes.c_uint()
                kernel32 = ctypes.windll.kernel32
                if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                    raise OSError("GetConsoleMode failed")
                # ENABLE_LINE_INPUT (0x0002) waits for a newline and has a
                # console line-buffer limit.  Gmail raw is one long base64url
                # value, so both line input and echo must be disabled.
                if not kernel32.SetConsoleMode(
                    handle, mode.value & ~0x0002 & ~0x0004
                ):
                    raise OSError("SetConsoleMode failed")
            else:
                import termios

                attributes = termios.tcgetattr(sys.stdin.fileno())
                attributes[3] &= ~(termios.ECHO | termios.ICANON)
                attributes[6][termios.VMIN] = 1
                attributes[6][termios.VTIME] = 0
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSANOW, attributes
                )
        except (AttributeError, OSError, ValueError):
            raise DeliveryValidationError(
                "cannot disable terminal echo for framed Gmail input"
            )
    print("DAX_STDIN_READY", flush=True)


def delivery_receipt_status(
    root: Path, manifest_path: Path | None = None
) -> dict[str, Any]:
    runtime.configure_public_runtime(root)
    root = root.resolve()
    expected_manifest: Path | None = None
    if manifest_path is not None:
        expected_manifest = manifest_path.resolve()
    else:
        pending_path = root / "pending-run.json"
        if pending_path.is_file():
            pending = runtime.read_json(pending_path)
            report_date = str(pending.get("date") or "").strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
                expected_manifest = (
                    root
                    / "deliveries"
                    / f"arxiv-daily-{report_date}-delivery.json"
                ).resolve()
    path = (
        delivery_receipt_path(root, expected_manifest)
        if expected_manifest is not None
        else root / "deliveries" / "delivery-receipt-v4.json"
    )
    if not path.is_file() and expected_manifest is not None:
        legacy_path = root / "deliveries" / "delivery-receipt-v4.json"
        if legacy_path.is_file():
            legacy = runtime.read_json(legacy_path)
            try:
                recorded_manifest = Path(
                    str(legacy.get("manifest") or "")
                ).resolve()
            except (OSError, RuntimeError, ValueError):
                recorded_manifest = None
            if recorded_manifest == expected_manifest:
                path = legacy_path
    if not path.is_file():
        return {"schema_version": runtime.SCHEMA_VERSION, "stage": None, "next_action": "search_exact_subject"}
    value = runtime.read_json(path)
    stage = value.get("stage")
    stored_failure_code = value.get("failure_code")
    stored_failure_detail = value.get("failure_detail")
    try:
        stored_send_attempt_count: int | None = _legacy_send_attempt_count(value)
        send_attempt_count_valid = True
    except DeliveryValidationError:
        stored_send_attempt_count = None
        send_attempt_count_valid = False
    verified_stage_consistent = True
    if stage in {"draft_verified", "sent_verified"}:
        try:
            recorded_manifest = Path(str(value.get("manifest") or "")).resolve()
            manifest = runtime.read_json(recorded_manifest)
            has_new_attestation = (
                "attestation_schema_version" in value or "attestation" in value
            )
            normalized_attestation = (
                _normalize_attestation(value.get("attestation"))
                if has_new_attestation
                else None
            )
            verified_stage_consistent = bool(
                recorded_manifest.is_file()
                and (
                    expected_manifest is None
                    or recorded_manifest == expected_manifest
                )
                and value.get("manifest_sha256") == _sha256(recorded_manifest)
                and value.get("subject") == manifest.get("subject")
                and value.get("html_sha256") == manifest.get("html_sha256")
                and value.get("pdf_sha256") == manifest.get("pdf_sha256")
                and value.get("body_verified") is True
                and value.get("attachment_verified") is True
                and send_attempt_count_valid
                and (
                    stage != "draft_verified"
                    or bool(str(value.get("gmail_draft_id") or "").strip())
                )
                and (
                    stage != "draft_verified"
                    or not has_new_attestation
                    or bool(
                        str(value.get("gmail_draft_message_id") or "").strip()
                    )
                )
                and (
                    stage != "sent_verified"
                    or bool(str(value.get("gmail_message_id") or "").strip())
                )
                and (stored_failure_code is None or stored_failure_code == "")
                and (stored_failure_detail is None or stored_failure_detail == "")
                and (
                    not has_new_attestation
                    or _verified_attestation_matches(
                        manifest,
                        stage,
                        value.get("attestation_schema_version"),
                        normalized_attestation,
                    )
                )
            )
        except (DeliveryValidationError, OSError, RuntimeError, ValueError):
            verified_stage_consistent = False
    next_action = {
        "draft_verified": "reconcile_exact_sent_then_draft",
        "sent_verified": "commit_success",
        "ambiguous": "reconcile_exact_sent_then_draft",
    }.get(stage, "reconcile_exact_sent_then_draft")
    if (
        stage == "ambiguous"
        and stored_failure_code in SEND_REAUTHORIZATION_FAILURE_CODES
    ):
        if not send_attempt_count_valid:
            next_action = "reconcile_exact_sent_then_draft"
        elif stored_send_attempt_count >= MAX_SEND_ATTEMPTS:
            next_action = "reconcile_exact_sent_only_attempt_budget_exhausted"
        elif (
            stored_failure_code == "gmail_send_outcome_unknown"
            and "send_attempt_count" not in value
        ):
            next_action = "reconcile_exact_sent_only_legacy_unreleased"
        else:
            next_action = "reconcile_exact_sent_only_unreleased"
            try:
                recorded_manifest = Path(str(value.get("manifest") or "")).resolve()
                _, blocked_binding = _blocked_send_reauthorization_binding(
                    root, recorded_manifest
                )
                state_path, _ = _gmail_send_state_paths(root, recorded_manifest)
                state = _read_gmail_send_state(state_path)
                if _released_lease_matches_blocked_binding(
                    state.get("last_released_lease"), blocked_binding
                ):
                    next_action = "await_explicit_send_reauthorization"
            except (DeliveryValidationError, OSError, RuntimeError, ValueError):
                next_action = "reconcile_exact_sent_only_unreleased"
    if not verified_stage_consistent:
        next_action = "reconcile_exact_sent_then_draft"
    if (
        send_attempt_count_valid
        and stored_send_attempt_count >= MAX_SEND_ATTEMPTS
        and stage != "sent_verified"
    ):
        next_action = "reconcile_exact_sent_only_attempt_budget_exhausted"
    elif (
        stage == "draft_verified"
        and send_attempt_count_valid
        and stored_send_attempt_count > 0
        and value.get("send_reauthorization") is None
    ):
        next_action = "reconcile_exact_sent_only_prior_attempt_unleased"
    return {
        "schema_version": value.get("schema_version"),
        "stage": stage,
        "gmail_draft_id": value.get("gmail_draft_id"),
        "gmail_draft_message_id": value.get("gmail_draft_message_id"),
        "gmail_message_id": value.get("gmail_message_id"),
        "send_attempt_count": stored_send_attempt_count,
        "send_attempt_count_valid": send_attempt_count_valid,
        "subject": value.get("subject"),
        "report_date": value.get("report_date"),
        "body_verified": value.get("body_verified"),
        "attachment_verified": value.get("attachment_verified"),
        "failure_code": value.get("failure_code"),
        "failure_detail": value.get("failure_detail"),
        "attestation_schema_version": value.get("attestation_schema_version"),
        "attestation": value.get("attestation"),
        "receipt": str(path),
        "next_action": next_action,
    }


def attest_gmail_raw_stream(
    root: Path, manifest_path: Path, stage: str, stream: BinaryIO
) -> dict[str, Any]:
    runtime.configure_public_runtime(root)
    try:
        manifest, _ = _gmail_raw_manifest(root, manifest_path)
    except GmailRawAttestationError as failure:
        return _attestation_result(
            {},
            {},
            stage,
            _empty_raw_attestation(stage),
            failure=failure,
            body_verified=False,
            attachment_verified=False,
        )
    expected_payload_bytes = manifest["html_bytes"] + manifest["pdf_bytes"]
    max_raw_bytes = min(
        GMAIL_RAW_ABSOLUTE_MAX_BYTES,
        max(512 * 1024, expected_payload_bytes * 2 + 512 * 1024),
    )
    try:
        framed = read_gmail_raw_frame(stream, max_raw_bytes=max_raw_bytes)
    except GmailRawFrameError as failure:
        return _attestation_result(
            manifest,
            {},
            stage,
            _empty_raw_attestation(stage),
            failure=failure,
            body_verified=False,
            attachment_verified=False,
        )
    envelope = dict(framed["metadata"])
    envelope["raw"] = framed["raw"]
    return attest_gmail_raw(root, manifest_path, stage, envelope)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-config", type=Path, help="explicit public user config for rootless commands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    for name in ("prepare", "attest"):
        child = subparsers.add_parser(name)
        child.add_argument("--root", required=True, type=Path)
        child.add_argument("--input", required=True, type=Path)
        if name == "prepare":
            child.add_argument("--output-dir", type=Path)
    chunk = subparsers.add_parser("mime-chunk")
    chunk.add_argument("--path", required=True, type=Path)
    chunk.add_argument("--expected-size", required=True, type=int)
    chunk.add_argument("--expected-sha256", required=True)
    chunk.add_argument("--offset", required=True, type=int)
    chunk.add_argument("--max-bytes", type=int, default=MIME_CHUNK_BYTES)
    receipt = subparsers.add_parser("record-receipt")
    receipt.add_argument("--root", required=True, type=Path)
    receipt.add_argument("--manifest", required=True, type=Path)
    receipt.add_argument("--input", required=True, type=Path)
    receipt_status = subparsers.add_parser("receipt-status")
    receipt_status.add_argument("--root", required=True, type=Path)
    receipt_status.add_argument("--manifest", type=Path)
    raw_attest = subparsers.add_parser("attest-gmail-raw")
    raw_attest.add_argument("--root", required=True, type=Path)
    raw_attest.add_argument("--manifest", required=True, type=Path)
    raw_attest.add_argument("--stage", required=True, choices=("draft", "sent"))
    receipt_stdin = subparsers.add_parser("record-receipt-stdin")
    receipt_stdin.add_argument("--root", required=True, type=Path)
    receipt_stdin.add_argument("--manifest", required=True, type=Path)
    receipt_stdin.add_argument("--send-lease-token")
    proof_stdin = subparsers.add_parser("prepare-send-proof-stdin")
    proof_stdin.add_argument("--root", required=True, type=Path)
    proof_stdin.add_argument("--manifest", required=True, type=Path)
    reauthorization_stdin = subparsers.add_parser(
        "issue-send-reauthorization-stdin"
    )
    reauthorization_stdin.add_argument("--root", required=True, type=Path)
    reauthorization_stdin.add_argument("--manifest", required=True, type=Path)
    legacy_reauthorization_stdin = subparsers.add_parser(
        "issue-legacy-send-reauthorization-stdin"
    )
    legacy_reauthorization_stdin.add_argument("--root", required=True, type=Path)
    legacy_reauthorization_stdin.add_argument(
        "--manifest", required=True, type=Path
    )
    legacy_reauthorization_rotate = subparsers.add_parser(
        "rotate-legacy-send-reauthorization-token"
    )
    legacy_reauthorization_rotate.add_argument("--root", required=True, type=Path)
    legacy_reauthorization_rotate.add_argument(
        "--manifest", required=True, type=Path
    )
    legacy_reauthorization_rotate.add_argument(
        "--reauthorization-id", required=True
    )
    reauthorized_proof_stdin = subparsers.add_parser(
        "prepare-reauthorized-send-proof-stdin"
    )
    reauthorized_proof_stdin.add_argument("--root", required=True, type=Path)
    reauthorized_proof_stdin.add_argument("--manifest", required=True, type=Path)
    reauthorized_proof_stdin.add_argument(
        "--reauthorization-token", required=True
    )
    lease_acquire = subparsers.add_parser("gmail-send-lease-acquire")
    lease_acquire.add_argument("--root", required=True, type=Path)
    lease_acquire.add_argument("--manifest", required=True, type=Path)
    lease_acquire.add_argument("--proof-token", required=True)
    lease_acquire.add_argument("--owner", required=True)
    lease_acquire.add_argument("--wait-seconds", type=float, default=10.0)
    lease_release = subparsers.add_parser("gmail-send-lease-release")
    lease_release.add_argument("--root", required=True, type=Path)
    lease_release.add_argument("--manifest", required=True, type=Path)
    lease_release.add_argument("--lease-token", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime.configure_public_cli(args)
    if args.command == "preflight":
        result = delivery_preflight()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ready"] else 3
    if args.command == "mime-chunk":
        result = read_attested_chunk(args.path, expected_size=args.expected_size, expected_sha256=args.expected_sha256, offset=args.offset, max_bytes=args.max_bytes)
    elif args.command == "attest-gmail-raw":
        prepare_framed_stdin()
        result = attest_gmail_raw_stream(
            args.root, args.manifest, args.stage, sys.stdin.buffer
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 4
    elif args.command == "record-receipt-stdin":
        prepare_framed_stdin()
        result = _record_delivery_receipt_value(
            args.root,
            args.manifest,
            read_receipt_stdin(sys.stdin.buffer),
            send_lease_token=args.send_lease_token,
        )
    elif args.command == "prepare-send-proof-stdin":
        prepare_framed_stdin()
        result = prepare_send_proof(
            args.root, args.manifest, read_receipt_stdin(sys.stdin.buffer)
        )
    elif args.command == "issue-send-reauthorization-stdin":
        prepare_framed_stdin()
        result = issue_send_reauthorization(
            args.root, args.manifest, read_receipt_stdin(sys.stdin.buffer)
        )
    elif args.command == "issue-legacy-send-reauthorization-stdin":
        prepare_framed_stdin()
        result = issue_legacy_send_reauthorization(
            args.root, args.manifest, read_receipt_stdin(sys.stdin.buffer)
        )
    elif args.command == "rotate-legacy-send-reauthorization-token":
        result = rotate_legacy_send_reauthorization_token(
            args.root,
            args.manifest,
            args.reauthorization_id,
        )
    elif args.command == "prepare-reauthorized-send-proof-stdin":
        prepare_framed_stdin()
        result = prepare_reauthorized_send_proof(
            args.root,
            args.manifest,
            args.reauthorization_token,
            read_receipt_stdin(sys.stdin.buffer),
        )
    elif args.command == "gmail-send-lease-acquire":
        result = acquire_gmail_send_lease(
            args.root,
            args.manifest,
            args.proof_token,
            args.owner,
            wait_seconds=args.wait_seconds,
        )
    elif args.command == "gmail-send-lease-release":
        result = release_gmail_send_lease(
            args.root, args.manifest, args.lease_token
        )
    elif args.command == "record-receipt":
        result = record_delivery_receipt(args.root, args.manifest, args.input)
    elif args.command == "receipt-status":
        result = delivery_receipt_status(args.root, args.manifest)
    else:
        digest = runtime.read_json(args.input.resolve())
        result = prepare_delivery(args.root, digest, output_dir=args.output_dir) if args.command == "prepare" else attest_existing_delivery(args.root, digest)
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DeliveryValidationError, runtime.DigestValidationError) as exc:
        raise SystemExit(f"error: {exc}") from exc
