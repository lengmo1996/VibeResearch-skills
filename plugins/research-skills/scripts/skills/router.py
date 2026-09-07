#!/usr/bin/env python3
"""Deterministic, registry-aware offline router used by governance evaluation.

This is an evaluator, not a runtime agent.  MCP calls are represented by names
only; no network service is contacted during ordinary tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from common import flatten_strings, tokens


@dataclass
class RouteDecision:
    primary_skill: str
    mode: str
    supporting_skills: list[str]
    rag_policy: str
    mcp_calls: list[str] = field(default_factory=list)
    matched_by: str = "policy"
    failure_behavior: str | None = None
    warnings: list[str] = field(default_factory=list)
    safety_flags: list[str] = field(default_factory=list)
    side_effect_class: str = "read_only"
    required_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _contains(prompt: str, *phrases: str) -> bool:
    return any(phrase.casefold() in prompt for phrase in phrases)


def _literal_mode(prompt: str, entry: dict[str, Any] | None) -> str | None:
    """Recognize an explicit mode, without interpreting it as action approval."""
    if not entry:
        return None
    modes = [str(mode) for mode in entry.get("modes", [])]
    if not modes:
        return None
    choices = "|".join(re.escape(mode) for mode in sorted(modes, key=len, reverse=True))
    skill = re.escape(str(entry["id"]))
    # Both `$skill code-mapping` and `$skill in code-mapping mode` are public forms.
    prefixes = (
        rf"(?:\${skill}|(?:use|使用|调用)\s+{skill})(?![a-z0-9-])\s*(?:[:：]\s*|的\s*)?(?:in\s+)?(?:mode\s*[:=：]?\s*)?",
        r"(?:\bmode\s*[:=：]\s*|模式\s*[:=：]\s*)",
    )
    for prefix in prefixes:
        match = re.search(prefix + rf"[`\"']?({choices})(?![a-z0-9_-])", prompt)
        if match:
            # `compare` is a documented compatibility alias, still registered.
            return "comparison" if entry["id"] == "literature-synthesis" and match[1] == "compare" else match[1]
    match = re.search(rf"(?<![a-z0-9_-])[`\"']?({choices})[`\"']?\s*(?:\bmode\b|模式)", prompt)
    if match:
        return "comparison" if entry["id"] == "literature-synthesis" and match[1] == "compare" else match[1]
    return None


def _declared_rag(mode: str, entry: dict[str, Any] | None) -> str:
    if not entry:
        return "optional"
    contracts = entry.get("mode_contracts", {})
    value = entry.get("rag_policy", "optional")
    if isinstance(contracts, dict):
        for key in ("*", mode):
            contract = contracts.get(key, {})
            if isinstance(contract, dict) and "rag_policy" in contract:
                value = contract["rag_policy"]
    return value if value in ("never", "optional", "recommended", "required") else "optional"


def _structure_audit_intent(prompt: str) -> bool:
    explicit = _contains(
        prompt,
        "reverse outline",
        "reverse-outline",
        "反向大纲",
        "反向梳理",
        "反向审查",
    )
    paragraph_map = _contains(
        prompt,
        "paragraph role",
        "paragraph function",
        "段落角色",
        "段落功能",
        "claim-evidence 依赖",
        "argument dependency",
    )
    diagnostic = _contains(
        prompt,
        "audit",
        "diagnose",
        "check",
        "审计",
        "诊断",
        "检查",
        "找出",
    )
    return explicit or (paragraph_map and diagnostic)


def _citation_metadata_intent(prompt: str) -> bool:
    exact = _contains(
        prompt,
        "validate citation metadata",
        "verify doi metadata",
        "check pmid",
        "check arxiv id",
        "duplicate citations",
        "citation metadata conflict",
        "引用元数据核验",
        "doi 核验",
        "重复引用",
    )
    identifier_check = _contains(prompt, "doi", "pmid", "pmcid", "arxiv") and _contains(
        prompt, "核验", "检查", "verify", "validate", "normalize", "规范"
    )
    return exact or identifier_check


def _entry_map(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(entry.get("id", "")): entry for entry in entries if entry.get("id")}


def _negative_match(prompt: str, entry: dict[str, Any]) -> bool:
    for trigger in flatten_strings(entry.get("negative_triggers", [])):
        normalized = trigger.casefold().strip()
        if normalized and normalized in prompt:
            return True
    return False


def _explicit_skill(prompt: str, entries: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Resolve a strong named invocation for a canonical active Skill."""

    ordered = sorted(entries, key=lambda item: len(str(item.get("id", ""))), reverse=True)
    for entry in ordered:
        skill_id = str(entry.get("id", ""))
        if not skill_id:
            continue
        patterns = (f"${skill_id}", f"使用 {skill_id}", f"use {skill_id}", f"调用 {skill_id}")
        if not any(pattern in prompt for pattern in patterns):
            continue
        if entry.get("activation") == "supporting_only":
            # Domain/knowledge Skills can be requested explicitly as context, but
            # they are never permitted to own the primary deliverable.
            continue
        if skill_id == "paper-reproduction":
            if _literal_mode(prompt, entry):
                return skill_id, f"explicit {skill_id} mode"
            if _contains(prompt, "environment-audit", "environment audit", "环境审计"):
                return "code-repo-adaptation", "legacy paper-reproduction environment forwarding"
            if _contains(prompt, "data-protocol", "data protocol", "数据协议"):
                return "research-dataset-metric-protocols", "legacy paper-reproduction data forwarding"
            if _contains(prompt, "smoke", "gap-analysis", "gap analysis", "verification", "verify", "验证"):
                return "code-debugging", "legacy paper-reproduction debugging forwarding"
            if _contains(prompt, "runbook"):
                if _contains(prompt, "环境", "依赖", "适配", "迁移", "framework"):
                    return "code-repo-adaptation", "legacy paper-reproduction runbook migration forwarding"
                return "code-experiment-config-management", "legacy paper-reproduction runbook lifecycle forwarding"
        return skill_id, f"explicit {skill_id}"
    return None, None


def _generic_trigger_route(prompt: str, entries: list[dict[str, Any]]) -> str | None:
    """Choose the best positive trigger only when policy rules have no match."""

    prompt_tokens = tokens(prompt)
    candidates: list[tuple[float, str]] = []
    for entry in entries:
        if (
            entry.get("status") == "deprecated"
            or entry.get("activation") == "supporting_only"
            or _negative_match(prompt, entry)
        ):
            continue
        trigger_values = flatten_strings(entry.get("positive_triggers", []))
        trigger_tokens = tokens(trigger_values)
        if not trigger_tokens:
            continue
        exact = sum(1 for value in trigger_values if value.casefold().strip() in prompt)
        coverage = len(prompt_tokens & trigger_tokens) / max(1, len(trigger_tokens))
        score = exact * 2.0 + coverage
        if score > 0.30:
            candidates.append((score, str(entry.get("id", ""))))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _policy_primary(prompt: str, entries: list[dict[str, Any]]) -> tuple[str, str]:
    explicit, reason = _explicit_skill(prompt, entries)
    if explicit:
        return explicit, reason or "explicit invocation"
    if re.search(r"skills?", prompt) and _contains(prompt, "重新评估", "各类", "实现", "优化空间"):
        return "project-skill-usage-evolution", "Skill implementation architecture audit"
    if "zotero" in prompt and _contains(prompt, "pdf", "附件", "对齐", "导出清单"):
        return "tool-zotero-pdf-ingestion", "Zotero attachment reconciliation"
    if _contains(prompt, "找 doi", "citation key") and _contains(prompt, "找", "核验", "查找"):
        return "tool-citation-metadata-validation", "bibliographic identifier resolution"
    if _citation_metadata_intent(prompt):
        return "tool-citation-metadata-validation", "citation metadata validation"
    if _contains(
        prompt,
        "scientific database query",
        "query a database api",
        "api pagination audit",
        "exhaustive database retrieval",
        "resume database query",
        "科学数据库查询",
        "数据库 api 分页",
        "查询完整性",
    ):
        return "tool-scientific-database-query", "scientific database query"
    if _contains(
        prompt,
        "resource preflight",
        "check available resources",
        "gpu memory preflight",
        "workload feasibility",
        "cpu memory disk requirements",
        "资源预检",
        "可用资源检查",
        "显存是否够",
        "运行可行性",
    ):
        return "tool-resource-preflight", "resource preflight"

    # Governance is intentionally separated from active-Skill mutation.
    if _contains(prompt, "unapproved mutation", "未批准变更", "未授权变更", "approval gate", "审批门"):
        return "project-skill-usage-evolution", "governance approval audit"
    if _contains(prompt, "rollback", "回滚计划", "恢复计划"):
        return "project-skill-usage-evolution", "governance rollback"
    if _contains(prompt, "shadow evaluation", "shadow eval", "影子评测", "候选版本对比"):
        return "project-skill-usage-evolution", "governance shadow evaluation"
    if _contains(prompt, "evolution proposal", "演化提案", "改进 proposal", "生成 proposal", "改进提案"):
        return "project-skill-usage-evolution", "governance proposal"
    if _contains(prompt, "skill 使用日志", "技能使用日志", "路由事件", "usage event"):
        return "project-skill-usage-evolution", "governance observation"
    if _contains(
        prompt,
        "skill architecture",
        "capability graph",
        "workflow coverage",
        "trigger overlap",
        "skill 架构",
        "能力图谱",
    ):
        return "project-skill-usage-evolution", "Skill architecture audit"
    if _contains(prompt, "修改全文", "重写全文"):
        return "writing-academic", "requested manuscript rewrite with optional capture"
    if "术语一致性" in prompt and _contains(prompt, "检查", "审查", "核对"):
        return "writing-manuscript-audit", "terminology audit using supplied or historical context"
    if _contains(
        prompt,
        "保存论文上下文到项目记忆",
        "持久化 paper context",
        "persist paper context",
        "save this to project memory",
        "persist this decision",
        "更新长期记忆",
        "保存已批准风格档案引用",
        "save approved style profile reference to project memory",
    ):
        return "project-memory-update", "explicit project-memory persistence request"
    if _contains(
        prompt,
        "风格档案引用",
        "style profile reference",
        "style-profile reference",
    ) and _contains(
        prompt,
        "项目记忆",
        "project memory",
        "保存",
        "persist",
    ):
        return "project-memory-update", "explicit style-profile reference persistence"

    if _contains(
        prompt,
        "积累表达",
        "积累术语",
        "写作表达积累",
        "待审核区",
        "pending review",
        "capture writing",
        "待审核的写作风格档案",
        "stage my author style profile",
        "以前积累过哪些术语",
        "writing candidate",
    ) or (_contains(prompt, "积累", "提取") and _contains(prompt, "表达", "术语", "reviewer response 策略")):
        return "writing-knowledge-capture", "writing knowledge capture"
    if _contains(
        prompt,
        "systematic review",
        "系统综述",
        "prisma",
        "full-text exclusion",
        "全文排除理由",
        "risk of bias",
        "evidence certainty",
        "meta-analysis",
    ):
        return "literature-systematic-review", "protocol-bound systematic review"
    legacy_reproduction = _contains(
        prompt,
        "paper reproduction",
        "论文复现",
        "复现论文",
        "reproduce this paper",
    )
    if _contains(prompt, "定位复现指标差距", "复现指标差距"):
        return "code-debugging", "reproduction-gap regression diagnosis"
    if _contains(prompt, "跑这个 baseline", "执行已经批准的实验矩阵"):
        return "code-experiment-config-management", "authorized experiment execution lifecycle"
    if legacy_reproduction and _contains(prompt, "制定", "设计", "规划") and _contains(prompt, "protocol", "验收指标", "实验协议"):
        return "research-experiment-design", "reproduction experiment protocol design"
    if legacy_reproduction and _contains(prompt, "environment-audit", "environment audit", "环境审计"):
        return "code-repo-adaptation", "legacy paper-reproduction environment forwarding"
    if legacy_reproduction and _contains(prompt, "data-protocol", "data protocol", "数据协议"):
        return "research-dataset-metric-protocols", "legacy paper-reproduction data forwarding"
    if legacy_reproduction and _contains(
        prompt,
        "smoke",
        "gap-analysis",
        "gap analysis",
        "verification",
        "verify",
        "验证",
    ):
        return "code-debugging", "legacy paper-reproduction debugging forwarding"
    if legacy_reproduction and _contains(prompt, "runbook"):
        if _contains(prompt, "环境", "依赖", "适配", "迁移", "framework"):
            return "code-repo-adaptation", "legacy paper-reproduction runbook migration forwarding"
        return "code-experiment-config-management", "legacy paper-reproduction runbook lifecycle forwarding"
    if _contains(
        prompt,
        "创新点",
        "核心创新",
        "official code",
        "官方代码",
        "code mapping",
        "代码映射",
        "核心实现",
        "实现论文模块",
        "实现这篇论文",
        "paper reproduction",
        "论文复现",
        "复现论文",
        "reproduce this paper",
    ):
        return "paper-reproduction", "paper reproduction"

    # Explicit compatibility migration outranks a traceback that merely exposes
    # the incompatibility. Final verification still returns to code-debugging.
    compatibility_target = _contains(
        prompt,
        "适配",
        "迁移",
        "兼容",
        "升级",
        "port",
        "migration",
        "compatibility",
    )
    compatibility_surface = _contains(
        prompt,
        "python",
        "pytorch",
        "cuda",
        "依赖",
        "dependency",
        "lightning",
        "diffusers",
        "transformers",
        "framework",
        "api",
        "dataset layout",
        "数据布局",
        "dataloader",
        "training pipeline",
        "训练管线",
        "inference",
        "checkpoint",
    )
    if compatibility_target and compatibility_surface:
        return "code-repo-adaptation", "explicit compatibility migration"

    if _contains(
        prompt,
        "minimal reproduction",
        "最小复现",
        "traceback",
        "报错",
        "错误栈",
        "nan",
        "oom",
        "failed test",
        "测试失败",
        "运行失败",
        "bug",
        "deadlock",
        "ddp 卡死",
        "verify this patch",
        "验证这个 patch",
        "patch verification",
        "回归测试",
    ):
        return "code-debugging", "concrete failure or verification"
    if _contains(
        prompt,
        "hydra",
        "实验配置",
        "run naming",
        "checkpoint 目录",
        "sweep 配置",
        "resume",
        "实验归档",
        "执行已规划实验",
        "运行实验矩阵",
        "监控实验运行",
        "收集运行制品",
        "run frozen experiment plan",
        "execute experiment matrix",
        "monitor experiment run",
        "collect run artifacts",
    ):
        return "code-experiment-config-management", "experiment configuration"
    if _contains(prompt, "github repository", "github repo", "开源仓库", "外部仓库", "repository") and _contains(
        prompt, "分析", "理解", "适配", "迁移", "当前环境", "inspect"
    ):
        return "code-repo-adaptation", "repository adaptation"
    if _contains(
        prompt,
        "实验结果",
        "结果表",
        "训练曲线",
        "显著性",
        "failure case",
        "统计假设",
        "多重比较",
        "best-seed",
        "seed coverage",
        "可复现性",
        "reproducibility",
    ) and _contains(
        prompt, "分析", "解释", "判断", "检查", "核对", "audit", "interpret"
    ):
        return "research-result-analysis", "result interpretation"
    if _contains(
        prompt,
        "sample size calculation",
        "power analysis",
        "minimum detectable effect",
        "样本量估计",
        "样本量计算",
        "检验效能",
        "统计功效",
        "最小可检测效应",
    ) or (
        _contains(prompt, "mde")
        and _contains(prompt, "sample", "power", "effect", "样本", "效应")
    ) or (
        _contains(prompt, "power", "检验效能", "统计功效")
        and _contains(prompt, "sample", "样本量")
    ):
        return "research-statistical-power", "statistical power planning"
    if _contains(
        prompt,
        "uncertainty budget",
        "measurement uncertainty",
        "dimensional consistency",
        "unit conversion audit",
        "type a uncertainty",
        "type b uncertainty",
        "coverage factor",
        "测量不确定度",
        "不确定度预算",
        "量纲检查",
        "单位换算审计",
    ):
        return "research-uncertainty-units", "uncertainty and units"
    if _contains(
        prompt,
        "data quality audit",
        "dataset quality",
        "missingness audit",
        "duplicate records",
        "schema violations",
        "data drift audit",
        "数据质量审计",
        "缺失值审计",
        "重复记录",
        "数据漂移审计",
    ):
        return "research-data-quality-audit", "data quality audit"
    if _contains(prompt, "设计实验", "实验方案", "消融方案", "baseline 方案", "evaluation plan"):
        return "research-experiment-design", "experiment design"
    if _contains(prompt, "定义", "设计", "规划") and _contains(prompt, "train/validation/test", "数据集划分", "dataset split", "leakage protocol"):
        return "research-dataset-metric-protocols", "dataset and evaluation protocol"

    if _contains(prompt, "投稿前", "camera-ready", "提交检查", "anonymity", "页数限制", "submission preflight"):
        return "publish-preflight", "submission preflight"
    if _contains(prompt, "投哪个", "目标期刊", "目标会议", "venue", "tip 还是", "tpami 还是"):
        return "publish-venue-targeting", "venue targeting"
    if _contains(prompt, "审稿意见", "reviewer comments", "openreview 评论", "cmt 意见") and _contains(
        prompt, "分组", "优先级", "triage", "严重度", "策略"
    ):
        return "writing-review-triage", "review triage"
    if _contains(prompt, "转成 ppt", "做成 slides", "演示文稿", "speaker notes"):
        return "paper-to-ppt", "paper presentation"
    if _contains(
        prompt,
        "生成 latex 表",
        "画实验图",
        "publication-ready table",
        "生成图表",
        "draw.io",
        "drawio",
        "可编辑流程图",
        "可编辑架构图",
        "pgfplots",
        "tikz 图",
    ):
        return "visual-research-artifact-generation", "research visual generation"

    # Explicit negative triggers win over broad audit/synthesis phrases.
    lightweight_rewrite = _contains(prompt, "简单英文改写", "英文改写", "改写这句话", "润色这句话", "grammar rewrite", "改成学术英语")
    if lightweight_rewrite:
        return "writing-academic", "lightweight rewrite (negative trigger suppressed full audit)"
    de_template_rewrite = _contains(
        prompt,
        "去模板化重写",
        "去模板化改写",
        "de-template this",
        "less formulaic rewrite",
    )
    author_voice_rewrite = _contains(
        prompt,
        "按我的写作语气改写",
        "参考我提供的本人论文样本",
        "match my own academic voice",
        "use my writing voice",
    )
    revision_patch = _contains(
        prompt,
        "修订 patch",
        "revision patch",
        "hash-bound manuscript patch",
        "原文 hash",
    )
    if revision_patch:
        return "writing-academic", "hash-bound manuscript revision patch"
    if de_template_rewrite or author_voice_rewrite:
        return "writing-academic", "bounded academic prose rewrite"
    if _contains(prompt, "重写", "改写", "压缩", "起草", "润色") and not _contains(prompt, "不要重写", "不直接重写", "只诊断"):
        if _contains(prompt, "摘要", "abstract", "introduction", "conclusion", "method", "段落", "句子", "逐点回复", "reviewer response", "reviewer comments"):
            return "writing-academic", "scoped prose operation"

    if _structure_audit_intent(prompt) or _contains(prompt, "反向审查", "章节结构并列出逻辑缺陷"):
        return "writing-manuscript-audit", "manuscript structure audit"

    citation_audit = _contains(prompt, "引用 claim", "claim 核验", "claim 的证据", "citation verification", "引用证据", "引用论断", "找支持这个 claim")
    audit = _contains(
        prompt,
        "全文审查",
        "术语一致性",
        "数字核对",
        "数字一致性",
        "表格和正文",
        "表格与正文",
        "公式符号",
        "公式编号",
        "数字与正文",
        "latex 语法",
        "检查语法",
        "baseline 公平性",
        "审查这篇稿件",
        "latex 检查",
        "审查消融",
        "消融审查",
        "manuscript audit",
        "模拟 reviewer",
        "独立评审",
        "评审视角",
        "review panel",
        "reviewer panel",
        "少数意见",
        "复验审计发现",
        "关闭审计问题",
        "verify audit findings",
        "close audit findings",
        "模板化写作痕迹",
        "ai 写作痕迹",
        "templated prose signatures",
        "prompt 残留",
        "prompt residue",
        "生成过程痕迹",
        "未替换占位符",
        "unresolved placeholder",
    )
    if citation_audit or audit:
        return "writing-manuscript-audit", "manuscript audit"

    if _contains(prompt, "值得读", "快速筛选", "论文初筛", "阅读优先级", "go/no-go", "挑三篇", "论文排序") or ("论文" in prompt and "排序" in prompt):
        return "paper-triage", "bounded paper reading queue"

    deny_multi_paper = _contains(prompt, "不做多论文综述", "不是多论文", "单篇论文", "one paper only")
    multi_paper = not deny_multi_paper and _contains(
        prompt,
        "多篇",
        "三篇",
        "多论文",
        "比较论文",
        "比较三种方法",
        "文献库中的",
        "knowledgehub 中的",
        "taxonomy",
        "研究空白",
        "论文集合",
        "比较检索到的论文",
        "比较当前论文",
        "知识库中的",
    )
    related_work = "related work" in prompt or "相关工作" in prompt
    supplied_evidence = _contains(prompt, "已提供的 evidence map", "根据 evidence map", "提供的证据图", "仅根据我提供", "只依据附件")
    if multi_paper or (related_work and not supplied_evidence):
        return "literature-synthesis", "multi-paper synthesis"

    if _contains(prompt, "abstract", "摘要", "introduction", "结论", "reviewer response", "回复审稿人") and _contains(
        prompt, "写", "起草", "重写", "改写", "润色", "压缩", "扩展", "rewrite", "draft"
    ):
        return "writing-academic", "academic prose"
    if related_work and supplied_evidence:
        return "writing-academic", "writing from supplied evidence"
    whole_paper_plan = _contains(prompt, "整篇论文", "全文论文", "whole paper", "full manuscript") and _contains(
        prompt,
        "规划",
        "大纲",
        "故事线",
        "章节依赖",
        "写作次序",
        "outline",
        "plan",
        "section dependency",
    )
    if whole_paper_plan:
        return "writing-academic", "whole-paper narrative planning"
    if _contains(prompt, "值得读", "快速筛选", "论文初筛", "阅读优先级", "go/no-go"):
        return "paper-triage", "paper triage"
    if _contains(prompt, "技术文档", "knowledgehub 文档", "快速了解", "是什么", "概念入门") and not _contains(
        prompt, "论文中", "这篇论文"
    ):
        return "research-concept-primer", "technical concept primer"
    if _contains(
        prompt,
        "论文",
        "paper",
        "pdf",
        "分析实验",
        "公式",
        "方法分析",
        "消融",
        "method",
        "equation",
        "figure_image",
        "table_image",
        "architecture figure",
        "architecture diagram",
    ):
        return "paper-deep-read", "single-paper analysis"

    generic = _generic_trigger_route(prompt, entries)
    return (generic, "registry positive trigger") if generic else ("research-concept-primer", "safe informational fallback")


def _mode(primary: str, prompt: str) -> str:
    if primary == "paper-to-ppt":
        if _contains(prompt, "speaker", "讲稿", "演讲"):
            return "speaker-ready"
        if _contains(prompt, "template", "模板"):
            return "template-adaptation"
        if _contains(prompt, "audit", "审计"):
            return "visual-audit"
        if _contains(prompt, "visual system", "视觉系统"):
            return "visual-system"
        if _contains(prompt, "outline", "大纲"):
            return "outline"
        return "deck"
    if primary == "paper-triage":
        if _contains(prompt, "project-specific", "项目需求", "项目相关"):
            return "project-specific"
        if _contains(prompt, "watch", "监控提供"):
            return "watch"
        if _contains(prompt, "多篇", "列表", "排序", "rank", "batch"):
            return "batch"
        return "single"
    if primary == "paper-deep-read":
        if _contains(prompt, "table", "表格", "结果表"):
            return "table"
        if _contains(prompt, "figure", "架构图", "结构图", "流程图", "pipeline 图", "图片"):
            return "figure"
        if _contains(prompt, "摘要", "概览", "overview", "快速总结"):
            return "overview"
        if _contains(prompt, "公式", "推导", "equation"):
            return "equations"
        if _contains(prompt, "方法", "method", "architecture", "网络结构"):
            return "method"
        if _contains(prompt, "消融", "实验", "ablation", "experiment"):
            return "experiments"
        if _contains(prompt, "局限", "limitations"):
            return "limitations"
        return "full"
    if primary == "literature-synthesis":
        if _contains(prompt, "taxonomy", "分类体系"):
            return "taxonomy"
        if _contains(prompt, "研究空白", "research gap"):
            return "gap"
        if _contains(prompt, "related work", "相关工作"):
            return "related-work"
        if _contains(prompt, "evidence map", "证据图"):
            return "evidence-map"
        return "comparison"
    if primary == "literature-kb-build":
        if _contains(prompt, "inventory", "盘点"):
            return "inventory"
        if _contains(prompt, "metadata", "元数据"):
            return "metadata"
        if _contains(prompt, "extract", "提取"):
            return "extract"
        if _contains(prompt, "chunk", "分块"):
            return "chunk"
        if _contains(prompt, "index", "索引"):
            return "index"
        if _contains(prompt, "verify", "验证", "核验"):
            return "verify"
        return "full"
    if primary == "literature-monitor":
        if _contains(prompt, "daily_arxiv_email", "daily arxiv email", "日报邮件"):
            return "daily_arxiv_email"
        if _contains(prompt, "weekly", "每周", "周报"):
            return "weekly"
        if _contains(prompt, "watchlist", "监视列表"):
            return "watchlist"
        if _contains(prompt, "baseline", "基线"):
            return "baseline"
        if _contains(prompt, "dataset", "数据集"):
            return "dataset"
        return "snapshot"
    if primary == "literature-systematic-review":
        if _contains(prompt, "protocol", "协议", "注册"):
            return "protocol"
        if _contains(prompt, "search", "检索批次", "查询"):
            return "search"
        if _contains(prompt, "screening", "筛选", "排除理由"):
            return "screening"
        if _contains(prompt, "risk of bias", "偏倚风险"):
            return "risk-of-bias"
        if _contains(prompt, "certainty", "证据确定性", "grade"):
            return "certainty"
        if _contains(prompt, "meta-analysis", "荟萃分析", "可合并"):
            return "meta-analysis"
        if _contains(prompt, "synthesis", "综合"):
            return "synthesis"
        return "full"
    if primary == "writing-academic":
        if _contains(
            prompt,
            "修订 patch",
            "revision patch",
            "hash-bound manuscript patch",
            "原文 hash",
        ):
            return "revision-patch"
        if _contains(prompt, "reviewer response", "回复审稿人", "逐点回复"):
            return "reviewer-response"
        if _contains(prompt, "related work", "相关工作"):
            return "related-work"
        if _contains(
            prompt,
            "去模板化重写",
            "去模板化改写",
            "de-template this",
            "less formulaic rewrite",
        ):
            return "de-template"
        if _contains(
            prompt,
            "按我的写作语气改写",
            "参考我提供的本人论文样本",
            "match my own academic voice",
            "use my writing voice",
        ):
            return "author-voice"
        if _contains(prompt, "outline", "大纲", "规划", "章节依赖", "写作次序", "section dependency"):
            return "outline"
        if _contains(prompt, "压缩", "compress"):
            return "compress"
        if _contains(prompt, "扩展", "expand"):
            return "expand"
        if _contains(prompt, "重写", "改写", "润色", "rewrite"):
            return "rewrite"
        return "draft"
    if primary == "writing-manuscript-audit":
        if _contains(prompt, "审查消融", "消融审查", "baseline 公平性"):
            return "reviewer"
        if _contains(
            prompt,
            "独立评审",
            "评审视角",
            "review panel",
            "reviewer panel",
            "少数意见",
        ):
            return "panel-review"
        if _contains(
            prompt,
            "复验审计发现",
            "关闭审计问题",
            "verify audit findings",
            "close audit findings",
            "audit closure",
        ):
            return "closure"
        if _structure_audit_intent(prompt):
            return "structure"
        if _contains(
            prompt,
            "prompt 残留",
            "prompt residue",
            "生成过程痕迹",
            "未替换占位符",
            "unresolved placeholder",
            "todo",
        ):
            return "artifact-leakage"
        if _contains(
            prompt,
            "模板化写作痕迹",
            "ai 写作痕迹",
            "templated prose signatures",
            "prose style",
        ):
            return "prose-style"
        if _contains(prompt, "表格", "数字", "caption"):
            return "table-data"
        if _contains(prompt, "公式", "符号", "维度"):
            return "formula"
        if _contains(prompt, "术语"):
            return "terminology"
        if _contains(prompt, "引用", "citation", "claim 的证据", "claim 核验", "证据"):
            return "citation-evidence"
        if _contains(prompt, "latex", "语言", "语法"):
            return "language"
        if _contains(prompt, "reviewer", "审稿"):
            return "reviewer"
        if _contains(prompt, "全文"):
            return "full"
        return "logic"
    if primary == "research-result-analysis":
        if _contains(
            prompt,
            "统计假设",
            "多重比较",
            "best-seed",
            "selective reporting",
            "statistical audit",
        ):
            return "statistical-audit"
        if _contains(
            prompt,
            "seed coverage",
            "重复运行",
            "可复现性",
            "reproducibility",
        ):
            return "reproducibility-check"
        if _contains(prompt, "失败", "failure", "异常"):
            return "failure-analysis"
        if _contains(prompt, "消融", "ablation"):
            return "ablation-analysis"
        if _contains(prompt, "下一步", "next"):
            return "next-step"
        if _contains(prompt, "claim", "结论", "支持"):
            return "claim-check"
        return "summary"
    if primary == "paper-reproduction":
        if _contains(prompt, "没有官方代码", "无官方代码", "no official code"):
            return "no-official-code"
        if _contains(prompt, "实现", "implementation", "integrate", "编写"):
            return "implementation"
        if _contains(prompt, "代码映射", "code mapping", "method to code", "官方仓库"):
            return "code-mapping"
        if _contains(prompt, "官方代码", "official code", "作者仓库"):
            return "official-code-discovery"
        if _contains(prompt, "创新", "novelty", "contribution", "核心方法"):
            return "innovation-analysis"
        return "full"
    if primary == "project-skill-usage-evolution":
        if _contains(
            prompt,
            "skill architecture",
            "capability graph",
            "workflow coverage",
            "trigger overlap",
            "skill 架构",
        "能力图谱",
        ) or (re.search(r"skills?", prompt) and _contains(prompt, "重新评估", "各类", "优化空间")):
            return "architecture-audit"
        if _contains(prompt, "unapproved", "未批准", "未授权", "approval"):
            return "approval-audit"
        if _contains(prompt, "rollback", "回滚", "恢复计划"):
            return "rollback"
        if _contains(prompt, "shadow", "影子评测", "候选版本对比"):
            return "shadow-eval"
        if _contains(prompt, "proposal", "提案"):
            return "proposal"
        return "observe"
    if primary == "project-memory-update":
        if _contains(
            prompt,
            "风格档案引用",
            "style profile reference",
            "style-profile reference",
            "wsp-",
        ):
            return "style-profile-ref"
        if _contains(prompt, "论文上下文", "paper context", "paper-context"):
            return "paper-context"
        if _contains(prompt, "decision", "决策"):
            return "decision"
        if _contains(prompt, "protocol", "协议"):
            return "protocol"
        if _contains(prompt, "experiment", "实验结论"):
            return "experiment"
        if _contains(prompt, "rebuttal", "回复计划"):
            return "rebuttal"
        return "summary"
    if primary == "writing-knowledge-capture":
        if _contains(prompt, "批准", "approve"):
            return "approve"
        if _contains(prompt, "拒绝", "reject"):
            return "reject"
        if _contains(prompt, "去重", "deduplicate"):
            return "deduplicate"
        if _contains(prompt, "reviewer response", "审稿回复策略"):
            return "reviewer-response"
        if _contains(prompt, "错误规则", "error rule"):
            return "error-rule"
        if _contains(
            prompt,
            "写作风格档案",
            "author style profile",
            "写作偏好",
            "style preference",
        ):
            return "style-preference"
        if _contains(prompt, "术语", "term"):
            return "term"
        if _contains(prompt, "论证", "argument"):
            return "argument-pattern"
        if _contains(prompt, "结构", "structure"):
            return "structure"
        return "phrase"
    if primary == "research-concept-primer":
        return "technical-docs" if _contains(prompt, "技术文档", "knowledgehub 文档") else "overview"
    if primary == "research-idea-generation":
        if _contains(prompt, "gap", "研究空白"):
            return "gap-driven"
        if _contains(prompt, "resource", "资源约束"):
            return "resource-constrained"
        if _contains(prompt, "variation", "方法变体"):
            return "method-variation"
        if _contains(prompt, "application", "应用迁移"):
            return "application-transfer"
        return "problem-driven"
    if primary == "research-statistical-power":
        if _contains(prompt, "simulation", "模拟"):
            return "simulation"
        if _contains(prompt, "sensitivity", "敏感性", "stress-test", "压力测试"):
            return "sensitivity"
        if _contains(prompt, "audit", "审计", "核对"):
            return "audit"
        if _contains(prompt, "formula", "closed-form", "解析"):
            return "closed-form"
        return "full"
    if primary == "research-uncertainty-units":
        if _contains(prompt, "unit", "dimension", "单位", "量纲"):
            return "unit-audit"
        if _contains(prompt, "budget", "预算", "type a", "type b"):
            return "budget"
        if _contains(prompt, "monte carlo", "propagation", "传播"):
            return "propagation"
        if _contains(prompt, "round", "report", "coverage", "有效数字", "报告"):
            return "reporting"
        if _contains(prompt, "plausib", "reasonable", "合理", "数量级"):
            return "plausibility"
        return "full"
    if primary == "research-data-quality-audit":
        if _contains(prompt, "schema", "字段", "类型"):
            return "schema"
        if _contains(prompt, "missing", "缺失"):
            return "completeness"
        if _contains(prompt, "duplicate", "重复", "collision"):
            return "uniqueness"
        if _contains(prompt, "drift", "漂移"):
            return "drift"
        if _contains(prompt, "lineage", "血缘", "来源"):
            return "lineage"
        if _contains(prompt, "fitness", "适用", "可用"):
            return "fitness"
        return "full"
    if primary == "tool-citation-metadata-validation":
        if _contains(prompt, "找 doi", "citation key"):
            return "resolve"
        if _contains(prompt, "normalize", "规范化"):
            return "normalize"
        if _contains(prompt, "resolve", "解析"):
            return "resolve"
        if _contains(prompt, "duplicate", "重复"):
            return "deduplicate"
        if _contains(prompt, "version", "preprint", "版本", "预印本"):
            return "version-link"
        if _contains(prompt, "bibliography", "参考文献表"):
            return "bibliography-audit"
        if _contains(prompt, "cross-check", "核验", "conflict", "冲突"):
            return "cross-check"
        return "full"
    if primary == "tool-scientific-database-query":
        if _contains(prompt, "capability", "schema", "能力", "模式"):
            return "capability"
        if _contains(prompt, "resume", "继续", "恢复"):
            return "resume"
        if _contains(prompt, "exhaustive", "all records", "完整", "全部"):
            return "exhaustive"
        if _contains(prompt, "audit", "审计", "核对"):
            return "audit"
        if _contains(prompt, "cross-check", "交叉"):
            return "cross-check"
        return "targeted"
    if primary == "tool-resource-preflight":
        if _contains(prompt, "inventory", "available", "盘点", "可用"):
            return "inventory"
        if _contains(prompt, "requirement", "需求", "最低"):
            return "requirements"
        if _contains(prompt, "fallback", "降级", "替代"):
            return "fallback"
        if _contains(prompt, "audit", "审计", "核对"):
            return "audit"
        if _contains(prompt, "match", "是否够", "可行"):
            return "match"
        return "full"
    if primary == "research-dataset-metric-protocols":
        if _contains(prompt, "split", "划分"):
            return "split"
        if _contains(prompt, "metric", "指标"):
            return "metric"
        if _contains(prompt, "leakage", "泄漏"):
            return "leakage"
        if _contains(prompt, "comparability", "可比"):
            return "comparability"
        return "full"
    if primary == "research-experiment-design":
        if _contains(prompt, "完整", "方案", "protocol", "验收"):
            return "full"
        for mode, words in (
            ("schedule", ("schedule", "排期", "时间安排")),
            ("ablation", ("ablation", "消融")),
            ("control", ("control", "控制变量")),
            ("baseline", ("baseline", "基线")),
        ):
            if _contains(prompt, *words):
                return mode
        return "full"
    if primary == "tool-zotero-pdf-ingestion":
        if _contains(prompt, "prepare-kb", "准备知识库"):
            return "prepare-kb"
        if _contains(prompt, "export", "导出"):
            return "export"
        if _contains(prompt, "去重", "deduplicate"):
            return "deduplicate"
        if _contains(prompt, "reconcile", "对齐", "附件"):
            return "reconcile"
        return "inventory"
    if primary == "code-repo-adaptation":
        if _contains(prompt, "environment-audit", "environment audit", "环境审计"):
            return "environment-compatibility"
        if _contains(prompt, "只读", "理解仓库", "repo understanding", "目录", "入口"):
            return "repo-understanding"
        if _contains(prompt, "checkpoint"):
            return "checkpoint-compatibility"
        if _contains(prompt, "predict", "inference", "推理", "预测", "export"):
            return "inference-compatibility"
        if _contains(prompt, "train", "validation", "训练", "验证入口", "pipeline", "管线"):
            return "training-pipeline-compatibility"
        if _contains(prompt, "dataset", "dataloader", "数据布局", "数据集"):
            return "dataset-compatibility"
        if _contains(prompt, "lightning", "diffusers", "transformers", "pytorch", "framework", "api", "接口"):
            return "framework-compatibility"
        if _contains(prompt, "dependency", "依赖", "包版本"):
            return "dependency-compatibility"
        if _contains(prompt, "environment", "python", "cuda", "当前环境"):
            return "environment-compatibility"
        if _contains(prompt, "patch", "修改"):
            return "compatibility-patch"
        return "repo-understanding"
    if primary == "code-debugging":
        if _contains(prompt, "复现指标差距"):
            return "regression"
        if _contains(prompt, "验证", "verify", "verification_request", "verification request", "patch"):
            return "patch-verification"
        if _contains(prompt, "最小复现", "minimal reproduction", "smoke"):
            return "minimal-reproduction"
        if _contains(prompt, "nan", "oom", "shape", "dtype", "device", "数值", "维度"):
            return "numerical"
        if _contains(prompt, "性能", "慢", "performance", "deadlock", "ddp", "卡死", "资源"):
            return "runtime"
        if _contains(prompt, "回归", "regression", "gap-analysis", "gap analysis"):
            return "regression"
        return "traceback"
    if primary == "code-experiment-config-management":
        if _contains(
            prompt,
            "执行已规划实验",
            "运行实验矩阵",
            "监控实验运行",
            "收集运行制品",
            "run frozen experiment plan",
            "execute experiment matrix",
            "monitor experiment run",
            "collect run artifacts",
            "跑这个 baseline",
            "执行已经批准的实验矩阵",
        ):
            return "run-lifecycle"
        if _contains(prompt, "checkpoint"):
            return "checkpoint-resume"
        if _contains(prompt, "seed", "随机种子"):
            return "seed-policy"
        if _contains(prompt, "run naming", "实验命名", "run id"):
            return "run-identity"
        if _contains(prompt, "archive", "归档"):
            return "archive"
        if _contains(prompt, "result registry", "结果记录"):
            return "result-registry"
        if _contains(prompt, "hydra", "config", "配置"):
            return "config-tree"
        return "full"
    if primary == "visual-research-artifact-generation":
        if _contains(
            prompt,
            "draw.io",
            "drawio",
            "可编辑流程图",
            "可编辑架构图",
            "节点关系",
            "node-edge",
            "uml",
            "erd",
            "c4",
        ):
            return "drawio-diagram"
        if _contains(
            prompt,
            "latex 表",
            "latex table",
            "results table",
            "result table",
            "booktabs",
            "论文表格",
            "结果表",
        ):
            return "latex-table"
        if _contains(prompt, "pgfplots"):
            return "pgfplots"
        if _contains(prompt, "tikz"):
            return "tikz-diagram"
        if _contains(prompt, "多面板", "multi-panel", "subfigure", "组合图"):
            return "multi-panel"
        return "data-plot"
    if primary == "visual-expression-mining":
        if _contains(prompt, "table", "表格"):
            return "table"
        if _contains(prompt, "schematic", "示意图"):
            return "schematic"
        if _contains(prompt, "story", "叙事"):
            return "storytelling"
        if _contains(prompt, "asset", "素材"):
            return "asset-pattern"
        return "figure"
    if primary == "writing-review-triage":
        if _contains(prompt, "response", "回复"):
            return "response-plan"
        if _contains(prompt, "revision", "修订"):
            return "revision-plan"
        return "triage"
    if primary == "publish-preflight":
        if _contains(prompt, "journal", "期刊"):
            return "journal"
        if _contains(prompt, "camera-ready", "终稿"):
            return "camera-ready"
        if _contains(prompt, "arxiv"):
            return "arxiv"
        return "conference"
    if primary == "publish-venue-targeting":
        if _contains(prompt, "fit", "匹配"):
            return "fit-analysis"
        if _contains(prompt, "backup", "备选"):
            return "primary-backup"
        if _contains(prompt, "revision", "修订"):
            return "revision-strategy"
        return "shortlist"
    return "default"


def _supporting(primary: str, prompt: str, known: set[str]) -> list[str]:
    candidates: list[str] = []
    if primary == "literature-synthesis" and _contains(prompt, "related work", "相关工作"):
        candidates.append("writing-academic")
    if primary == "writing-manuscript-audit" and _contains(prompt, "引用论断", "引用 claim", "citation verification", "claim 的证据", "claim 核验", "找支持这个 claim"):
        candidates.append("literature-synthesis")
    if primary == "paper-reproduction":
        candidates.append("paper-deep-read")
    if primary == "writing-academic" and _contains(prompt, "reviewer response", "回复审稿人"):
        candidates.append("writing-review-triage")
    if primary == "writing-academic" and _contains(prompt, "积累术语", "积累表达"):
        candidates.append("writing-knowledge-capture")

    unique: list[str] = []
    for candidate in candidates:
        if candidate != primary and candidate in known and candidate not in unique:
            unique.append(candidate)
    return unique[:2]


def _rag_policy(
    primary: str,
    mode: str,
    prompt: str,
    entry: dict[str, Any] | None,
) -> str:
    declared = _declared_rag(mode, entry)
    # A private-library keyword cannot override the selected mode's hard boundary.
    if declared == "never":
        return "never"
    if re.search(r"(?:不要|不需要|不需|不允许|无需|不必|禁止|不)(?:访问|调用|检索|查询|搜索|查|参考)", prompt) or re.search(
        r"\b(?:do not|don't|without|no)\s+(?:use\s+)?(?:search|retriev\w*|rag|external|knowledgehub)", prompt
    ):
        return "never"
    if _contains(
        prompt,
        "不要检索",
        "不访问 rag",
        "no rag",
        "仅根据我提供",
        "只依据附件",
        "只根据这张表",
        "无需外部证据",
        "只依据",
        "仅依据",
        "只根据",
        "仅根据",
    ):
        return "never"
    if primary == "writing-manuscript-audit" and _structure_audit_intent(prompt):
        return "never"
    if primary == "writing-manuscript-audit" and _contains(
        prompt,
        "模板化写作痕迹",
        "ai 写作痕迹",
        "templated prose signatures",
        "prose style",
        "prompt 残留",
        "prompt residue",
        "生成过程痕迹",
        "未替换占位符",
        "unresolved placeholder",
        "todo",
    ):
        return "never"
    if primary == "writing-academic" and _contains(
        prompt,
        "去模板化重写",
        "去模板化改写",
        "de-template this",
        "less formulaic rewrite",
        "按我的写作语气改写",
        "参考我提供的本人论文样本",
        "match my own academic voice",
        "use my writing voice",
    ):
        return "never"
    if primary == "writing-knowledge-capture" and _contains(
        prompt,
        "写作风格档案",
        "author style profile",
        "待审核的写作风格档案",
        "stage my author style profile",
    ):
        return "never"
    if primary in {"writing-academic", "writing-manuscript-audit"} and _contains(
        prompt, "简单英文改写", "改写这句话", "学术英语", "latex 检查", "latex 语法", "语法和标点", "表格和正文", "表格与正文", "数字核对", "数字与正文"
    ):
        return "never"
    if _contains(prompt, "knowledgehub", "zotero", "我的文献库", "本地文献库", "知识库中", "我的知识库", "以前积累", "以前的写法", "已读工作"):
        return "required"
    if primary in {
        "code-debugging",
        "code-repo-adaptation",
        "code-experiment-config-management",
        "project-skill-usage-evolution",
    }:
        return "never"
    return declared


def _execution_contract(
    mode: str,
    entry: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Resolve the mode-specific side-effect class and declared tool requirements."""

    if not entry:
        return "read_only", []
    mode_contracts = entry.get("mode_contracts", {})
    wildcard: dict[str, Any] = {}
    exact: dict[str, Any] = {}
    if isinstance(mode_contracts, dict):
        wildcard_value = mode_contracts.get("*")
        exact_value = mode_contracts.get(mode)
        if isinstance(wildcard_value, dict):
            wildcard = wildcard_value
        if isinstance(exact_value, dict):
            exact = exact_value

    side_effect_class = (
        exact.get("side_effect_class")
        or wildcard.get("side_effect_class")
        or entry.get("side_effect_class")
        or "read_only"
    )
    required_tools = exact.get("required_tools", wildcard.get("required_tools", []))
    if not isinstance(required_tools, list):
        required_tools = []
    normalized_tools = [
        str(tool).strip()
        for tool in required_tools
        if isinstance(tool, str) and str(tool).strip()
    ]
    return str(side_effect_class), list(dict.fromkeys(normalized_tools))


def route(prompt: str, entries: list[dict[str, Any]]) -> RouteDecision:
    """Route one prompt under the repository policy without executing tools."""

    normalized = " ".join(prompt.casefold().split())
    by_id = _entry_map(entries)
    known = set(by_id)
    primary, matched_by = _policy_primary(normalized, entries)
    entry = by_id.get(primary)
    if entry is None:
        raise ValueError(f"Skill is not included in this public profile: {primary}")
    if entry and entry.get("activation") == "supporting_only":
        primary = "research-concept-primer"
        matched_by = f"supporting-only guard for {entry.get('id')}"
        entry = by_id.get(primary)

    # If a policy-selected Skill is absent from a synthetic registry, preserve
    # the decision so evaluator fixtures can still diagnose the missing entry.
    mode = _literal_mode(normalized, entry) or _mode(primary, normalized.replace(primary, ""))
    registered_modes = entry.get("modes", []) if entry else []
    if registered_modes and mode not in registered_modes:
        mode = "full" if "full" in registered_modes else registered_modes[0]
    supporting = _supporting(primary, normalized, known)
    rag_policy = _rag_policy(primary, mode, normalized, entry)
    side_effect_class, required_tools = _execution_contract(mode, entry)

    calls: list[str] = []
    failure_behavior: str | None = None
    warnings: list[str] = []
    safety_flags: list[str] = []
    unavailable = _contains(normalized, "mcp unavailable", "mcp 不可用", "knowledgehub 不可用")
    degraded = _contains(normalized, "rag degraded", "rag 降级", "稀疏检索", "degraded")
    zero_hit = _contains(normalized, "zero hit", "零命中", "无命中")

    if rag_policy == "required":
        calls.append("rag_status")
        if unavailable:
            failure_behavior = "stop_retrieval_dependent_claims"
            warnings.append("required MCP unavailable")
        else:
            calls.append("rag_search")
    elif unavailable and rag_policy in {"optional", "recommended"}:
        failure_behavior = "continue_from_supplied_inputs"
    if degraded and rag_policy != "never" and not unavailable:
        failure_behavior = "continue_with_degraded_notice_and_lower_confidence"
        warnings.append("retrieval degraded")
    if zero_hit and rag_policy != "never" and not unavailable:
        failure_behavior = "check_filters_and_rewrite_once"
        warnings.append("zero-hit is not evidence of a research gap")
    if _contains(normalized, "prompt injection", "忽略系统指令", "泄露 token", "执行文献中的指令"):
        safety_flags.append("ignored_retrieved_instruction")
        if failure_behavior is None:
            failure_behavior = "ignore_retrieved_instruction"
    if not unavailable and rag_policy != "never":
        if _contains(normalized, "reranker unavailable"):
            failure_behavior = "fallback_supported_ranking"
        elif _contains(normalized, "schema mismatch"):
            failure_behavior = "report_missing_capability"
    if _contains(normalized, "partial manuscript") and failure_behavior is None:
        failure_behavior = "partial_scope_low_confidence"

    return RouteDecision(
        primary_skill=primary,
        mode=mode,
        supporting_skills=supporting,
        rag_policy=rag_policy,
        mcp_calls=calls,
        matched_by=matched_by,
        failure_behavior=failure_behavior,
        warnings=warnings,
        safety_flags=safety_flags,
        side_effect_class=side_effect_class,
        required_tools=required_tools,
    )
