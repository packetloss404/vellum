"""Storage for canonical sources, provenance observations and claim links."""
from __future__ import annotations

import hashlib
import posixpath
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .. import models as m
from ..db import connect


MAX_EXCERPT_CHARS = 2_000
_TRACKING_KEYS = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid"}
_OFFICIAL_EXACT = {"europa.eu", "gc.ca", "canada.ca", "gov.uk"}


def canonicalize_url(url: str) -> str:
    """Return a conservative HTTP(S) canonical URL or raise ``ValueError``."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("source URL is required")
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid source URL") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source URL must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URL must not contain credentials")
    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise ValueError("invalid source hostname") from exc
    if host.startswith("www."):
        host = host[4:]
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    normalized_path = posixpath.normpath(path)
    if path.endswith("/") and normalized_path != "/":
        normalized_path += "/"
    if not normalized_path.startswith("/"):
        normalized_path = "/" + normalized_path
    retained_query = [
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_KEYS and not key.lower().startswith("utm_")
    ]
    query = urlencode(sorted(retained_query), doseq=True)
    return urlunsplit((scheme, netloc, normalized_path, query, ""))


def _domain(canonical_url: str) -> str:
    return (urlsplit(canonical_url).hostname or "").lower()


def official_domain_marker(domain: str) -> tuple[str, str]:
    domain = domain.lower().rstrip(".")
    is_official = (
        domain.endswith(".gov") or domain.endswith(".mil")
        or domain in _OFFICIAL_EXACT
        or any(domain.endswith("." + official) for official in _OFFICIAL_EXACT)
    )
    if is_official:
        return "government_domain", "deterministic_official_domain"
    return "unverified", "model_labels_are_claimed_not_verified"


def _now() -> str:
    return m.utc_now().isoformat()


def _bounded(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return " ".join(value.split())[:MAX_EXCERPT_CHARS] or None


_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "superseded"}


def _validate_writable_run(conn, dossier_id: str, run_id: str) -> str:
    row = conn.execute(
        "SELECT id,status FROM research_runs WHERE id=? AND dossier_id=?",
        (run_id, dossier_id),
    ).fetchone()
    if row is None:
        raise ValueError("research run does not belong to dossier")
    if row["status"] in _TERMINAL_RUN_STATUSES:
        raise ValueError(f"research run is {row['status']} and cannot accept evidence")
    return run_id


def _resolve_write_run_id(
    conn,
    dossier_id: str,
    run_id: Optional[str],
    work_session_id: Optional[str],
) -> Optional[str]:
    """Resolve attribution without guessing from the dossier's newest run."""
    if work_session_id:
        session = conn.execute(
            "SELECT dossier_id,research_run_id,ended_at FROM work_sessions WHERE id=?",
            (work_session_id,),
        ).fetchone()
        if session is None or session["dossier_id"] != dossier_id:
            raise ValueError("work session does not belong to dossier")
        if session["ended_at"] is not None:
            raise ValueError("ended work session cannot accept evidence")
        derived_run_id = session["research_run_id"]
        if run_id is not None and run_id != derived_run_id:
            raise ValueError("research run does not match work session")
        return (
            _validate_writable_run(conn, dossier_id, derived_run_id)
            if derived_run_id else None
        )
    if run_id:
        return _validate_writable_run(conn, dossier_id, run_id)
    return None


def _resolve_audit_run_id(conn, dossier_id: str, run_id: Optional[str]) -> Optional[str]:
    if run_id:
        row = conn.execute(
            "SELECT id FROM research_runs WHERE id=? AND dossier_id=?", (run_id, dossier_id)
        ).fetchone()
        if row is None:
            raise ValueError("research run does not belong to dossier")
        return run_id
    row = conn.execute(
        "SELECT id FROM research_runs WHERE dossier_id = ? AND status IN "
        "('queued','running','pause_requested','waiting_for_user','blocked_sleep','paused','cap_reached','quarantined') "
        "ORDER BY started_at DESC LIMIT 1", (dossier_id,)
    ).fetchone()
    return row["id"] if row else None


def record_observation(
    *, dossier_id: str, url: str, provenance: str, title: Optional[str] = None,
    excerpt: Optional[str] = None, page_age: Optional[str] = None,
    published_at: Optional[str] = None, provider: Optional[str] = None,
    provider_ref: Optional[str] = None, run_id: Optional[str] = None,
    work_session_id: Optional[str] = None, source_kind: Optional[str] = None,
    model_source_type: Optional[str] = None, model_authority: Optional[str] = None,
    limitations: Optional[str] = None,
) -> dict[str, Any]:
    if provenance not in {"discovered", "cited", "consulted", "user_provided"}:
        raise ValueError("invalid evidence provenance")
    canonical = canonicalize_url(url)
    source_kind = source_kind or "web"
    domain = _domain(canonical)
    authority_status, authority_basis = official_domain_marker(domain)
    excerpt = _bounded(excerpt)
    limitations = _bounded(limitations)
    excerpt_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest() if excerpt else None
    now = _now()
    with connect() as conn:
        run_id = _resolve_write_run_id(
            conn, dossier_id, run_id, work_session_id
        )
        # The schema's provider/provider_ref uniqueness is global. Namespace
        # by dossier and run/session identity so the same cited excerpt in a
        # later research run becomes evidence for that run, not a pointer to
        # an older observation.
        if provider and provider_ref:
            scope = run_id or work_session_id or "unscoped"
            provider_ref = f"{dossier_id}:{scope}:{provider_ref}"
        row = conn.execute(
            "SELECT id FROM evidence_sources WHERE dossier_id = ? AND canonical_url = ?",
            (dossier_id, canonical),
        ).fetchone()
        source_id = row["id"] if row else m.new_id("src")
        conn.execute(
            """INSERT INTO evidence_sources
               (id,dossier_id,canonical_url,original_url,title,domain,source_kind,
                model_source_type,model_authority,authority_status,authority_basis,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(dossier_id,canonical_url) DO UPDATE SET
                 title=COALESCE(excluded.title,evidence_sources.title),
                 source_kind=COALESCE(excluded.source_kind,evidence_sources.source_kind),
                 model_source_type=COALESCE(excluded.model_source_type,evidence_sources.model_source_type),
                 model_authority=COALESCE(excluded.model_authority,evidence_sources.model_authority),
                 authority_status=excluded.authority_status,authority_basis=excluded.authority_basis,
                 updated_at=excluded.updated_at""",
            (source_id,dossier_id,canonical,url,title,domain,source_kind,model_source_type,
             model_authority,authority_status,authority_basis,now,now),
        )
        row = conn.execute(
            "SELECT id FROM evidence_sources WHERE dossier_id = ? AND canonical_url = ?",
            (dossier_id, canonical),
        ).fetchone()
        source_id = row["id"]
        observation_id = m.new_id("obs")
        if provider and provider_ref:
            prior = conn.execute(
                "SELECT id FROM evidence_observations WHERE provider = ? AND provider_ref = ?",
                (provider, provider_ref),
            ).fetchone()
            if prior:
                owner = conn.execute(
                    "SELECT es.dossier_id,eo.source_id FROM evidence_observations eo "
                    "JOIN evidence_sources es ON es.id=eo.source_id WHERE eo.id=?",
                    (prior["id"],),
                ).fetchone()
                if owner is None or owner["dossier_id"] != dossier_id:
                    raise ValueError("provider reference belongs to another dossier")
                if owner["source_id"] != source_id:
                    raise ValueError("provider reference belongs to another source")
                observation_id = prior["id"]
        conn.execute(
            """INSERT OR IGNORE INTO evidence_observations
               (id,source_id,run_id,work_session_id,provenance,retrieved_at,page_age,published_at,
                excerpt,excerpt_sha256,limitations,provider,provider_ref,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (observation_id,source_id,run_id,work_session_id,provenance,now,page_age,published_at,
             excerpt,excerpt_hash,limitations,provider,provider_ref,now),
        )
    return {"source_id": source_id, "observation_id": observation_id,
            "canonical_url": canonical, "authority_status": authority_status}


def record_claim_links(
    *, dossier_id: str, observation_id: str, claims: list[str], relation: str,
    run_id: Optional[str] = None, plan_item_id: Optional[str] = None,
    section_id: Optional[str] = None, excerpt: Optional[str] = None,
    materiality: str = "material", primary_required: bool = False,
) -> list[str]:
    if relation not in {"supports", "contradicts", "context"}:
        raise ValueError("invalid claim evidence relation")
    if materiality not in {"material", "supporting"}:
        raise ValueError("invalid claim materiality")
    with connect() as conn:
        obs = conn.execute(
            "SELECT es.dossier_id,eo.run_id FROM evidence_observations eo JOIN evidence_sources es ON es.id=eo.source_id WHERE eo.id=?",
            (observation_id,),
        ).fetchone()
        if obs is None or obs["dossier_id"] != dossier_id:
            raise ValueError("evidence observation does not belong to dossier")
        observation_run_id = obs["run_id"]
        if run_id is not None and run_id != observation_run_id:
            raise ValueError("evidence observation belongs to another research run")
        run_id = (
            _validate_writable_run(conn, dossier_id, observation_run_id)
            if observation_run_id else None
        )
        if section_id:
            row = conn.execute("SELECT dossier_id FROM sections WHERE id=?", (section_id,)).fetchone()
            if row is None or row["dossier_id"] != dossier_id:
                raise ValueError("section does not belong to dossier")
        if plan_item_id:
            row = conn.execute(
                "SELECT dossier_id FROM plan_items WHERE dossier_id=? AND (id=? OR plan_item_id=?)",
                (dossier_id, plan_item_id, plan_item_id),
            ).fetchone()
            if row is None:
                raise ValueError("plan item does not belong to dossier")
        ids: list[str] = []
        now = _now()
        for text in claims:
            text = " ".join(str(text).split()).strip()
            if not text:
                continue
            existing = conn.execute(
                "SELECT id FROM research_claims WHERE dossier_id=? AND claim_text=? "
                "AND COALESCE(run_id,'')=COALESCE(?,'') AND COALESCE(plan_item_id,'')=COALESCE(?,'') "
                "AND COALESCE(section_id,'')=COALESCE(?,'') LIMIT 1",
                (dossier_id, text, run_id, plan_item_id, section_id),
            ).fetchone()
            claim_id = existing["id"] if existing else m.new_id("clm")
            if existing:
                conn.execute(
                    "UPDATE research_claims SET materiality=?,primary_required=MAX(primary_required,?),updated_at=? WHERE id=?",
                    (materiality, int(primary_required), now, claim_id),
                )
            else:
                conn.execute(
                    """INSERT INTO research_claims
                       (id,dossier_id,run_id,plan_item_id,section_id,claim_text,materiality,status,primary_required,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,'active',?,?,?)""",
                    (claim_id,dossier_id,run_id,plan_item_id,section_id,text,materiality,int(primary_required),now,now),
                )
            conn.execute(
                "INSERT OR IGNORE INTO claim_evidence (claim_id,observation_id,relation,excerpt,created_at) VALUES (?,?,?,?,?)",
                (claim_id,observation_id,relation,_bounded(excerpt),now),
            )
            ids.append(claim_id)
    return ids


def completion_audit(dossier_id: str, run_id: Optional[str] = None) -> dict[str, Any]:
    """Deterministic inputs for the model's final evidence audit."""
    with connect() as conn:
        run_id = _resolve_audit_run_id(conn, dossier_id, run_id)
        run_clause = " AND rc.run_id = ?" if run_id else ""
        params: tuple[Any, ...] = (dossier_id, run_id) if run_id else (dossier_id,)
        claims = conn.execute(
            "SELECT rc.id,rc.claim_text,rc.primary_required," 
            "COUNT(DISTINCT CASE WHEN eo.provenance IN ('cited','consulted','user_provided') THEN ce.observation_id END) evidence_count," 
            "COUNT(DISTINCT CASE WHEN eo.provenance IN ('cited','consulted','user_provided') "
            "AND es.model_source_type='primary' AND es.authority_status='government_domain' "
            "THEN ce.observation_id END) qualified_primary_count "
            "FROM research_claims rc LEFT JOIN claim_evidence ce ON ce.claim_id=rc.id "
            "LEFT JOIN evidence_observations eo ON eo.id=ce.observation_id "
            "LEFT JOIN evidence_sources es ON es.id=eo.source_id "
            "WHERE rc.dossier_id=? AND rc.status='active'" + run_clause + " GROUP BY rc.id",
            params,
        ).fetchall()
        unsupported = [
            dict(row) for row in claims
            if int(row["evidence_count"] or 0) == 0
            or (bool(row["primary_required"]) and int(row["qualified_primary_count"] or 0) == 0)
        ]
        qualified_sql = (
            "SELECT COUNT(DISTINCT es.id) n FROM evidence_sources es JOIN evidence_observations eo ON eo.source_id=es.id "
            "WHERE es.dossier_id=? AND eo.provenance IN ('cited','consulted','user_provided')"
        )
        qualified_params: tuple[Any, ...] = (dossier_id,)
        if run_id:
            qualified_sql += " AND eo.run_id=?"
            qualified_params = (dossier_id, run_id)
        qualified = conn.execute(qualified_sql, qualified_params).fetchone()["n"]
        requires_disconfirmation = False
        disconfirmation_recorded = True
        if run_id:
            run = conn.execute("SELECT depth FROM research_runs WHERE id=?", (run_id,)).fetchone()
            requires_disconfirmation = bool(run and run["depth"] == "deep")
            if requires_disconfirmation:
                disconfirmation_recorded = bool(conn.execute(
                    "SELECT 1 FROM reasoning_trail WHERE dossier_id=? "
                    "AND tags LIKE '%\"disconfirmation\"%' AND tags LIKE ? LIMIT 1",
                    (dossier_id, f'%\"research_run:{run_id}\"%'),
                ).fetchone())
        ready = not unsupported and bool(claims) and disconfirmation_recorded
    return {"run_id": run_id, "claim_count": len(claims), "qualified_source_count": qualified,
            "unsupported_claims": unsupported,
            "requires_disconfirmation": requires_disconfirmation,
            "disconfirmation_recorded": disconfirmation_recorded,
            "ready": ready}
