"""Evidence provenance helpers shared by the main and sub-agent runtimes.

Anthropic web-search responses contain two materially different events: a URL
was *discovered* in a result set, and text from that URL was actually *cited*.
Keeping those separate prevents a search-results page from inflating the
research quality counters.  This module deliberately serializes only public
metadata and bounded cited excerpts; ``encrypted_content`` is never retained.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Optional


MAX_EVIDENCE_EXCERPT_CHARS = 2_000


@dataclass(frozen=True)
class EvidenceObservation:
    url: str
    title: Optional[str]
    provenance: str
    excerpt: Optional[str] = None
    page_age: Optional[str] = None
    provider: str = "anthropic_web_search"
    provider_ref: Optional[str] = None


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _bounded_excerpt(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split()).strip()
    return value[:MAX_EVIDENCE_EXCERPT_CHARS] or None


def _stable_ref(kind: str, *parts: Any) -> str:
    material = "\x1f".join(str(part or "") for part in parts)
    return f"{kind}:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def parse_anthropic_evidence(content: Iterable[Any]) -> list[EvidenceObservation]:
    """Extract discovered and cited web evidence from response content.

    Works with SDK model objects and already-serialized dictionaries.  It is
    safe to call on every response, including ``pause_turn`` responses.
    """
    observations: list[EvidenceObservation] = []
    for raw_block in content:
        block = _plain(raw_block)
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "web_search_tool_result":
            result_content = block.get("content")
            if not isinstance(result_content, list):
                continue
            tool_use_id = block.get("tool_use_id") or ""
            for index, raw_result in enumerate(result_content):
                result = _plain(raw_result)
                if not isinstance(result, dict) or result.get("type") != "web_search_result":
                    continue
                url = result.get("url")
                if not isinstance(url, str) or not url.strip():
                    continue
                # Do not copy the dict: it contains encrypted_content.
                observations.append(EvidenceObservation(
                    url=url,
                    title=result.get("title") if isinstance(result.get("title"), str) else None,
                    provenance="discovered",
                    page_age=result.get("page_age") if isinstance(result.get("page_age"), str) else None,
                    provider_ref=f"{tool_use_id}:{index}" if tool_use_id else _stable_ref("result", url, index),
                ))
        elif block_type == "text":
            citations = block.get("citations")
            if not isinstance(citations, list):
                continue
            for raw_citation in citations:
                citation = _plain(raw_citation)
                if not isinstance(citation, dict):
                    continue
                if citation.get("type") not in {"web_search_result_location", "web_search_result_location_param"}:
                    continue
                url = citation.get("url")
                if not isinstance(url, str) or not url.strip():
                    continue
                excerpt = _bounded_excerpt(citation.get("cited_text"))
                observations.append(EvidenceObservation(
                    url=url,
                    title=citation.get("title") if isinstance(citation.get("title"), str) else None,
                    provenance="cited",
                    excerpt=excerpt,
                    provider_ref=_stable_ref("citation", url, excerpt),
                ))
    return observations


def persist_anthropic_evidence(
    dossier_id: str,
    content: Iterable[Any],
    *,
    run_id: Optional[str] = None,
    work_session_id: Optional[str] = None,
) -> int:
    """Best-effort runtime adapter; returns the number of observations saved."""
    from ..storage import evidence_store

    observations = parse_anthropic_evidence(content)
    saved = 0
    for observation in observations:
        try:
            evidence_store.record_observation(
                dossier_id=dossier_id,
                url=observation.url,
                title=observation.title,
                provenance=observation.provenance,
                excerpt=observation.excerpt,
                page_age=observation.page_age,
                provider=observation.provider,
                provider_ref=observation.provider_ref,
                run_id=run_id,
                work_session_id=work_session_id,
            )
            saved += 1
        except ValueError:
            # Malformed/untrusted result URLs do not fail an agent turn.
            continue
    return saved
