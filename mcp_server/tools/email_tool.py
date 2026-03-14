"""Email Campaign Tool — create campaigns and send emails via Flask API."""
import requests

API = "http://localhost:5000"


def get_campaigns() -> list:
    """Return all saved campaigns."""
    try:
        resp = requests.get(f"{API}/api/campaigns-list", timeout=10)
        return resp.json()
    except Exception as e:
        return []


def create_campaign(name: str, service: str, subject: str, body: str) -> dict:
    """Create a new email campaign. Returns campaign id."""
    try:
        resp = requests.post(f"{API}/api/campaigns/save", json={
            "name": name,
            "service": service,
            "subject": subject,
            "body": body
        }, timeout=10)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_campaign(lead_ids: list, campaign_id: int) -> dict:
    """
    Send a campaign to a list of lead IDs.
    lead_ids: list of integer lead IDs from the leads table.
    """
    try:
        resp = requests.post(f"{API}/api/send-emails", json={
            "lead_ids": lead_ids,
            "campaign_id": campaign_id
        }, timeout=10)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_send_status() -> dict:
    """Get real-time sending progress."""
    try:
        resp = requests.get(f"{API}/api/send-status", timeout=10)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def stop_sending() -> dict:
    """Stop the current sending run."""
    try:
        resp = requests.post(f"{API}/api/send-stop", timeout=10)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_leads(limit: int = 100) -> list:
    """Fetch leads from the database (max 500)."""
    try:
        resp = requests.get(f"{API}/api/leads", timeout=10)
        data = resp.json()
        return data[:limit]
    except Exception as e:
        return []


def get_email_templates() -> dict:
    """Return all built-in email templates."""
    try:
        resp = requests.get(f"{API}/api/templates", timeout=10)
        return resp.json()
    except Exception as e:
        return {}
