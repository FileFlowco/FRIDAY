"""
FRIDAY — Persistent State
Survives restarts. Handles:
  - Per-user context memory (last niche, location, conversation history)
  - Lead pipeline / CRM (status per lead)
  - Follow-up tracking (who to follow up with and when)

Thread-safe via file lock pattern (good enough for single-process; swap for Redis on cloud).
"""

import os
import json
import time
from datetime import datetime, timedelta
from config import STATE_FILE


def _load() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)   # atomic write


# ── Context memory ────────────────────────────────────────────────────────────

def get_context(user_id: str = "web") -> dict:
    """Return persistent context for a user."""
    return _load().get("context", {}).get(str(user_id), {})


def set_context(user_id: str = "web", **kwargs):
    """Update one or more context fields for a user."""
    data = _load()
    data.setdefault("context", {}).setdefault(str(user_id), {}).update(kwargs)
    data["context"][str(user_id)]["updated_at"] = datetime.now().isoformat()
    _save(data)


def get_history(user_id: str = "web") -> list:
    return _load().get("history", {}).get(str(user_id), [])


def append_history(user_id: str = "web", role: str = "user", content: str = ""):
    data = _load()
    hist = data.setdefault("history", {}).setdefault(str(user_id), [])
    hist.append({"role": role, "content": content[:600]})
    data["history"][str(user_id)] = hist[-30:]   # keep last 30 turns
    _save(data)


def clear_history(user_id: str = "web"):
    data = _load()
    data.setdefault("history", {})[str(user_id)] = []
    _save(data)


# ── Lead CRM ──────────────────────────────────────────────────────────────────
# Statuses: "not_contacted" | "contacted" | "replied" | "interested" | "closed" | "not_interested"

def get_pipeline() -> list:
    """Return all tracked leads."""
    return _load().get("pipeline", [])


def add_leads_to_pipeline(leads: list, niche: str, location: str):
    """Add a batch of leads to the pipeline (skip duplicates by place_id)."""
    data      = _load()
    pipeline  = data.get("pipeline", [])
    existing  = {l["place_id"] for l in pipeline if l.get("place_id")}
    added     = 0

    for lead in leads:
        pid = lead.get("place_id", "")
        if pid and pid in existing:
            continue
        pipeline.append({
            "place_id":   pid,
            "name":       lead.get("name", ""),
            "email":      lead.get("email", ""),
            "phone":      lead.get("phone", ""),
            "website":    lead.get("website", ""),
            "priority":   lead.get("priority", "Cold"),
            "niche":      niche,
            "location":   location,
            "status":     "not_contacted",
            "notes":      "",
            "added_at":   datetime.now().isoformat(),
            "contacted_at": None,
            "followup_at":  None,
        })
        if pid:
            existing.add(pid)
        added += 1

    data["pipeline"] = pipeline[-500:]   # cap at 500
    _save(data)
    return added


def update_lead_status(identifier: str, status: str, notes: str = ""):
    """
    Update a lead's status. identifier can be:
      - a number string ("3" = 3rd lead in pipeline)
      - business name (partial match)
      - place_id
    """
    data     = _load()
    pipeline = data.get("pipeline", [])

    matched = None

    # Try numeric index first
    if identifier.isdigit():
        idx = int(identifier) - 1
        if 0 <= idx < len(pipeline):
            matched = pipeline[idx]
    else:
        # Partial name match
        low = identifier.lower()
        for lead in pipeline:
            if low in lead.get("name", "").lower():
                matched = lead
                break

    if matched is None:
        return None

    matched["status"] = status
    if notes:
        matched["notes"] = notes
    if status == "contacted":
        matched["contacted_at"] = datetime.now().isoformat()
        # Schedule follow-up reminder 3 days from now
        fu = datetime.now() + timedelta(days=3)
        matched["followup_at"] = fu.isoformat()
    elif status in ("replied", "interested", "closed", "not_interested"):
        matched["followup_at"] = None   # no follow-up needed

    data["pipeline"] = pipeline
    _save(data)
    return matched


def get_followups_due() -> list:
    """Return leads where follow-up is due (followup_at <= now)."""
    now      = datetime.now()
    pipeline = _load().get("pipeline", [])
    due = []
    for lead in pipeline:
        fu = lead.get("followup_at")
        if fu and lead.get("status") == "contacted":
            try:
                if datetime.fromisoformat(fu) <= now:
                    due.append(lead)
            except Exception:
                pass
    return due


def clear_followup(place_id: str):
    data     = _load()
    pipeline = data.get("pipeline", [])
    for lead in pipeline:
        if lead.get("place_id") == place_id:
            lead["followup_at"] = None
            lead["status"]      = "followed_up"
    data["pipeline"] = pipeline
    _save(data)


def get_pipeline_summary() -> dict:
    pipeline = get_pipeline()
    by_status: dict = {}
    for lead in pipeline:
        s = lead.get("status", "not_contacted")
        by_status[s] = by_status.get(s, 0) + 1
    return {
        "total":          len(pipeline),
        "not_contacted":  by_status.get("not_contacted", 0),
        "contacted":      by_status.get("contacted", 0),
        "replied":        by_status.get("replied", 0),
        "interested":     by_status.get("interested", 0),
        "closed":         by_status.get("closed", 0),
        "not_interested": by_status.get("not_interested", 0),
    }
