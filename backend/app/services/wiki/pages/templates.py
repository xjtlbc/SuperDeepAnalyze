"""Wiki page templates and frontmatter with domain-adaptive specialization."""

PAGE_TEMPLATE = """---
title: {title}
type: {page_type}
created: {created}
tags: {tags}
sources: {sources}
community: {community}
importance: {importance}
---

# {title}

{content}
"""

# Legal case specialized page templates
LEGAL_TEMPLATES = {
    "person": """## 基本信息
{basic_info}

## 关系网络
{relations}

## 涉及事件
{events}

## 证词/陈述
{testimony}

## 可信度评估
{credibility}
""",
    "event": """## 事件经过
{description}

## 涉及人物
{participants}

## 相关证据
{evidence}

## 各方描述对比
{comparisons}

## 矛盾标注
{contradictions}
""",
    "evidence": """## 证据内容
{content}

## 来源文档
{source_doc}

## 争议点
{disputes}

## 关联事件
{related_events}

## 可信度等级
{confidence_level}
""",
}


def build_frontmatter(
    title: str,
    page_type: str,
    tags: list[str] | None = None,
    sources: list[dict] | None = None,
    community: int = 0,
    importance: float = 0.0,
) -> dict:
    """Build frontmatter dict for a wiki page."""
    from datetime import datetime, timezone
    return {
        "title": title,
        "type": page_type,
        "created": datetime.now(timezone.utc).isoformat(),
        "tags": tags or [],
        "sources": sources or [],
        "community": community,
        "importance": importance,
    }


def render_page(title: str, page_type: str, content: str, frontmatter: dict) -> str:
    """Render a complete wiki page with frontmatter."""
    fm = frontmatter.copy()
    tags_str = str(fm.get("tags", []))
    sources_str = str(fm.get("sources", []))
    return PAGE_TEMPLATE.format(
        title=title,
        page_type=page_type,
        created=fm.get("created", ""),
        tags=tags_str,
        sources=sources_str,
        community=fm.get("community", 0),
        importance=fm.get("importance", 0.0),
        content=content,
    )


def detect_template_type(title: str, description: str = "", domain: str = "general") -> str:
    """Detect which template to use based on page title/description and domain."""
    text = (title + description).lower()

    # Technical domain keywords
    if domain == "technical":
        if any(kw in text for kw in ["方法", "模型", "算法", "框架", "架构", "method", "model", "algorithm", "framework"]):
            return "method"
        if any(kw in text for kw in ["概念", "定义", "原理", "concept", "definition"]):
            return "concept"
        if any(kw in text for kw in ["实验", "结果", "评估", "experiment", "result", "evaluation"]):
            return "method"

    # Legal/investigation domain keywords
    if any(kw in text for kw in ["证据", "物证", "书证", "证词", "口供", "笔录"]):
        return "evidence"
    if any(kw in text for kw in ["事件", "经过", "案发", "时间线"]):
        return "event"
    if any(kw in text for kw in ["人物", "嫌疑人", "被害人", "被告", "原告"]):
        return "person"
    if "证人" in text:
        return "person"
    return "default"


def build_page_context(catalog_node: dict, report, domain: str = "general") -> str:
    """Build context string for page generation based on catalog node and report data."""
    from app.services.prompts.domain import get_domain_config
    cfg = get_domain_config(domain)

    path = catalog_node.get("full_path", catalog_node.get("path", ""))
    title = catalog_node.get("title", "")
    description = catalog_node.get("description", "")

    parts = [f"请为wiki页面 '{title}' (路径: {path}) 生成内容。", f"页面描述: {description}", ""]

    # Detect template type and add domain-adaptive instructions
    template_type = detect_template_type(title, description, domain)
    if template_type == "person":
        parts.append("请按以下结构生成人物页面：")
        parts.append("1. 基本信息（姓名、身份、角色）")
        parts.append("2. 关系网络（与其他人物的关系，使用 [[人物名]] 链接）")
        parts.append("3. 涉及事件（列出该人物参与的关键事件）")
        parts.append("4. 证词/陈述（如有）")
        parts.append("5. 可信度评估（基于证词一致性和证据支持度）")
        parts.append("")
    elif template_type == "concept":
        parts.append("请按以下结构生成概念页面：")
        parts.append("1. 定义与背景（概念定义、提出背景）")
        parts.append("2. 核心原理（关键机制或算法描述）")
        parts.append("3. 与其他概念的关系（使用 [[概念名]] 链接）")
        parts.append("4. 应用场景（实际应用或实验结果）")
        parts.append("5. 局限与改进（已知局限和改进方向）")
        parts.append("")
    elif template_type == "method":
        parts.append("请按以下结构生成方法/模型页面：")
        parts.append("1. 方法概述（核心思想和创新点）")
        parts.append("2. 技术细节（架构、算法、关键设计）")
        parts.append("3. 实验结果（数据集、指标、对比）")
        parts.append("4. 与相关方法的关系（使用 [[方法名]] 链接）")
        parts.append("5. 局限与未来工作")
        parts.append("")
    elif template_type == "event":
        parts.append("请按以下结构生成事件页面：")
        parts.append("1. 事件经过（时间、地点、具体过程）")
        parts.append("2. 涉及人物/实体（使用 [[实体名]] 链接）")
        parts.append("3. 相关证据/数据（列出支持该描述的证据）")
        parts.append("4. 影响与后果")
        parts.append("5. 矛盾标注（如存在矛盾，明确指出）")
        parts.append("")
    elif template_type == "evidence":
        parts.append("请按以下结构生成证据页面：")
        parts.append("1. 证据内容（详细描述）")
        parts.append("2. 来源文档（标注出处）")
        parts.append("3. 争议点（如对该证据有争议）")
        parts.append("4. 关联事件（该证据支持或反驳的事件）")
        parts.append("5. 可信度等级（EXTRACTED/INFERRED/AMBIGUOUS）")
        parts.append("")

    # Add relevant data from report
    if "人物" in title or "person" in template_type:
        persons = [e for e in report.entities if e.type == "person"]
        parts.append(f"## 相关人物实体（共{len(persons)}个）")
        for e in persons[:20]:
            aliases = f"，别名：{', '.join(e.aliases)}" if e.aliases else ""
            attrs = f"，属性：{e.attributes}" if e.attributes else ""
            parts.append(f"- {e.name}{aliases}{attrs}")

    if "矛盾" in title or "contradiction" in path.lower():
        parts.append("## 矛盾点")
        for c in report.contradictions:
            parts.append(f"- [{c.severity}] {c.description} (涉及: {', '.join(c.involved_entities)})")

    if "缺口" in title or "gap" in path.lower():
        parts.append("## 知识缺口")
        for g in report.knowledge_gaps:
            parts.append(f"- {g.description} (建议: {g.suggestion})")

    if "叙事" in title or "thread" in path.lower():
        parts.append("## 叙事线索")
        for t in report.narrative_threads:
            parts.append(f"- {t.title}: {t.description}")

    return "\n".join(parts)
