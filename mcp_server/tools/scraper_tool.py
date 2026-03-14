"""GMB Scraper Tool — triggers Node.js scraper via Flask API."""
import requests

API = "http://localhost:5000"


def trigger_scraper(city: str, country: str, category: str, limit: int = 20) -> dict:
    """
    Start GMB scraper job. Returns job_id and status.
    Poll status with get_scraper_status(job_id).
    """
    try:
        resp = requests.post(f"{API}/api/gmb/start", json={
            "city": city,
            "country": country,
            "category": category,
            "limit": min(limit, 100)
        }, timeout=10)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_scraper_status(job_id: str, offset: int = 0) -> dict:
    """Poll scraper job status and retrieve new log lines + leads when done."""
    try:
        resp = requests.get(
            f"{API}/api/gmb/status/{job_id}",
            params={"offset": offset},
            timeout=10
        )
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def stop_scraper() -> dict:
    """Stop any running scraper job."""
    try:
        resp = requests.post(f"{API}/api/gmb/stop", timeout=10)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def import_leads(leads: list, service_needed: str = "Website Development") -> dict:
    """Import scraped leads into LeadPro database."""
    try:
        resp = requests.post(f"{API}/api/gmb/import", json={
            "leads": leads,
            "service_needed": service_needed
        }, timeout=15)
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}
