# SPDX-License-Identifier: Apache-2.0
# Adapted from arxiv-mcp-server 0.5.0, tools/download.py::_fetch_pdf_content.
# Copyright 2024 Joseph Blazick
# Source: https://github.com/blazickjp/arxiv-mcp-server/blob/d22255b0c24578ed214d2918d2ff2786d92a778e/src/arxiv_mcp_server/tools/download.py
# Changes in VibeResearch: arxiv 4.x compatibility using a streamed temporary
# PDF download, conditional fallback installation, and guaranteed cleanup.
# The public export adds this attribution; the PDF behavior is unchanged.
# See LICENSES/Apache-2.0.txt at the source or plugin distribution root.

"""Compatibility patch for arxiv-mcp-server's PDF fallback.

arxiv-mcp-server 0.5.0 calls ``arxiv.Result.download_pdf()``, but arxiv 4.x
removed that method. The priority wrapper installs this narrow patch only
when the method is absent. HTML-first behavior and the upstream tool schema
remain unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _stream_pdf_to_path(download_module: Any, paper: Any, pdf_path: Path) -> None:
    pdf_url = getattr(paper, "pdf_url", None)
    if not pdf_url:
        raise RuntimeError("arXiv result does not provide a PDF URL")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = pdf_path.with_suffix(f"{pdf_path.suffix}.part")
    try:
        with download_module.httpx.stream(
            "GET",
            pdf_url,
            headers={"User-Agent": "arxiv-mcp-server/0.5.0"},
            timeout=60,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            with partial_path.open("wb") as stream:
                for chunk in response.iter_bytes():
                    if chunk:
                        stream.write(chunk)
        if not partial_path.exists() or partial_path.stat().st_size == 0:
            raise RuntimeError("arXiv PDF response was empty")
        partial_path.replace(pdf_path)
    finally:
        try:
            partial_path.unlink()
        except FileNotFoundError:
            pass


def install_pdf_download_compat(download_module: Any) -> bool:
    """Replace the incompatible PDF fallback when arxiv.Result lacks it."""

    result_type = getattr(download_module.arxiv, "Result", None)
    if callable(getattr(result_type, "download_pdf", None)):
        return False

    def _fetch_pdf_content(paper_id: str) -> tuple[str, Any]:
        if not download_module._pdf_available:
            raise ImportError(
                "PDF conversion requires the pdf extra: "
                "pip install arxiv-mcp-server[pdf]"
            )

        client = download_module.get_arxiv_client()
        try:
            paper = next(
                client.results(download_module.arxiv.Search(id_list=[paper_id]))
            )
        except StopIteration:
            raise download_module.PaperNotFoundError(
                f"Paper {paper_id} not found on arXiv"
            )

        pdf_path = download_module.get_paper_path(paper_id, ".pdf")
        try:
            _stream_pdf_to_path(download_module, paper, pdf_path)
            download_module.logger.info(
                "Converting PDF to markdown for %s using compatibility downloader",
                paper_id,
            )
            markdown = download_module.pymupdf4llm.to_markdown(
                pdf_path,
                show_progress=False,
            )
            return markdown, paper
        finally:
            download_module.gc.collect()
            try:
                pdf_path.unlink()
            except FileNotFoundError:
                pass

    download_module._fetch_pdf_content = _fetch_pdf_content
    return True
