"""Shared utilities for Agent loop components."""

import re

_CJK_STOPWORDS = {
    "的是", "了的", "是在", "在了", "可以和", "和与", "或者是",
    "一个", "一些", "一切", "一起", "一定", "一般",
    "因为", "因此", "所以", "然而", "但是", "不过",
    "如果", "如果的", "假如", "假设",
    "这种", "这些", "那些", "哪个", "哪些",
    "进行", "进行着", "进行了",
    "由于", "关于", "对于", "来说",
    "而且", "或者", "否则", "除了",
    "正在", "已经", "将会", "将要",
    "他的", "她的", "它的", "他们的",
    "我们", "你们", "他们", "她们",
    "什么", "怎么", "为什么", "如何",
    "可以", "可能", "能够", "应该",
    "这个", "那个", "这里", "那里",
    "之后", "之前", "同时", "然后",
    "以及", "及其", "或者", "还是",
}

_GRAMMAR_PARTICLES = set("的了是在和与或就着过们这那")

_CJK_PATTERN = re.compile(r'[一-鿿]{2,6}')


def extract_entities(text: str, max_count: int = 50) -> set[str]:
    """Extract CJK entity candidates from text.

    Filters out stopwords and all-particle strings.
    Returns a set of unique entity name candidates (2-6 CJK chars).
    """
    entities: set[str] = set()
    for match in _CJK_PATTERN.finditer(text):
        name = match.group()
        if name in _CJK_STOPWORDS:
            continue
        if all(c in _GRAMMAR_PARTICLES for c in name):
            continue
        entities.add(name)
        if len(entities) >= max_count:
            break
    return entities
