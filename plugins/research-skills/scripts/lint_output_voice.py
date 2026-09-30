#!/usr/bin/env python3
"""Count machine-flavored phrasing in a model output (Markdown or plain text).

Usage: python scripts/lint_output_voice.py OUTPUT.md [--max-per-1k 3]

A regression signal for comparing Skill versions or models on the same fixtures; it
is not a quality score and not an authorship detector. Patterns mirror the tables in
skills/_shared/output-voice.md. Code blocks and inline code are ignored. "Info"
patterns are reported but excluded from the density, because they are common in
legitimate academic text.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

COUNTED = {
    "zh:空洞拔高": r"至关重要|举足轻重|里程碑|奠定了?(坚实的?)?基础|开辟了?新|划时代|深远影响",
    "zh:套话过渡": r"值得注意的是|需要指出的是|不难发现|由此可见|综上所述|总而言之|总的来说|简而言之",
    "zh:对举腔": r"不仅[^。；\n]{1,30}更|这不是[^。\n]{1,30}而是|与其说[^。\n]{1,30}不如说",
    "zh:流行动词": r"赋能|助力|深耕|打通|抓手|闭环|全方位|多维度|全链路",
    "zh:层层保留": r"(可能|或许|也许)[^。\n]{0,8}(一定程度上|在某种程度上)",
    "zh:开场复述": r"^(好的|当然)[，,].{0,20}(我将|下面|以下)",
    "en:inflated": r"\b(pivotal|crucial role|testament to|evolving landscape|marks? a (shift|turning point))\b",
    "en:stock": r"\b(delve|delves|delving|leverag(e|es|ed|ing)|utili[sz](e|es|ed|ing)|it'?s worth noting)\b",
    "en:contrast": r"(isn'?t|is not) (just |only )?about [^.]{1,40}\. It'?s about",
    "en:signpost": r"(let'?s break (this|it) down|here'?s what you need to know|in short:|key takeaway:|bottom line:)",
    "en:ing_tail": r", (highlighting|underscoring|showcasing|emphasizing) ",
    "format:internal_id": r"\b(CLM|AUD|HYP|EV|TST|PAP|AXIS|OBS|FIND|MAP|DEC)-\d{2,}\b",
    "format:english_status": r"not provided / unclear|insufficient-material|supported interpretation|unconfirmed inference",
}
INFO = {
    "info:bold": r"\*\*[^*\n]+\*\*",
    "info:翻译腔": r"进行了?[^。，\n]{0,6}(分析|优化|研究|处理)|在[^。，\n]{1,15}的背景下",
    "info:en_intensifier": r"\b(really|truly|importantly)\b",
}


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", " ", text)


def scan(text: str) -> tuple[dict[str, int], float]:
    """Return per-pattern hit counts and counted hits per 1,000 characters."""
    body = strip_code(text)
    hits: dict[str, int] = {}
    for name, pattern in {**COUNTED, **INFO}.items():
        found = len(re.findall(pattern, body, flags=re.I | re.M))
        if found:
            hits[name] = found
    counted = sum(n for name, n in hits.items() if not name.startswith("info:"))
    return hits, counted / max(len(body), 1) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-per-1k", type=float, default=3.0)
    args = parser.parse_args()
    hits, density = scan(args.path.read_text(encoding="utf-8"))
    for name, count in sorted(hits.items()):
        print(f"{name}\t{count}")
    print(f"per_1k_chars\t{density:.2f}")
    return 1 if density > args.max_per_1k else 0


if __name__ == "__main__":
    sys.exit(main())
