"""Inbox Tool — sync inbox, analyze reply intent, auto-respond via Flask API."""
import re
import requests

API = "http://localhost:5000"

# Simple intent classification keywords
_POSITIVE = ["interested", "yes", "sure", "please", "call", "when", "how much",
              "pricing", "price", "cost", "tell me more", "sounds good", "great",
              "let's do it", "schedule", "meeting", "demo", "forward"]
_NEGATIVE  = ["not interested", "unsubscribe", "remove", "stop", "no thanks",
              "don't contact", "do not contact", "opt out"]


def sync_inbox(limit: int = 30) -> dict:
    """Pull latest emails from IMAP inbox into the database."""
    try:
        resp = requests.post(f"{API}/api/inbox/sync",
                             json={"limit": limit}, timeout=30)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_messages() -> list:
    """Return all inbox messages stored in the database."""
    try:
        resp = requests.get(f"{API}/api/inbox/messages", timeout=10)
        return resp.json()
    except Exception as e:
        return []


def classify_intent(body_text: str) -> str:
    """
    Classify a reply as: 'interested' | 'not_interested' | 'question' | 'unknown'.
    """
    t = (body_text or "").lower()
    if any(k in t for k in _NEGATIVE):
        return "not_interested"
    if any(k in t for k in _POSITIVE):
        return "interested"
    if "?" in t:
        return "question"
    return "unknown"


def reply_to_message(msg_id: int, to_email: str, subject: str, body: str) -> dict:
    """Send a reply to an inbox message."""
    try:
        resp = requests.post(f"{API}/api/inbox/reply", json={
            "id": msg_id,
            "to_email": to_email,
            "subject": subject,
            "body": body
        }, timeout=15)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_unread_interested() -> list:
    """
    Return inbox messages classified as 'interested' that haven't been replied to.
    """
    messages = get_messages()
    result = []
    for m in messages:
        if m.get("replied"):
            continue
        intent = classify_intent(m.get("body_text", ""))
        if intent == "interested":
            result.append({**m, "intent": intent})
    return result


def get_questions() -> list:
    """Return unreplied messages that contain a question."""
    messages = get_messages()
    return [
        {**m, "intent": "question"}
        for m in messages
        if not m.get("replied") and classify_intent(m.get("body_text", "")) == "question"
    ]
