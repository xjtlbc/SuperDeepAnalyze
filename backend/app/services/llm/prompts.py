"""Prompt templates for pre-compilation pipeline."""


def _build_l1_prompt(kb_id: str = "") -> str:
    """Build domain-adaptive L1 summary prompt."""
    if kb_id:
        from app.services.prompts.domain import detect_kb_domain, get_domain_config
        domain = detect_kb_domain(kb_id)
        cfg = get_domain_config(domain)
    else:
        cfg = {
            "material": "知识库文档",
            "entity_types": "人物、组织、地点、事件、概念、物品",
        }

    return f"""你是一个{cfg['material']}分析专家。请对以下文档片段进行摘要分析。

## 要求：
1. 生成 3-5 行的段落摘要，保留关键事实
2. 提取文中出现的实体及其关系
3. 标注疑点或不一致之处

## 文档内容：
{{content}}

## 输出格式（JSON）：
{{{{
  "summary": "段落摘要内容",
  "entities_mentioned": ["实体A", "实体B"],
  "relations": [{{{{"from": "实体A", "to": "实体B", "type": "关系类型", "confidence": 0.85}}}}],
  "contradictions": [{{{{"type": "inconsistency", "description": "矛盾描述"}}}}]
}}}}
"""


def _build_l0_prompt(kb_id: str = "") -> str:
    """Build domain-adaptive L0 entity extraction prompt."""
    if kb_id:
        from app.services.prompts.domain import detect_kb_domain, get_domain_config
        domain = detect_kb_domain(kb_id)
        cfg = get_domain_config(domain)
    else:
        cfg = {
            "material": "知识库文档",
            "entity_types": "人物/组织/地点/事件/物品/概念",
        }

    return f"""你是一个{cfg['material']}分析专家。请基于以下摘要，构建全局实体库、关系网络和时间线。

## 要求：
1. 提取所有实体（{cfg['entity_types']}），包括别名（aliases）和结构化属性（attributes）
2. 提取实体之间的关系（relations），每条关系必须标注：
   - from/to: 实体名称
   - type: 关系类型
   - confidence: 置信度标签（EXTRACTED=原文明确记载 / INFERRED=合理推断 / AMBIGUOUS=存疑）
   - evidence: 证据来源（摘要片段或文档id）
3. 记录每个实体在哪些文档中被提及（mentions: doc_id + chunk_ids）
4. 按时间排序构建事件时间线
5. 构建事件之间的因果/时序关系图
6. 标注文档之间的交叉引用和矛盾点

## 置信度标签说明：
- EXTRACTED: 原文明确记载，有直接证据支撑
- INFERRED: 通过上下文合理推断，但无直接原文
- AMBIGUOUS: 信息不完整或存在矛盾，需进一步验证

## 摘要内容：
{{summaries}}

## 输出格式（JSON）：
{{{{
  "entities": [
    {{{{
      "name": "实体名称",
      "type": "person|organization|location|event|concept|method|model|dataset|metric",
      "aliases": ["别名"],
      "attributes": {{{{"属性名": "属性值"}}}},
      "confidence": "EXTRACTED",
      "mentions": [{{{{"doc_id": "doc_001", "chunk_ids": ["chunk_003"]}}}}]
    }}}}
  ],
  "relations": [
    {{{{
      "from": "实体A",
      "to": "实体B",
      "type": "关系类型",
      "confidence": "EXTRACTED",
      "evidence": "摘要中记载：..."
    }}}}
  ],
  "timeline": [
    {{{{
      "time": "2024-03-15",
      "description": "事件描述",
      "participants": ["实体A"],
      "confidence": "EXTRACTED",
      "evidence": "doc_002/chunk_008"
    }}}}
  ],
  "event_graph": {{{{
    "nodes": [{{{{"id": "evt_001", "label": "事件名称", "type": "event"}}}}],
    "edges": [{{{{"source": "evt_001", "target": "evt_002", "label": "导致", "confidence": "INFERRED"}}}}]
  }}}},
  "cross_refs": [
    {{{{
      "doc_a": "doc_001",
      "doc_b": "doc_002",
      "relation": "关系描述",
      "contradiction": false,
      "description": "..."
    }}}}
  ]
}}}}
"""


class Prompts:
    """Centralized prompt templates — delegates to domain-adaptive builders."""

    L1_SUMMARY = _build_l1_prompt()
    L0_ENTITY = _build_l0_prompt()

    DOCUMENT_ANALYSIS = """分析以下文档，提取关键信息。

## 文档内容：
{content}

## 请输出：
1. 文档类型判断
2. 关键实体列表
3. 关键时间节点
4. 核心事实摘要
"""

    @classmethod
    def format(cls, template_name: str, **kwargs) -> str:
        """Format a prompt template with given variables."""
        template = getattr(cls, template_name, None)
        if template is None:
            raise ValueError(f"Unknown prompt template: {template_name}")
        return template.format(**kwargs)

    @classmethod
    def format_for_kb(cls, template_name: str, kb_id: str, **kwargs) -> str:
        """Format a domain-adaptive prompt for a specific KB."""
        if template_name == "L1_SUMMARY":
            template = _build_l1_prompt(kb_id)
        elif template_name == "L0_ENTITY":
            template = _build_l0_prompt(kb_id)
        else:
            template = getattr(cls, template_name, None)
            if template is None:
                raise ValueError(f"Unknown prompt template: {template_name}")
        return template.format(**kwargs)

    @classmethod
    def format(cls, template_name: str, **kwargs) -> str:
        """Format a prompt template with given variables."""
        template = getattr(cls, template_name, None)
        if template is None:
            raise ValueError(f"Unknown prompt template: {template_name}")
        return template.format(**kwargs)
