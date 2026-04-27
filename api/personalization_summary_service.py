"""Personalization summary — condense user profiles into ≤150-char prompt hints.

Pulls profile-type memories from EverCore, parses explicit_info / implicit_traits,
redacts sensitive fields (emails, phone numbers, OTP codes, secrets), and asks
Claude Haiku to condense the result into a single short paragraph that downstream
clients (e.g. SaySo's 记忆联想 textarea) can ingest as recognition prompt context.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

from open_notebook.config import MEMORY_HUB_URL, MEMORY_HUB_USER_ID

DEFAULT_MAX_CHARS = 150
RAW_CAP = 5000
PROFILE_FETCH_LIMIT = 50
DEFAULT_DASHSCOPE_MODEL = "qwen-plus"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"
CACHE_TTL_SECONDS = 600

PREF_KEYS = (
    "身份信息",
    "语言风格",
    "偏好",
    "兴趣",
    "口头禅",
    "communication",
    "greeting",
    "language_skill",
    "name",
    "contact",
)
FOCUS_KEYS = (
    "最近关注",
    "项目信息",
    "工作专题",
    "关注主题",
    "技术环境",
    "technical",
    "affiliation",
    "availability",
    "行为倾向",
    "行为意图",
)

_REDACTORS: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[邮箱]"),
    (re.compile(r"sk-ant-[\w-]{20,}"), "[密钥]"),
    (re.compile(r"\b(?:sk|pk|ak)[-_][A-Za-z0-9]{20,}\b"), "[密钥]"),
    (
        re.compile(
            r"\b(?:api[-_]?key|access[-_]?token)[-_:= ]+[A-Za-z0-9._-]{12,}",
            re.IGNORECASE,
        ),
        "[密钥]",
    ),
    (re.compile(r"Bearer\s+[\w.-]{8,}", re.IGNORECASE), "[token]"),
    (
        re.compile(
            r"(验证码|verification\s*code|verify\s*code|otp|动态码|短信码)\s*[:：]?\s*\d{4,8}",
            re.IGNORECASE,
        ),
        r"\1[已隐去]",
    ),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[电话]"),
    (re.compile(r"\+\d{1,4}[\s-]?\d{4,15}(?!\d)"), "[电话]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[证件号]"),
    (re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"), "[卡号]"),
    (
        re.compile(r"(密码|password|passwd|pwd)\s*[:：=]\s*\S+", re.IGNORECASE),
        r"\1[已隐去]",
    ),
)

_PLACEHOLDER_RE = re.compile(
    r"\[(邮箱|电话|密钥|token|证件号|卡号|已隐去)\][，。、,;；\s]*"
)


def redact_sensitive(text: str) -> str:
    out = text
    for pat, repl in _REDACTORS:
        out = pat.sub(repl, out)
    return out


def _normalize_category(cat: str) -> str:
    return re.sub(r"[\[\]【】]", "", cat).strip().lower()


def _match_any(cat: str, keys: Tuple[str, ...]) -> bool:
    n = _normalize_category(cat)
    return any(k.lower() in n for k in keys)


async def _fetch_profiles(user_id: str) -> List[Dict[str, Any]]:
    """Fetch raw profile memories from EverCore (port 1995 by default)."""
    payload = {
        "filters": {"user_id": user_id},
        "memory_type": "profile",
        "limit": PROFILE_FETCH_LIMIT,
        "offset": 0,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{MEMORY_HUB_URL}/api/v1/memories/get", json=payload)
        resp.raise_for_status()
        body = resp.json()
    return ((body or {}).get("data") or {}).get("profiles") or []


def _bucketize(profiles: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    prefs: List[str] = []
    focus: List[str] = []
    others: List[str] = []
    seen: set[str] = set()

    def push(arr: List[str], s: str) -> None:
        key = s[:80]
        if key in seen:
            return
        seen.add(key)
        arr.append(s)

    for p in profiles:
        pd = p.get("profile_data") or {}
        items = (pd.get("explicit_info") or []) + (pd.get("implicit_traits") or [])
        for item in items:
            cat = (item.get("category") or "").strip()
            raw_desc = (item.get("description") or "").strip()
            if not raw_desc:
                continue
            desc = redact_sensitive(raw_desc)
            if _match_any(cat, PREF_KEYS):
                push(prefs, desc)
            elif _match_any(cat, FOCUS_KEYS):
                push(focus, desc)
            else:
                push(others, f"{cat}:{desc}" if cat else desc)

    return {"preferences": prefs, "recent_focus": focus, "other": others}


def _build_raw(buckets: Dict[str, List[str]]) -> str:
    sections: List[str] = []
    if buckets["preferences"]:
        sections.append("【用户偏好】\n" + "\n".join(buckets["preferences"]))
    if buckets["recent_focus"]:
        sections.append("【最近关注】\n" + "\n".join(buckets["recent_focus"]))
    if not sections and buckets["other"]:
        sections.append("\n".join(buckets["other"][:6]))
    return "\n\n".join(sections)[:RAW_CAP]


def _build_prompt(raw: str, max_chars: int) -> str:
    return (
        f"把下面用户画像凝练为不超过 {max_chars} 个中文字符的口播术语线索，"
        "单段，不分点，不要复述行业/职业字段，只保留对语音转写有用的偏好"
        "与近期关注（专业术语、项目名、人名、口头风格）。\n\n"
        "严格禁止：邮箱、电话、验证码、密码、API 密钥、token、身份证号、"
        "银行卡号、住址等任何敏感字段一律省略，不要输出占位符（如「[邮箱]」"
        "「[电话]」），宁可遗漏也不展示。\n\n"
        "直接输出凝练后内容，不要前后缀，不要加引号。\n\n"
        f"{raw}"
    )


async def _condense_via_dashscope(
    raw: str, max_chars: int, api_key: str
) -> Optional[str]:
    base_url = os.environ.get(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    model = os.environ.get("DASHSCOPE_MODEL", DEFAULT_DASHSCOPE_MODEL)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "max_tokens": 256,
                    "messages": [
                        {"role": "user", "content": _build_prompt(raw, max_chars)}
                    ],
                },
            )
        if resp.status_code >= 400:
            logger.warning(
                "[personalization-summary] dashscope HTTP {}: {}",
                resp.status_code,
                resp.text[:200],
            )
            return None
        body = resp.json()
        text = (
            ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
            or ""
        ).strip()
        return text or None
    except Exception as e:
        logger.warning("[personalization-summary] dashscope condense failed: {}", e)
        return None


async def _condense_via_anthropic(
    raw: str, max_chars: int, api_key: str
) -> Optional[str]:
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": model,
                    "max_tokens": 256,
                    "messages": [
                        {"role": "user", "content": _build_prompt(raw, max_chars)}
                    ],
                },
            )
        if resp.status_code >= 400:
            logger.warning(
                "[personalization-summary] anthropic HTTP {}: {}",
                resp.status_code,
                resp.text[:200],
            )
            return None
        body = resp.json()
        for block in body.get("content") or []:
            if block.get("type") == "text":
                text = (block.get("text") or "").strip()
                if text:
                    return text
        return None
    except Exception as e:
        logger.warning("[personalization-summary] anthropic condense failed: {}", e)
        return None


async def _condense(raw: str, max_chars: int) -> Optional[str]:
    dash_key = os.environ.get("DASHSCOPE_API_KEY")
    if dash_key:
        text = await _condense_via_dashscope(raw, max_chars, dash_key)
    else:
        anth_key = os.environ.get("ANTHROPIC_API_KEY")
        if not anth_key:
            logger.info(
                "[personalization-summary] no LLM key (DASHSCOPE_API_KEY/"
                "ANTHROPIC_API_KEY), skipping condense"
            )
            return None
        text = await _condense_via_anthropic(raw, max_chars, anth_key)
    if not text:
        return None
    cleaned = _PLACEHOLDER_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_chars] or None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_cache: Dict[Tuple[str, int], Tuple[float, Dict[str, Any]]] = {}


def _cache_get(key: Tuple[str, int]) -> Optional[Dict[str, Any]]:
    entry = _cache.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.monotonic() - ts > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: Tuple[str, int], value: Dict[str, Any]) -> None:
    _cache[key] = (time.monotonic(), value)


async def get_personalization_summary(
    user_id: Optional[str] = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Return condensed personalization summary for a user.

    Response:
        {
          "user_id": str,
          "text": str,                # ≤max_chars condensed paragraph
          "mode": "llm"|"truncated"|"empty",
          "buckets": {preferences, recent_focus, other},   # post-redaction
        }
    """
    uid = user_id or MEMORY_HUB_USER_ID
    cache_key = (uid, max_chars)
    if use_cache:
        cached = _cache_get(cache_key)
        if cached:
            return cached

    profiles = await _fetch_profiles(uid)
    if not profiles:
        result = {"user_id": uid, "text": "", "mode": "empty", "buckets": {}}
        _cache_set(cache_key, result)
        return result

    buckets = _bucketize(profiles)
    raw = _build_raw(buckets)
    if not raw:
        result = {"user_id": uid, "text": "", "mode": "empty", "buckets": buckets}
        _cache_set(cache_key, result)
        return result

    condensed = await _condense(raw, max_chars)
    if condensed:
        result = {
            "user_id": uid,
            "text": condensed,
            "mode": "llm",
            "buckets": buckets,
        }
    else:
        fallback = (
            (buckets["preferences"][:1] or buckets["recent_focus"][:1] or buckets["other"][:1])
            or [""]
        )[0]
        result = {
            "user_id": uid,
            "text": fallback[:max_chars],
            "mode": "truncated",
            "buckets": buckets,
        }
    _cache_set(cache_key, result)
    return result
