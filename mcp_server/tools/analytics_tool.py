"""Analytics Tool — lead scoring, SEO analysis summary, campaign stats."""
import sqlite3

DB_PATH = "c:/wamp64/www/LeadPro/data/leads.db"


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def score_lead(lead: dict) -> dict:
    """
    Score a single lead 0-100 based on available data quality.
    Returns lead dict with added 'score' and 'score_reasons' keys.
    """
    score = 0
    reasons = []

    if lead.get("email"):
        score += 25
        reasons.append("+25 has email")
    if lead.get("phone"):
        score += 15
        reasons.append("+15 has phone")
    if lead.get("business_name"):
        score += 10
        reasons.append("+10 has business name")
    if lead.get("location"):
        score += 5
        reasons.append("+5 has location")

    notes = (lead.get("notes") or "").lower()

    # SEO lead: website exists but poor SEO = highest value
    if "type: poor_seo" in notes:
        score += 30
        reasons.append("+30 poor SEO (high opportunity)")
        # Bonus for very low SEO score
        import re
        m = re.search(r"seo score: (\d+)", notes)
        if m and int(m.group(1)) < 40:
            score += 10
            reasons.append("+10 very low SEO score (<40)")
    elif "type: no_website" in notes:
        score += 20
        reasons.append("+20 no website (web dev opportunity)")

    # Rating bonus
    m = __import__("re").search(r"rating: ([\d.]+)", notes)
    if m:
        rating = float(m.group(1))
        if rating >= 4.0:
            score += 5
            reasons.append(f"+5 high rating ({rating})")

    return {**lead, "score": min(score, 100), "score_reasons": reasons}


def get_top_leads(limit: int = 20) -> list:
    """Return top-scored leads from the database."""
    conn = _db()
    c = conn.cursor()
    c.execute("""
        SELECT id, business_name, email, phone, website, location,
               service_needed, status, notes, added_on
        FROM leads
        WHERE status='new'
        ORDER BY added_on DESC
        LIMIT 500
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    scored = sorted([score_lead(r) for r in rows], key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def get_campaign_stats() -> list:
    """Return all campaigns with sent count and basic stats."""
    conn = _db()
    c = conn.cursor()
    c.execute("""
        SELECT ca.id, ca.name, ca.service, ca.sent_count, ca.created_on,
               COUNT(CASE WHEN el.status='sent' THEN 1 END) AS actual_sent,
               COUNT(CASE WHEN el.status='failed' THEN 1 END) AS failed
        FROM campaigns ca
        LEFT JOIN email_logs el ON el.campaign_id=ca.id
        GROUP BY ca.id
        ORDER BY ca.created_on DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_lead_summary() -> dict:
    """Return counts by status, source, and service."""
    conn = _db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM leads")
    total = c.fetchone()[0]

    c.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")
    by_status = dict(c.fetchall())

    c.execute("SELECT source, COUNT(*) FROM leads GROUP BY source ORDER BY COUNT(*) DESC LIMIT 10")
    by_source = dict(c.fetchall())

    c.execute("SELECT service_needed, COUNT(*) FROM leads GROUP BY service_needed ORDER BY COUNT(*) DESC LIMIT 10")
    by_service = dict(c.fetchall())

    c.execute("""
        SELECT COUNT(*) FROM leads
        WHERE notes LIKE '%type: poor_seo%'
    """)
    poor_seo = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM leads
        WHERE notes LIKE '%type: no_website%'
    """)
    no_website = c.fetchone()[0]

    conn.close()
    return {
        "total": total,
        "by_status": by_status,
        "by_source": by_source,
        "by_service": by_service,
        "poor_seo_leads": poor_seo,
        "no_website_leads": no_website
    }


def get_today_activity() -> dict:
    """Return today's email activity."""
    conn = _db()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM email_logs
        WHERE status='sent' AND date(sent_on)=date('now','localtime')
    """)
    sent_today = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM email_logs
        WHERE status='failed' AND date(sent_on)=date('now','localtime')
    """)
    failed_today = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM leads
        WHERE date(added_on)=date('now','localtime')
    """)
    new_leads_today = c.fetchone()[0]

    conn.close()
    return {
        "sent_today": sent_today,
        "failed_today": failed_today,
        "new_leads_today": new_leads_today
    }
