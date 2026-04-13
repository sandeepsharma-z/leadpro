from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
import sqlite3, smtplib, json, threading, time, os, random, re, io, csv
import subprocess, uuid
import glob as glob_module
import imaplib, email, webbrowser, requests
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import make_msgid, formatdate
import urllib.request as _urllib_request
from email.header import decode_header
from datetime import datetime
import logging
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    import docx
except Exception:
    docx = None

try:
    import openpyxl
except Exception:
    openpyxl = None

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
DB_PATH = "data/leads.db"
BRAND_ASSETS_DIR = "data/brand_assets"

# ─── DATABASE SETUP ────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_name TEXT,
        email TEXT UNIQUE,
        phone TEXT,
        website TEXT,
        location TEXT,
        service_needed TEXT,
        source TEXT,
        status TEXT DEFAULT 'new',
        notes TEXT,
        added_on TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        service TEXT,
        subject TEXT,
        body TEXT,
        sent_count INTEGER DEFAULT 0,
        created_on TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'draft'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS email_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        campaign_id INTEGER,
        email TEXT,
        status TEXT,
        sent_on TEXT DEFAULT CURRENT_TIMESTAMP,
        error TEXT,
        subject_sent TEXT,
        body_sent TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS inbox_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_uid TEXT UNIQUE,
        sender_name TEXT,
        sender_email TEXT,
        subject TEXT,
        body_text TEXT,
        received_on TEXT,
        lead_id INTEGER,
        replied INTEGER DEFAULT 0,
        source TEXT DEFAULT 'imap'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS social_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        author TEXT,
        subtitle TEXT,
        profile_url TEXT,
        post_text TEXT,
        post_url TEXT,
        email TEXT,
        phone TEXT,
        reply_draft TEXT,
        status TEXT DEFAULT 'new',
        found_on TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        company TEXT,
        phone TEXT,
        slot_datetime TEXT,
        message TEXT,
        status TEXT DEFAULT 'pending',
        created_on TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # default settings
    defaults = [
        ('smtp_host', 'smtp.hostinger.com'),
        ('smtp_port', '465'),
        ('smtp_user', ''),
        ('smtp_pass', ''),
        ('imap_host', 'imap.hostinger.com'),
        ('imap_port', '993'),
        ('logo_white_url', 'https://solvinex.com/uploads/footer-logo-white.png'),
        ('logo_color_url', 'https://solvinex.com/uploads/header-logo.png'),
        ('brand_primary', '#2563eb'),
        ('brand_secondary', '#0ea5e9'),
        ('brand_font', 'Inter'),
        ('sender_name', 'Your Agency'),
        ('daily_limit', '200'),
        ('delay_between', '3'),
        ('delay_jitter', '4'),
        ('auto_send_enabled', '0'),
        ('auto_campaign_id', ''),
        ('inbox_auto_sync', '0'),
        ('inbox_sync_minutes', '5'),
        ('opencrawl_enabled', '1'),
        ('opencrawl_auto_enabled', '0'),
        ('opencrawl_interval_minutes', '60'),
        ('opencrawl_locations', 'Delhi,Mumbai,Bangalore'),
        ('opencrawl_niches', 'restaurant,clinic,gym,hotel'),
        ('opencrawl_services', 'Website Development,SEO (Search Engine Optimization)'),
        ('opencrawl_pages_per_query', '1'),
        ('opencrawl_daily_new_leads_limit', '100'),
        ('opencrawl_auto_email', '1'),
        ('linkedin_li_at', ''),
        ('linkedin_email', ''),
        ('linkedin_password', ''),
        ('linkedin_auto_monitor', '0'),
        ('linkedin_monitor_interval', '30'),
        ('linkedin_comment_auto', '0'),
        ('linkedin_comment_template', 'Hi {name}! 👋 Noticed you might be looking for help with {service}. We have helped 50+ businesses grow online with professional website development, SEO & digital marketing. Would love to share a quick proposal — feel free to connect or drop your email! 🚀'),
        ('social_keywords', 'need website,looking for web developer,need SEO services,need digital marketing,website banana hai'),
        ('social_auto_save', '1'),
        ('social_default_service', 'Website Development'),
        ('booking_days_ahead', '14'),
        ('booking_start_hour', '9'),
        ('booking_end_hour', '18'),
        ('booking_slot_minutes', '60'),
        ('booking_title', 'Book a Free Discovery Call'),
        ('booking_subtitle', 'Pick a time that works for you — 15 minutes, no pressure.'),
        ('ig_sessionid', ''),
        ('ig_csrftoken', ''),
        ('ig_email', ''),
        ('ig_niche', ''),
        ('ig_message_template', 'Hi {name}! 👋\n\nI came across your profile and love what you\'re doing in the {niche} space!\n\nI noticed you don\'t have a website yet — that\'s actually a big opportunity. A professional website can bring you 3–5x more clients on autopilot through Google searches.\n\nWe build fast, stunning websites starting from just $299. The first consultation is 100% free — no pressure at all.\n\nWould you be open to a quick 10-minute call this week? 🚀'),
        ('ig_max_dms', '10'),
        ('ig_delay_seconds', '35'),
    ]
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
    # Auto-fix old broken Solvinex logo defaults from previous builds.
    c.execute("UPDATE settings SET value=? WHERE key='logo_white_url' AND value='https://solvinex.com/assets/logo-white.png'",
              ('https://solvinex.com/uploads/footer-logo-white.png',))
    c.execute("UPDATE settings SET value=? WHERE key='logo_color_url' AND value='https://solvinex.com/assets/logo-color.png'",
              ('https://solvinex.com/uploads/header-logo.png',))
    # Safe migrations for older DBs
    try:
        c.execute("ALTER TABLE email_logs ADD COLUMN subject_sent TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE email_logs ADD COLUMN body_sent TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE social_leads ADD COLUMN reply_draft TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE social_leads ADD COLUMN post_urn TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE social_leads ADD COLUMN commented INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_social_unique
                     ON social_leads(platform, author, post_url, post_text)""")
    except Exception:
        pass
    # Campaign cold outreach columns
    for col_sql in [
        "ALTER TABLE campaigns ADD COLUMN template_type VARCHAR(50) DEFAULT 'html'",
        "ALTER TABLE campaigns ADD COLUMN template_name VARCHAR(100) DEFAULT ''",
        "ALTER TABLE campaigns ADD COLUMN followup_days INTEGER DEFAULT 0",
        "ALTER TABLE campaigns ADD COLUMN personalization_json TEXT DEFAULT '{}'",
    ]:
        try:
            c.execute(col_sql)
        except Exception:
            pass
    # Cold email plain-text templates table
    c.execute('''CREATE TABLE IF NOT EXISTS email_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        display_name TEXT,
        template_type TEXT DEFAULT 'plain_text',
        subject TEXT,
        body TEXT,
        created_on TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # Seed 6 cold outreach templates (INSERT OR IGNORE = never overwrite user edits)
    cold_templates = [
        ('cold_no_website', 'No Website (Direct)', 'plain_text',
         'Quick question about {{business_name}}',
         "Hi,\n\nSaw {{business_name}} on Google Maps - love the reviews!\n\nBut noticed you don't have a website yet. That's costing you customers who search online before visiting.\n\nWe build simple, affordable websites for local {{industry}} businesses in {{location}}.\n\nWant a free mockup of what your site could look like?\n\nJust reply \"YES\" and I'll send it over.\n\nCheers,\n{{sender_name}}\nSolvinex"),
        ('cold_competitor', 'Competitor Angle', 'plain_text',
         'Your competitor just got ahead',
         "Hi,\n\nQuick heads up - another {{industry}} in {{location}} just launched their website.\n\nThey're now showing up higher on Google when people search for \"{{industry}} near me.\"\n\nWant to catch up? We can get you online in 7 days.\n\nReply for free quote.\n\n{{sender_name}}\nSolvinex"),
        ('cold_free_audit', 'Free Audit Offer', 'plain_text',
         'Free website audit for {{business_name}}',
         "Hi,\n\nI help {{industry}} businesses in {{location}} get more customers online.\n\nCan I send you a quick (free) audit showing:\n✓ How you rank vs competitors\n✓ What's missing from your online presence\n✓ 3 quick wins to get more walk-ins\n\nTakes 2 minutes. Interested?\n\n{{sender_name}}\nSolvinex"),
        ('cold_social_proof', 'Social Proof / Case Study', 'plain_text',
         'Case study: {{industry}} got 40% more customers',
         "Hi,\n\nLast month we built a website for a {{industry}} in {{location}}.\n\nResult: 40% increase in phone calls + bookings in first 30 days.\n\nWould similar results interest you for {{business_name}}?\n\nReply \"DETAILS\" to see the case study.\n\n{{sender_name}}\nSolvinex"),
        ('cold_limited_offer', 'Limited Offer', 'plain_text',
         'Special offer for {{location}} businesses',
         "Hi {{business_name}},\n\nRunning a promotion this month for {{location}} {{industry}} businesses:\n✓ Professional website - 50% off\n✓ Free mobile optimization\n✓ 3 months free support\n\nOnly 3 spots left this month.\n\nInterested? Reply FAST.\n\n{{sender_name}}\nSolvinex"),
        ('cold_followup', 'Follow-up', 'plain_text',
         'Re: {{business_name}} website',
         "Hi,\n\nFollowing up on my email from {{days_ago}} days ago.\n\nStill happy to send that free website mockup if you're interested.\n\nNo pressure - just reply \"YES\" or \"NOT NOW\" so I know.\n\nThanks!\n{{sender_name}}\nSolvinex"),
    ]
    for name, display, ttype, subj, body in cold_templates:
        c.execute('''INSERT OR IGNORE INTO email_templates
            (name, display_name, template_type, subject, body)
            VALUES (?,?,?,?,?)''', (name, display, ttype, subj, body))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def get_all_settings():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    rows = c.fetchall()
    conn.close()
    return {k: v for k, v in rows}

def _safe_int(value, default):
    try:
        return int(value)
    except Exception:
        return default

def _safe_float(value, default):
    try:
        return float(value)
    except Exception:
        return default

def _normalize_email(value):
    raw = (value or '').strip().lower()
    if not raw:
        return None
    # Accept common scraped formats: "mailto:x@y.com", "<x@y.com>", "x@y.com;"
    raw = re.sub(r'^mailto:\s*', '', raw)
    m = re.search(r'([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', raw)
    if not m:
        return None
    e = m.group(1).strip().strip('.,;:!?)(')
    if re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', e):
        return e
    return None

def _get_today_sent_count(conn=None):
    local_conn = conn is None
    if local_conn:
        conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM email_logs WHERE status='sent' AND date(sent_on)=date('now','localtime')")
    count = c.fetchone()[0]
    if local_conn:
        conn.close()
    return count

def _personalize_text(text, biz_name, service, sender_name, extra=None):
    s = get_all_settings()
    brand_font = s.get('brand_font', 'Inter')
    brand_font_google = quote_plus(brand_font).replace('%20', '+')
    sender_email = s.get('smtp_user', '') or s.get('smtp_username', '')
    ex = extra or {}
    result = (text or '') \
        .replace('{business}', biz_name or '') \
        .replace('{service}', service or '') \
        .replace('{industry}', ex.get('industry', service.split(',')[0].strip() if service else '') or '') \
        .replace('{review_count}', ex.get('review_count', '') or '') \
        .replace('{sender_name}', sender_name or '') \
        .replace('{sender_email}', sender_email) \
        .replace('{logo_white_url}', s.get('logo_white_url', 'https://solvinex.com/uploads/footer-logo-white.png')) \
        .replace('{logo_color_url}', s.get('logo_color_url', 'https://solvinex.com/uploads/header-logo.png')) \
        .replace('{brand_primary}', s.get('brand_primary', '#2563eb')) \
        .replace('{brand_secondary}', s.get('brand_secondary', '#0ea5e9')) \
        .replace('{brand_font}', brand_font) \
        .replace('{brand_font_google}', brand_font_google)
    # Also handle {{double_brace}} style (plain text templates)
    result = result \
        .replace('{{business_name}}', biz_name or '') \
        .replace('{{location}}', ex.get('location', '') or '') \
        .replace('{{industry}}', ex.get('industry', service.split(',')[0].strip() if service else '') or '') \
        .replace('{{sender_name}}', sender_name or '') \
        .replace('{{days_ago}}', ex.get('days_ago', '3') or '3')
    return result

def _append_social_links_footer(body_html):
    body = body_html or ''

    def _normalize_social_anchor_labels(html):
        out = html or ''
        canonical = [
            (
                r'https?://(?:www\.)?instagram\.com/solvinex_com/?',
                "<a href=\"https://www.instagram.com/solvinex_com/\" style=\"display:inline-block;padding:6px 12px;border:1px solid #bfdbfe;border-radius:999px;color:#1d4ed8;text-decoration:none;margin:0 6px 8px 0;font-weight:600;font-size:12px;\">Instagram</a>",
            ),
            (
                r'https?://(?:www\.)?x\.com/solvinex_com/?',
                "<a href=\"https://x.com/solvinex_com\" style=\"display:inline-block;padding:6px 12px;border:1px solid #bfdbfe;border-radius:999px;color:#1d4ed8;text-decoration:none;margin:0 6px 8px 0;font-weight:600;font-size:12px;\">X</a>",
            ),
            (
                r'https?://(?:www\.)?linkedin\.com/company/solvinex/?',
                "<a href=\"https://www.linkedin.com/company/solvinex\" style=\"display:inline-block;padding:6px 12px;border:1px solid #bfdbfe;border-radius:999px;color:#1d4ed8;text-decoration:none;margin:0 6px 8px 0;font-weight:600;font-size:12px;\">LinkedIn</a>",
            ),
            (
                r'https?://(?:www\.)?facebook\.com/solvinex/?',
                "<a href=\"https://www.facebook.com/solvinex/\" style=\"display:inline-block;padding:6px 12px;border:1px solid #bfdbfe;border-radius:999px;color:#1d4ed8;text-decoration:none;margin:0 6px 8px 0;font-weight:600;font-size:12px;\">Facebook</a>",
            ),
        ]
        for href_rx, anchor_html in canonical:
            out = re.sub(
                rf"<a\b[^>]*href=[\"']{href_rx}[\"'][^>]*>.*?</a>",
                anchor_html,
                out,
                flags=re.IGNORECASE | re.DOTALL,
            )
        return out

    body = _normalize_social_anchor_labels(body)
    social_urls = [
        'https://www.instagram.com/solvinex_com/',
        'https://x.com/solvinex_com',
        'https://www.linkedin.com/company/solvinex',
        'https://www.facebook.com/solvinex/',
    ]
    if any(u in body for u in social_urls):
        return body

    footer_block = (
        "<div style=\"margin-top:22px;padding-top:14px;border-top:1px solid #e5e7eb;"
        "font-family:Arial,sans-serif;font-size:13px;color:#64748b\">"
        "<div style=\"margin-bottom:6px;\"><strong style=\"color:#334155;\">Follow Solvinex:</strong></div>"
        "<div>"
        "<a href=\"https://www.instagram.com/solvinex_com/\" style=\"display:inline-block;padding:6px 12px;border:1px solid #bfdbfe;border-radius:999px;color:#1d4ed8;text-decoration:none;margin:0 6px 8px 0;font-weight:600;font-size:12px;\">Instagram</a>"
        "<a href=\"https://x.com/solvinex_com\" style=\"display:inline-block;padding:6px 12px;border:1px solid #bfdbfe;border-radius:999px;color:#1d4ed8;text-decoration:none;margin:0 6px 8px 0;font-weight:600;font-size:12px;\">X</a>"
        "<a href=\"https://www.linkedin.com/company/solvinex\" style=\"display:inline-block;padding:6px 12px;border:1px solid #bfdbfe;border-radius:999px;color:#1d4ed8;text-decoration:none;margin:0 6px 8px 0;font-weight:600;font-size:12px;\">LinkedIn</a>"
        "<a href=\"https://www.facebook.com/solvinex/\" style=\"display:inline-block;padding:6px 12px;border:1px solid #bfdbfe;border-radius:999px;color:#1d4ed8;text-decoration:none;margin:0 6px 8px 0;font-weight:600;font-size:12px;\">Facebook</a>"
        "</div>"
        "</div>"
    )
    if '</body>' in body.lower():
        idx = body.lower().rfind('</body>')
        return body[:idx] + footer_block + body[idx:]
    return body + footer_block

def _human_delay(settings):
    base = max(1.0, _safe_float(settings.get('delay_between', 3), 3.0))
    jitter = max(0.0, _safe_float(settings.get('delay_jitter', 4), 4.0))
    return base + random.uniform(0, jitter)

def _read_file_text(file_storage):
    filename = (file_storage.filename or '').lower()
    raw = file_storage.read()
    if filename.endswith(('.txt', '.log')):
        return raw.decode('utf-8', errors='ignore')
    if filename.endswith('.csv'):
        return raw.decode('utf-8', errors='ignore')
    if filename.endswith('.pdf'):
        if not PdfReader:
            raise ValueError("PDF support missing. Install pypdf.")
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join([(p.extract_text() or '') for p in reader.pages])
    if filename.endswith('.docx'):
        if not docx:
            raise ValueError("DOCX support missing. Install python-docx.")
        d = docx.Document(io.BytesIO(raw))
        return "\n".join([p.text for p in d.paragraphs])
    if filename.endswith(('.xlsx', '.xlsm')):
        if not openpyxl:
            raise ValueError("XLSX support missing. Install openpyxl.")
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        chunks = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                line = ", ".join([str(v).strip() for v in row if v is not None and str(v).strip()])
                if line:
                    chunks.append(line)
        return "\n".join(chunks)
    raise ValueError("Unsupported file type. Use txt/csv/pdf/docx/xlsx.")

def _extract_contacts(text):
    email_re = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    contacts = []
    seen = set()
    for line in text.splitlines():
        emails = email_re.findall(line)
        if not emails:
            continue
        for email in emails:
            e = email.lower().strip()
            if e in seen:
                continue
            seen.add(e)
            cleaned = line.replace(email, ' ')
            parts = [p.strip() for p in re.split(r'[,;|\t]', cleaned) if p.strip()]
            name = ''
            for part in parts:
                if '@' in part or 'http' in part.lower():
                    continue
                if 2 <= len(part) <= 80:
                    name = part
                    break
            if not name:
                name = e.split('@')[0].replace('.', ' ').replace('_', ' ').title()
            contacts.append({'name': name[:80], 'email': e})
    return contacts

def _decode_mime(value):
    if not value:
        return ''
    parts = decode_header(value)
    out = []
    for txt, enc in parts:
        if isinstance(txt, bytes):
            out.append(txt.decode(enc or 'utf-8', errors='ignore'))
        else:
            out.append(str(txt))
    return ''.join(out)

def _parse_email_message(msg):
    subject = _decode_mime(msg.get('Subject', ''))
    from_raw = _decode_mime(msg.get('From', ''))
    sender_email = ''
    m = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', from_raw)
    if m:
        sender_email = m.group(0).lower()
    sender_name = from_raw.replace(f"<{sender_email}>", '').strip().strip('"') if sender_email else from_raw
    body_text = ''
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition", ""))
            if ctype in ('text/plain', 'text/html') and 'attachment' not in cdisp:
                payload = part.get_payload(decode=True) or b''
                text = payload.decode(part.get_content_charset() or 'utf-8', errors='ignore')
                if ctype == 'text/html':
                    text = BeautifulSoup(text, 'lxml').get_text(" ", strip=True)
                body_text += "\n" + text
    else:
        payload = msg.get_payload(decode=True) or b''
        body_text = payload.decode(msg.get_content_charset() or 'utf-8', errors='ignore')
    return {
        'subject': subject[:300],
        'sender_name': (sender_name or '').strip()[:120],
        'sender_email': sender_email[:200],
        'body_text': (body_text or '').strip()[:5000],
        'received_on': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def _upsert_lead_from_inbox(conn, sender_name, sender_email):
    if not sender_email:
        return None
    c = conn.cursor()
    c.execute("SELECT id FROM leads WHERE email=?", (sender_email,))
    row = c.fetchone()
    if row:
        return row[0]
    c.execute('''INSERT OR IGNORE INTO leads
        (business_name, email, source, notes, status)
        VALUES (?,?,?,?,?)''',
        (sender_name or sender_email.split('@')[0], sender_email, 'inbox-reply', 'Imported from inbox', 'interested'))
    return c.lastrowid if c.lastrowid else None

def sync_inbox_messages(limit=30):
    s = get_all_settings()
    host = s.get('imap_host', 'imap.hostinger.com').strip()
    port = _safe_int(s.get('imap_port', '993'), 993)
    user = s.get('smtp_user', '').strip()
    password = s.get('smtp_pass', '').strip()
    if not host or not user or not password:
        raise ValueError("Configure IMAP host and SMTP credentials first")

    mail = imaplib.IMAP4_SSL(host, port)
    mail.login(user, password)
    mail.select('INBOX')
    typ, data = mail.uid('search', None, 'ALL')
    if typ != 'OK':
        mail.logout()
        return {'fetched': 0, 'inserted': 0}
    uids = (data[0] or b'').split()
    uids = uids[-max(1, limit):]

    fetched, inserted = 0, 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for uid in uids:
        uid_str = uid.decode(errors='ignore')
        c.execute("SELECT id FROM inbox_messages WHERE msg_uid=?", (uid_str,))
        if c.fetchone():
            continue
        typ2, msg_data = mail.uid('fetch', uid, '(RFC822)')
        if typ2 != 'OK' or not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        parsed = _parse_email_message(msg)
        if not parsed['sender_email']:
            continue
        lead_id = _upsert_lead_from_inbox(conn, parsed['sender_name'], parsed['sender_email'])
        c.execute('''INSERT OR IGNORE INTO inbox_messages
            (msg_uid, sender_name, sender_email, subject, body_text, received_on, lead_id)
            VALUES (?,?,?,?,?,?,?)''',
            (uid_str, parsed['sender_name'], parsed['sender_email'], parsed['subject'],
             parsed['body_text'], parsed['received_on'], lead_id))
        fetched += 1
        if c.rowcount:
            inserted += 1
    conn.commit()
    conn.close()
    mail.logout()
    return {'fetched': fetched, 'inserted': inserted}

def _extract_phone_any(text):
    m = re.search(r'(?:\+?\d[\d\-\s]{7,}\d)', text or '')
    return m.group(0).strip() if m else ''

def crawl_site_for_leads(url, service_needed='', location=''):
    resp = requests.get(url, timeout=12, headers={'User-Agent': 'Mozilla/5.0'})
    html = resp.text
    soup = BeautifulSoup(html, 'lxml')
    text = soup.get_text(" ", strip=True)
    emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)))
    phone = _extract_phone_any(text)
    business = (soup.title.get_text(strip=True) if soup.title else '')[:120] or url
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    inserted = 0
    for em in emails[:25]:
        c.execute('''INSERT OR IGNORE INTO leads
            (business_name, email, phone, website, location, service_needed, source, notes)
            VALUES (?,?,?,?,?,?,?,?)''',
            (business, em.lower(), phone, url, location, service_needed, 'opencrawl-local', 'Imported from website crawl'))
        if c.rowcount:
            inserted += 1
    conn.commit()
    conn.close()
    return {'url': url, 'found': len(emails), 'inserted': inserted}

def _detect_service_need(text, allowed_services):
    t = (text or '').lower()
    rules = [
        ('Website Development', ['website', 'web design', 'web development', 'site redesign']),
        ('SEO (Search Engine Optimization)', ['seo', 'google ranking', 'search engine', 'organic traffic']),
        ('Logo Design', ['logo', 'brand identity']),
        ('Social Media Management', ['social media', 'instagram', 'facebook marketing']),
        ('App Development', ['mobile app', 'android app', 'ios app']),
        ('E-commerce Solutions', ['ecommerce', 'online store', 'shopify', 'woocommerce']),
        ('UI/UX Design', ['ui/ux', 'ux design', 'user experience']),
        ('Branding & Graphic Design', ['branding', 'graphic design']),
        ('CMS Development', ['wordpress', 'cms']),
        ('Website Maintenance', ['website maintenance', 'site maintenance', 'security updates']),
    ]
    allowed = set([x.strip() for x in allowed_services if x.strip()])
    for service, keys in rules:
        if allowed and service not in allowed:
            continue
        if any(k in t for k in keys):
            return service
    if allowed:
        return list(allowed)[0]
    return 'Website Development'

def _search_duckduckgo_urls(query, pages=1):
    urls = []
    for p in range(max(1, pages)):
        start = p * 30
        u = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&s={start}"
        r = requests.get(u, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(r.text, 'lxml')
        for a in soup.select('a.result__a'):
            href = a.get('href', '').strip()
            if not href:
                continue
            # DuckDuckGo redirect URL -> real URL in uddg param
            if 'duckduckgo.com/l/?' in href and 'uddg=' in href:
                q = parse_qs(urlparse(href).query)
                href = unquote((q.get('uddg', [''])[0] or '').strip())
            if not href.startswith('http'):
                continue
            dom = urlparse(href).netloc.lower()
            if any(x in dom for x in ['google.', 'facebook.', 'instagram.', 'linkedin.', 'youtube.', 'twitter.', 'wikipedia.']):
                continue
            urls.append(href)
        time.sleep(1.2)
    # stable unique
    out, seen = [], set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:80]

def _find_campaign_id_for_service(conn, service_name):
    c = conn.cursor()
    c.execute("SELECT id, service FROM campaigns ORDER BY created_on DESC")
    rows = c.fetchall()
    target = (service_name or '').lower().strip()
    for cid, s in rows:
        services = [x.strip().lower() for x in (s or '').split(',') if x.strip()]
        if target and target in services:
            return cid
    return None

def _get_today_opencrawl_new_count(conn=None):
    local = conn is None
    if local:
        conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM leads WHERE source='opencrawl-local' AND date(added_on)=date('now','localtime')")
    n = c.fetchone()[0]
    if local:
        conn.close()
    return n

def run_opencrawl_cycle(max_runtime_sec=900):
    settings = get_all_settings()
    locations = [x.strip() for x in settings.get('opencrawl_locations', '').split(',') if x.strip()]
    niches = [x.strip() for x in settings.get('opencrawl_niches', '').split(',') if x.strip()]
    service_pool = [x.strip() for x in settings.get('opencrawl_services', '').split(',') if x.strip()]
    pages = max(1, min(3, _safe_int(settings.get('opencrawl_pages_per_query', '1'), 1)))
    daily_new_limit = max(1, _safe_int(settings.get('opencrawl_daily_new_leads_limit', '100'), 100))
    auto_email = settings.get('opencrawl_auto_email', '1') == '1'

    if not locations or not niches:
        return {'found': 0, 'inserted': 0, 'emailed': 0}

    found_total, inserted_total, emailed_total = 0, 0, 0
    errors = []
    started = time.time()
    limited_locations = locations[:15]
    limited_niches = niches[:20]
    opencrawl_status['queries_total'] = len(limited_locations) * len(limited_niches)
    opencrawl_status['queries_done'] = 0
    opencrawl_status['current_query'] = ''
    conn = sqlite3.connect(DB_PATH)
    for loc in limited_locations:
        for niche in limited_niches:
            if opencrawl_status.get('stop_requested'):
                conn.close()
                return {
                    'found': found_total,
                    'inserted': inserted_total,
                    'emailed': emailed_total,
                    'errors': len(errors),
                    'last_error': errors[-1] if errors else '',
                    'note': 'stopped by user'
                }
            if time.time() - started > max_runtime_sec:
                conn.close()
                return {
                    'found': found_total,
                    'inserted': inserted_total,
                    'emailed': emailed_total,
                    'errors': len(errors),
                    'last_error': errors[-1] if errors else '',
                    'note': f'timeout after {max_runtime_sec}s'
                }
            if _get_today_opencrawl_new_count(conn) >= daily_new_limit:
                conn.close()
                return {
                    'found': found_total,
                    'inserted': inserted_total,
                    'emailed': emailed_total,
                    'errors': len(errors),
                    'last_error': errors[-1] if errors else '',
                    'note': 'daily new lead limit reached'
                }
            query = f"{niche} {loc} contact email website"
            opencrawl_status['current_query'] = query
            opencrawl_status['queries_done'] = opencrawl_status.get('queries_done', 0) + 1
            try:
                urls = _search_duckduckgo_urls(query, pages=pages)
            except Exception as e:
                errors.append(f"{query}: {e}")
                continue
            for u in urls[:40]:
                try:
                    r = requests.get(u, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                    soup = BeautifulSoup(r.text, 'lxml')
                    text = soup.get_text(" ", strip=True)
                    service_need = _detect_service_need(text, service_pool)
                    result = crawl_site_for_leads(u, service_need, loc)
                    found_total += result.get('found', 0)
                    inserted_total += result.get('inserted', 0)
                    if result.get('inserted', 0) and auto_email:
                        c = conn.cursor()
                        campaign_id = _find_campaign_id_for_service(conn, service_need)
                        if campaign_id and not sending_status.get('running'):
                            c.execute("""SELECT id FROM leads
                                WHERE source='opencrawl-local' AND status='new' AND service_needed=?
                                ORDER BY added_on DESC LIMIT ?""", (service_need, min(5, result.get('inserted', 0))))
                            ids = [x[0] for x in c.fetchall()]
                            if ids:
                                _send_emails_worker(ids, campaign_id, 'auto-crawl')
                                emailed_total += len(ids)
                except Exception as e:
                    errors.append(f"{u}: {e}")
                    continue
    conn.close()
    return {
        'found': found_total,
        'inserted': inserted_total,
        'emailed': emailed_total,
        'errors': len(errors),
        'last_error': errors[-1] if errors else ''
    }

# ─── ROUTES ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM leads")
    total_leads = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE status='emailed'")
    emailed = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE status='new'")
    new_leads = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM email_logs WHERE status='sent'")
    total_sent = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM campaigns")
    campaigns = c.fetchone()[0]
    conn.close()
    return render_template('index.html',
        total_leads=total_leads, emailed=emailed,
        new_leads=new_leads, total_sent=total_sent, campaigns=campaigns)

@app.route('/leads')
def leads():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    service_filter = request.args.get('service', '')
    status_filter = request.args.get('status', '')
    query = "SELECT * FROM leads WHERE 1=1"
    params = []
    if service_filter:
        query += " AND service_needed=?"
        params.append(service_filter)
    if status_filter:
        query += " AND status=?"
        params.append(status_filter)
    query += " ORDER BY added_on DESC"
    c.execute(query, params)
    leads_data = c.fetchall()
    conn.close()
    source_filter = request.args.get('source', '')
    page_mode = request.args.get('mode', 'all')
    return render_template('leads.html', leads=leads_data,
        service_filter=service_filter, status_filter=status_filter,
        source_filter=source_filter, page_mode=page_mode)

@app.route('/cold-leads')
def cold_leads():
    return redirect(url_for('leads', source='gmb-scraper', mode='cold'))

@app.route('/api/leads', methods=['GET'])
def api_leads():
    source_filter = (request.args.get('source') or '').strip()
    service_filter = (request.args.get('service') or '').strip()
    status_filter = (request.args.get('status') or '').strip()
    limit = max(1, min(_safe_int(request.args.get('limit', 500), 500), 2000))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = """SELECT id, business_name, email, phone, website, location,
                      service_needed, source, status, added_on
               FROM leads WHERE 1=1"""
    params = []
    if source_filter:
        query += " AND source=?"
        params.append(source_filter)
    else:
        # Default All Leads view: show only contactable leads with email.
        query += " AND email IS NOT NULL AND TRIM(email)<>''"
    if service_filter:
        query += " AND service_needed=?"
        params.append(service_filter)
    if status_filter:
        query += " AND status=?"
        params.append(status_filter)
    query += " ORDER BY added_on DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        'id': r[0], 'business_name': r[1], 'email': r[2],
        'phone': r[3], 'website': r[4], 'location': r[5],
        'service_needed': r[6], 'source': r[7], 'status': r[8], 'added_on': r[9]
    } for r in rows])

@app.route('/api/leads/add', methods=['POST'])
def add_lead():
    data = request.json
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        email_v = _normalize_email(data.get('email', ''))
        c.execute('''INSERT OR IGNORE INTO leads
            (business_name, email, phone, website, location, service_needed, source, notes)
            VALUES (?,?,?,?,?,?,?,?)''',
            (data.get('business_name',''), email_v,
             data.get('phone',''), data.get('website',''),
             data.get('location',''), data.get('service_needed',''),
             data.get('source','manual'), data.get('notes','')))
        conn.commit()
        affected = c.rowcount
        conn.close()
        return jsonify({'success': True, 'inserted': affected})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/leads/bulk-add', methods=['POST'])
def bulk_add_leads():
    leads_list = request.json.get('leads', [])
    inserted = 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for lead in leads_list:
        try:
            email_v = _normalize_email(lead.get('email',''))
            if not email_v:
                continue
            c.execute('''INSERT OR IGNORE INTO leads
                (business_name, email, phone, website, location, service_needed, source)
                VALUES (?,?,?,?,?,?,?)''',
                (lead.get('business_name',''), email_v,
                 lead.get('phone',''), lead.get('website',''),
                 lead.get('location',''), lead.get('service_needed',''),
                 lead.get('source','import')))
            if c.rowcount: inserted += 1
        except: pass
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'inserted': inserted})

@app.route('/api/leads/upload-doc', methods=['POST'])
def upload_doc():
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'Please choose a document'}), 400
    service_needed = request.form.get('service_needed', '').strip()
    location = request.form.get('location', '').strip()
    try:
        text = _read_file_text(f)
        contacts = _extract_contacts(text)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not contacts:
        return jsonify({'success': False, 'error': 'No emails found in file'}), 400

    inserted = 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for contact in contacts:
        try:
            c.execute('''INSERT OR IGNORE INTO leads
                (business_name, email, location, service_needed, source, notes)
                VALUES (?,?,?,?,?,?)''',
                (contact['name'], contact['email'], location, service_needed, 'doc-upload', f.filename))
            if c.rowcount:
                inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({
        'success': True,
        'found': len(contacts),
        'inserted': inserted,
        'duplicates': len(contacts) - inserted
    })

@app.route('/api/leads/delete/<int:lead_id>', methods=['DELETE'])
def delete_lead(lead_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/leads/update-status', methods=['POST'])
def update_status():
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE leads SET status=? WHERE id IN ({})".format(
        ','.join('?' * len(data['ids']))),
        [data['status']] + data['ids'])
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ─── CAMPAIGNS ─────────────────────────────────────────────────────────────────
@app.route('/campaigns')
def campaigns():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM campaigns ORDER BY created_on DESC")
    camps = c.fetchall()
    conn.close()
    return render_template('campaigns.html', campaigns=camps, settings=get_all_settings())

@app.route('/api/campaigns/save', methods=['POST'])
def save_campaign():
    data = request.json
    ttype   = data.get('template_type', 'html')
    tname   = data.get('template_name', '')
    fdays   = int(data.get('followup_days', 0))
    pjson   = json.dumps(data.get('personalization', {}))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if data.get('id'):
        c.execute("""UPDATE campaigns
                     SET name=?, service=?, subject=?, body=?,
                         template_type=?, template_name=?, followup_days=?, personalization_json=?
                     WHERE id=?""",
            (data['name'], data['service'], data['subject'], data['body'],
             ttype, tname, fdays, pjson, data['id']))
    else:
        c.execute("""INSERT INTO campaigns
            (name, service, subject, body, template_type, template_name, followup_days, personalization_json)
            VALUES (?,?,?,?,?,?,?,?)""",
            (data['name'], data['service'], data['subject'], data['body'],
             ttype, tname, fdays, pjson))
        data['id'] = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': data['id']})

@app.route('/api/email-templates')
def get_email_templates():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM email_templates ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/email-templates/<name>')
def get_email_template(name):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM email_templates WHERE name=?", (name,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(row))

@app.route('/api/email-templates/save', methods=['POST'])
def save_email_template():
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT OR REPLACE INTO email_templates
        (name, display_name, template_type, subject, body) VALUES (?,?,?,?,?)""",
        (data['name'], data.get('display_name',''), data.get('template_type','plain_text'),
         data['subject'], data['body']))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/campaigns/delete/<int:cid>', methods=['DELETE'])
def delete_campaign(cid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM campaigns WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    # If a send is running for this campaign, stop it immediately.
    if sending_status.get('running') and sending_status.get('campaign_id') == cid:
        sending_status['running'] = False
        sending_status['current'] = 'Stopped (campaign deleted)'
    return jsonify({'success': True})

# ─── EMAIL SENDING ──────────────────────────────────────────────────────────────
sending_status = {'running': False, 'total': 0, 'sent': 0, 'failed': 0, 'current': '', 'mode': 'manual', 'campaign_id': None}
auto_sender_status = {'enabled': False, 'last_run': '', 'last_error': '', 'last_batch': 0}
opencrawl_status = {
    'enabled': False,
    'running': False,
    'stop_requested': False,
    'last_run': '',
    'last_error': '',
    'last_found': 0,
    'last_inserted': 0,
    'last_errors_count': 0,
    'last_trigger': '',
    'started_on': '',
    'current_query': '',
    'queries_total': 0,
    'queries_done': 0
}

@app.route('/api/send-emails', methods=['POST'])
def send_emails():
    global sending_status
    if sending_status['running']:
        return jsonify({'success': False, 'error': 'Already running!'})
    data = request.json
    lead_ids = data.get('lead_ids', [])
    campaign_id = data.get('campaign_id')
    if not lead_ids or not campaign_id:
        return jsonify({'success': False, 'error': 'Select leads and campaign'})
    thread = threading.Thread(target=_send_emails_worker, args=(lead_ids, campaign_id, 'manual'))
    thread.daemon = True
    thread.start()
    return jsonify({'success': True, 'message': f'Sending to {len(lead_ids)} leads...'})

def _send_emails_worker(lead_ids, campaign_id, mode='manual'):
    global sending_status
    sending_status = {
        'running': True,
        'total': len(lead_ids),
        'sent': 0,
        'failed': 0,
        'current': '',
        'mode': mode,
        'campaign_id': campaign_id
    }
    s = get_all_settings()
    daily_limit = max(1, _safe_int(s.get('daily_limit', '200'), 200))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT subject, body, service FROM campaigns WHERE id=?", (campaign_id,))
    camp = c.fetchone()
    if not camp:
        sending_status['running'] = False
        conn.close()
        return
    subject_tmpl, body_tmpl, campaign_service = camp
    # Manual send should allow re-sending to explicitly selected leads.
    # Auto modes remain resume-safe to avoid repeated sends.
    eligible_ids = []
    for lid in lead_ids:
        if mode == 'manual':
            c.execute("SELECT id FROM leads WHERE id=? AND email IS NOT NULL AND TRIM(email)<>''", (lid,))
        else:
            c.execute('''SELECT l.id
                FROM leads l
                LEFT JOIN email_logs el
                  ON el.lead_id=l.id AND el.campaign_id=? AND el.status='sent'
                WHERE l.id=? AND l.status!='emailed' AND el.id IS NULL
                  AND l.email IS NOT NULL AND TRIM(l.email)<>''',
                (campaign_id, lid))
        if c.fetchone():
            eligible_ids.append(lid)
    sending_status['total'] = len(eligible_ids)
    if not eligible_ids:
        sending_status['running'] = False
        sending_status['current'] = 'No pending leads to send'
        conn.close()
        return

    sent_today = _get_today_sent_count(conn)
    for lid in eligible_ids:
        if not sending_status.get('running', False):
            sending_status['current'] = 'Stopped'
            break
        # Stop if campaign was deleted mid-send.
        c.execute("SELECT 1 FROM campaigns WHERE id=?", (campaign_id,))
        if not c.fetchone():
            sending_status['current'] = 'Stopped (campaign deleted)'
            break
        if sent_today >= daily_limit:
            sending_status['current'] = f'Daily limit reached ({daily_limit})'
            break
        c.execute("SELECT email, business_name, service_needed FROM leads WHERE id=?", (lid,))
        lead = c.fetchone()
        if not lead:
            continue
        email, biz_name, service = lead
        if not email or not str(email).strip():
            sending_status['failed'] += 1
            continue
        service_final = (campaign_service or '').strip() or (service or '').strip()
        sending_status['current'] = email
        subject = _personalize_text(subject_tmpl, biz_name, service_final, s.get('sender_name', ''))
        body = _append_social_links_footer(_personalize_text(body_tmpl, biz_name, service_final, s.get('sender_name', '')))
        try:
            _send_one_email(s, email, subject, body, s.get('sender_name',''))
            c.execute("UPDATE leads SET status='emailed' WHERE id=?", (lid,))
            c.execute("""INSERT INTO email_logs
                (lead_id, campaign_id, email, status, subject_sent, body_sent)
                VALUES (?,?,?,'sent',?,?)""",
                (lid, campaign_id, email, subject, body))
            c.execute("UPDATE campaigns SET sent_count=sent_count+1 WHERE id=?", (campaign_id,))
            sending_status['sent'] += 1
            sent_today += 1
        except Exception as e:
            c.execute("""INSERT INTO email_logs
                (lead_id, campaign_id, email, status, error, subject_sent, body_sent)
                VALUES (?,?,?,'failed',?,?,?)""",
                (lid, campaign_id, email, str(e), subject, body))
            sending_status['failed'] += 1
        conn.commit()
        time.sleep(_human_delay(s))
    sending_status['running'] = False
    sending_status['campaign_id'] = None
    if sending_status['current'] not in ('Stopped',) and not str(sending_status['current']).startswith('Daily limit reached'):
        sending_status['current'] = 'Done!'
    conn.close()

_logo_img_cache = {}

def _fetch_logo_bytes(url):
    """Download logo image bytes (cached per process lifetime)."""
    if not url:
        return None
    if url in _logo_img_cache:
        return _logo_img_cache[url]
    try:
        req = _urllib_request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with _urllib_request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        _logo_img_cache[url] = data
        return data
    except Exception:
        return None

def _send_one_email(s, to_email, subject, body, sender_name):
    # Embed logo images inline (CID) so they show without "Load images" click
    settings_s = get_all_settings()
    logo_map = [
        ('cid_logo_white', settings_s.get('logo_white_url', '')),
        ('cid_logo_color', settings_s.get('logo_color_url', '')),
    ]
    processed_body = body
    inline_images = []
    for cid, url in logo_map:
        if url and url in processed_body:
            img_bytes = _fetch_logo_bytes(url)
            if img_bytes:
                processed_body = processed_body.replace(f'src="{url}"', f'src="cid:{cid}"')
                processed_body = processed_body.replace(f"src='{url}'", f"src='cid:{cid}'")
                inline_images.append((cid, img_bytes))

    # multipart/related wraps HTML + inline images
    msg = MIMEMultipart('related')
    msg['Subject'] = subject
    msg['From'] = f"{sender_name} <{s['smtp_user']}>"
    msg['To'] = to_email
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid()
    msg['X-Mailer'] = 'LeadPro Humanized Sender 1.1'
    msg['List-Unsubscribe'] = f"<mailto:{s.get('smtp_user', '')}?subject=unsubscribe>"
    msg.attach(MIMEText(processed_body, 'html'))
    for cid, img_bytes in inline_images:
        img_part = MIMEImage(img_bytes)
        img_part.add_header('Content-ID', f'<{cid}>')
        img_part.add_header('Content-Disposition', 'inline')
        msg.attach(img_part)

    port = int(s.get('smtp_port', 465))
    if port == 465:
        server = smtplib.SMTP_SSL(s['smtp_host'], port)
    else:
        server = smtplib.SMTP(s['smtp_host'], port)
        server.starttls()
    server.login(s['smtp_user'], s['smtp_pass'])
    server.sendmail(s['smtp_user'], to_email, msg.as_string())
    server.quit()

@app.route('/api/send-status')
def send_status():
    return jsonify(sending_status)

@app.route('/api/send-stop', methods=['POST'])
def send_stop():
    global sending_status
    sending_status['running'] = False
    return jsonify({'success': True})

def _auto_sender_loop():
    global auto_sender_status
    while True:
        time.sleep(60)
        try:
            settings = get_all_settings()
            enabled = settings.get('auto_send_enabled', '0') == '1'
            auto_sender_status['enabled'] = enabled
            if not enabled or sending_status.get('running'):
                continue
            campaign_id = _safe_int(settings.get('auto_campaign_id', ''), 0)
            if campaign_id <= 0:
                continue
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            daily_limit = max(1, _safe_int(settings.get('daily_limit', '200'), 200))
            sent_today = _get_today_sent_count(conn)
            remaining = max(0, daily_limit - sent_today)
            if remaining <= 0:
                conn.close()
                continue
            c.execute("SELECT id FROM leads WHERE status='new' ORDER BY added_on ASC LIMIT ?", (remaining,))
            lead_ids = [r[0] for r in c.fetchall()]
            conn.close()
            if not lead_ids:
                continue
            auto_sender_status['last_run'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            auto_sender_status['last_batch'] = len(lead_ids)
            auto_sender_status['last_error'] = ''
            _send_emails_worker(lead_ids, campaign_id, 'auto')
        except Exception as e:
            auto_sender_status['last_error'] = str(e)

def _inbox_sync_loop():
    while True:
        time.sleep(30)
        try:
            s = get_all_settings()
            if s.get('inbox_auto_sync', '0') != '1':
                continue
            every = max(1, _safe_int(s.get('inbox_sync_minutes', '5'), 5))
            last = _safe_int(get_setting('inbox_last_sync_epoch') or '0', 0)
            now = int(time.time())
            if now - last < every * 60:
                continue
            sync_inbox_messages(limit=50)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", ('inbox_last_sync_epoch', str(now)))
            conn.commit()
            conn.close()
        except Exception:
            pass

def _opencrawl_loop():
    global opencrawl_status
    while True:
        time.sleep(45)
        try:
            s = get_all_settings()
            enabled = s.get('opencrawl_auto_enabled', '0') == '1'
            opencrawl_status['enabled'] = enabled
            if not enabled:
                continue
            every = max(10, _safe_int(s.get('opencrawl_interval_minutes', '60'), 60))
            last = _safe_int(get_setting('opencrawl_last_run_epoch') or '0', 0)
            now = int(time.time())
            if now - last < every * 60:
                continue
            if opencrawl_status.get('running'):
                continue
            _opencrawl_run_worker('auto')
        except Exception as e:
            opencrawl_status['last_error'] = str(e)

def _opencrawl_run_worker(trigger='manual'):
    global opencrawl_status
    if opencrawl_status.get('running'):
        return
    opencrawl_status['running'] = True
    opencrawl_status['stop_requested'] = False
    opencrawl_status['last_trigger'] = trigger
    opencrawl_status['last_error'] = ''
    opencrawl_status['started_on'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        result = run_opencrawl_cycle(max_runtime_sec=900)
        opencrawl_status['last_run'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        opencrawl_status['last_found'] = result.get('found', 0)
        opencrawl_status['last_inserted'] = result.get('inserted', 0)
        opencrawl_status['last_errors_count'] = result.get('errors', 0)
        opencrawl_status['last_error'] = result.get('last_error', '') or result.get('note', '')
        now = int(time.time())
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", ('opencrawl_last_run_epoch', str(now)))
        conn.commit()
        conn.close()
    except Exception as e:
        opencrawl_status['last_error'] = str(e)
    finally:
        opencrawl_status['current_query'] = ''
        opencrawl_status['running'] = False

@app.route('/api/auto-send/status')
def auto_send_status():
    s = get_all_settings()
    limit = max(1, _safe_int(s.get('daily_limit', '200'), 200))
    sent_today = _get_today_sent_count()
    return jsonify({
        'enabled': s.get('auto_send_enabled', '0') == '1',
        'campaign_id': _safe_int(s.get('auto_campaign_id', ''), 0),
        'daily_limit': limit,
        'sent_today': sent_today,
        'remaining_today': max(0, limit - sent_today),
        'last_run': auto_sender_status.get('last_run', ''),
        'last_error': auto_sender_status.get('last_error', ''),
        'last_batch': auto_sender_status.get('last_batch', 0),
        'sender_running': sending_status.get('running', False),
        'sender_mode': sending_status.get('mode', 'manual')
    })

# ─── TEST EMAIL ─────────────────────────────────────────────────────────────────
@app.route('/api/test-email', methods=['POST'])
def test_email():
    data = request.json
    s = get_all_settings()
    try:
        _send_one_email(s, data['to'], 'LeadPro Test Email ✓',
            '<h2>Connection Successful!</h2><p>Your Hostinger email is configured correctly.</p>',
            s.get('sender_name','LeadPro'))
        return jsonify({'success': True, 'message': 'Test email sent!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ─── SETTINGS ──────────────────────────────────────────────────────────────────
@app.route('/settings')
def settings_page():
    return render_template('settings.html', settings=get_all_settings())

@app.route('/api/settings/save', methods=['POST'])
def save_settings():
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for k, v in data.items():
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, v))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/brand-assets/<path:filename>')
def brand_asset_file(filename):
    os.makedirs(BRAND_ASSETS_DIR, exist_ok=True)
    return send_from_directory(BRAND_ASSETS_DIR, filename)

@app.route('/api/settings/upload-logo', methods=['POST'])
def upload_logo():
    logo_type = (request.form.get('type') or '').strip().lower()
    if logo_type not in ('white', 'color'):
        return jsonify({'success': False, 'error': 'type must be white or color'}), 400
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'file is required'}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'file is required'}), 400

    ext = (os.path.splitext(f.filename)[1] or '').lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'):
        return jsonify({'success': False, 'error': 'Only png/jpg/jpeg/webp/gif/svg allowed'}), 400

    os.makedirs(BRAND_ASSETS_DIR, exist_ok=True)
    filename = f"logo-{logo_type}{ext}"
    file_path = os.path.join(BRAND_ASSETS_DIR, filename)
    f.save(file_path)
    logo_url = request.url_root.rstrip('/') + url_for('brand_asset_file', filename=filename)

    key = 'logo_white_url' if logo_type == 'white' else 'logo_color_url'
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, logo_url))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'key': key, 'url': logo_url})

# ─── LOGS ──────────────────────────────────────────────────────────────────────
@app.route('/logs')
def logs():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT el.id, l.business_name, el.email, c.name, el.status, el.sent_on, el.error
        FROM email_logs el
        LEFT JOIN leads l ON el.lead_id=l.id
        LEFT JOIN campaigns c ON el.campaign_id=c.id
        ORDER BY el.sent_on DESC LIMIT 500''')
    logs_data = c.fetchall()
    conn.close()
    return render_template('logs.html', logs=logs_data)

@app.route('/api/logs/<int:log_id>')
def log_detail(log_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT el.id, el.email, c.name, el.status, el.sent_on, el.error, el.subject_sent, el.body_sent,
            el.campaign_id, el.lead_id
        FROM email_logs el
        LEFT JOIN campaigns c ON el.campaign_id=c.id
        WHERE el.id=?''', (log_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'error': 'Log not found'}), 404

    subject = row[6] or ''
    body = row[7] or ''
    # Fallback for old logs created before snapshot columns existed.
    if not subject or not body:
        campaign_id = row[8]
        lead_id = row[9]
        biz_name, service_needed = '', ''
        if lead_id:
            c.execute("SELECT business_name, service_needed FROM leads WHERE id=?", (lead_id,))
            lr = c.fetchone()
            if lr:
                biz_name, service_needed = lr[0] or '', lr[1] or ''
        c.execute("SELECT subject, body, service FROM campaigns WHERE id=?", (campaign_id,))
        cr = c.fetchone()
        if cr:
            sender_name = get_setting('sender_name') or 'Your Agency'
            service_final = (service_needed or '').strip() or (cr[2] or '').strip()
            subject = subject or _personalize_text(cr[0] or '', biz_name, service_final, sender_name)
            body = body or _append_social_links_footer(_personalize_text(cr[1] or '', biz_name, service_final, sender_name))

    conn.close()
    return jsonify({
        'success': True,
        'id': row[0],
        'email': row[1],
        'campaign': row[2],
        'status': row[3],
        'sent_on': row[4],
        'error': row[5],
        'subject': subject,
        'body': body
    })

@app.route('/inbox')
def inbox_page():
    return render_template('inbox.html')

@app.route('/api/inbox/sync', methods=['POST'])
def inbox_sync():
    try:
        limit = _safe_int((request.json or {}).get('limit', 30), 30)
        result = sync_inbox_messages(limit=max(5, min(limit, 200)))
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/inbox/messages')
def inbox_messages():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT id, sender_name, sender_email, subject, body_text, received_on, replied, lead_id
        FROM inbox_messages ORDER BY received_on DESC LIMIT 500''')
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        'id': r[0], 'sender_name': r[1], 'sender_email': r[2], 'subject': r[3],
        'body_text': r[4], 'received_on': r[5], 'replied': bool(r[6]), 'lead_id': r[7]
    } for r in rows])

@app.route('/api/inbox/reply', methods=['POST'])
def inbox_reply():
    data = request.json or {}
    msg_id = _safe_int(data.get('id', 0), 0)
    to_email = (data.get('to_email') or '').strip().lower()
    subject = (data.get('subject') or '').strip()
    body = (data.get('body') or '').strip()
    if not msg_id or not to_email or not subject or not body:
        return jsonify({'success': False, 'error': 'id, to_email, subject, body required'}), 400
    s = get_all_settings()
    try:
        _send_one_email(s, to_email, subject, body, s.get('sender_name',''))
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE inbox_messages SET replied=1 WHERE id=?", (msg_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/opencrawl/import', methods=['POST'])
def opencrawl_import():
    data = request.json or {}
    urls = data.get('urls', [])
    service_needed = (data.get('service_needed') or '').strip()
    location = (data.get('location') or '').strip()
    if not isinstance(urls, list) or not urls:
        return jsonify({'success': False, 'error': 'urls list required'}), 400
    results = []
    for u in urls[:50]:
        try:
            if not str(u).startswith('http'):
                u = 'https://' + str(u).strip()
            results.append(crawl_site_for_leads(u, service_needed, location))
        except Exception as e:
            results.append({'url': str(u), 'found': 0, 'inserted': 0, 'error': str(e)})
    return jsonify({'success': True, 'results': results})

@app.route('/api/opencrawl/status')
def opencrawl_auto_status():
    s = get_all_settings()
    return jsonify({
        'enabled': s.get('opencrawl_auto_enabled', '0') == '1',
        'running': bool(opencrawl_status.get('running', False)),
        'started_on': opencrawl_status.get('started_on', ''),
        'current_query': opencrawl_status.get('current_query', ''),
        'queries_total': opencrawl_status.get('queries_total', 0),
        'queries_done': opencrawl_status.get('queries_done', 0),
        'interval_minutes': _safe_int(s.get('opencrawl_interval_minutes', '60'), 60),
        'locations': s.get('opencrawl_locations', ''),
        'niches': s.get('opencrawl_niches', ''),
        'services': s.get('opencrawl_services', ''),
        'daily_new_leads_limit': _safe_int(s.get('opencrawl_daily_new_leads_limit', '100'), 100),
        'today_new_leads': _get_today_opencrawl_new_count(),
        'last_run': opencrawl_status.get('last_run', ''),
        'last_found': opencrawl_status.get('last_found', 0),
        'last_inserted': opencrawl_status.get('last_inserted', 0),
        'last_errors_count': opencrawl_status.get('last_errors_count', 0),
        'last_trigger': opencrawl_status.get('last_trigger', ''),
        'last_error': opencrawl_status.get('last_error', ''),
    })

@app.route('/api/opencrawl/run-now', methods=['POST'])
def opencrawl_run_now():
    if opencrawl_status.get('running'):
        return jsonify({'success': True, 'started': False, 'message': 'OpenCrawl already running'})
    t = threading.Thread(target=_opencrawl_run_worker, args=('manual',), daemon=True)
    t.start()
    return jsonify({'success': True, 'started': True, 'message': 'OpenCrawl started'})

@app.route('/api/opencrawl/stop', methods=['POST'])
def opencrawl_stop():
    opencrawl_status['stop_requested'] = True
    return jsonify({'success': True, 'message': 'Stop requested'})

@app.route('/api/whatsapp/open', methods=['POST'])
def whatsapp_open():
    data = request.json or {}
    phone = re.sub(r'[^0-9]', '', data.get('phone', '') or '')
    message = data.get('message', '') or 'Hi'
    if not phone:
        return jsonify({'success': False, 'error': 'phone required'}), 400
    app_url = f"whatsapp://send?phone={phone}&text={quote_plus(message)}"
    web_url = f"https://wa.me/{phone}?text={quote_plus(message)}"
    opened = _open_whatsapp_url(app_url, web_url)
    return jsonify({'success': opened, 'app_url': app_url, 'web_url': web_url})

def _open_whatsapp_url(app_url, web_url=''):
    # Reliable opener for Windows desktop sessions.
    try:
        if os.name == 'nt':
            try:
                os.startfile(app_url)  # type: ignore[attr-defined]
                return True
            except Exception:
                if web_url:
                    os.startfile(web_url)  # type: ignore[attr-defined]
                    return True
                return False
        opened = webbrowser.open(app_url)
        if (not opened) and web_url:
            opened = webbrowser.open(web_url)
        return bool(opened)
    except Exception:
        return False

@app.route('/api/whatsapp/open-bulk', methods=['POST'])
def whatsapp_open_bulk():
    data = request.json or {}
    items = data.get('items', [])
    delay_ms = max(300, min(int(data.get('delay_ms') or 900), 5000))
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'error': 'items required'}), 400

    opened = 0
    failed = 0
    for item in items:
        try:
            phone = re.sub(r'[^0-9]', '', (item or {}).get('phone', '') or '')
            message = (item or {}).get('message', '') or 'Hi'
            if not phone:
                failed += 1
                continue
            app_url = f"whatsapp://send?phone={phone}&text={quote_plus(message)}"
            web_url = f"https://wa.me/{phone}?text={quote_plus(message)}"
            if _open_whatsapp_url(app_url, web_url):
                opened += 1
            else:
                failed += 1
            time.sleep(delay_ms / 1000.0)
        except Exception:
            failed += 1
    return jsonify({'success': True, 'opened': opened, 'failed': failed, 'total': len(items)})

# ─── EMAIL TEMPLATES ────────────────────────────────────────────────────────────
EMAIL_TEMPLATES = {
    "Website Development": {
        "subject": "We noticed {business} doesn't have a website yet 🌐",
        "body": """<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#2563eb">Hi {business},</h2>
<p>I came across your business and noticed you don't have a website yet. In today's digital world, <strong>86% of customers search online before visiting a business</strong> — and without a website, you're missing out on a huge chunk of potential customers.</p>
<p>We specialize in building <strong>fast, professional websites</strong> that:</p>
<ul><li>✅ Look great on mobile & desktop</li><li>✅ Load in under 2 seconds</li><li>✅ Drive real customer inquiries</li></ul>
<p><strong>We've helped 50+ local businesses get online and grow their revenue by 3x in the first year.</strong></p>
<p>I'd love to show you a free mockup of what your website could look like. Can we schedule a quick 15-minute call?</p>
<p>Reply to this email or call us anytime.</p>
<br><p>Best regards,<br><strong>{sender_name}</strong></p>
</div>"""
    },
    "SEO (Search Engine Optimization)": {
        "subject": "{business} is invisible on Google — let's fix that",
        "body": """<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#16a34a">Hi {business},</h2>
<p>I searched for your business on Google and noticed it's not showing up in the top results. <strong>75% of people never scroll past the first page</strong> — which means your competitors are getting the customers that should be yours.</p>
<p>Our SEO services will get {business} ranking on Page 1 for keywords your customers are actually searching:</p>
<ul><li>🔍 Local SEO & Google Business Profile optimization</li><li>📈 Keyword research & content strategy</li><li>🔗 High-quality backlink building</li><li>📊 Monthly ranking reports</li></ul>
<p><strong>We guarantee first-page results within 90 days or your money back.</strong></p>
<p>Want a free SEO audit showing exactly what needs to be fixed? Just reply and I'll send it over!</p>
<br><p>Best regards,<br><strong>{sender_name}</strong></p>
</div>"""
    },
    "Logo Design": {
        "subject": "Your brand deserves a better logo, {business} 🎨",
        "body": """<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#7c3aed">Hi {business},</h2>
<p>A strong logo is the foundation of a memorable brand. I noticed {business} could benefit from a more professional, modern identity that truly represents what you stand for.</p>
<p>We create logos that:</p>
<ul><li>🎯 Are unique and 100% custom (no templates)</li><li>📱 Work on everything — business cards to billboards</li><li>✏️ Come with unlimited revisions until you love it</li><li>📁 Delivered in all formats (AI, PNG, SVG, PDF)</li></ul>
<p><strong>Starting from just ₹4,999 with 3-day delivery.</strong></p>
<p>I'd love to share our portfolio. Shall I send some samples relevant to your industry?</p>
<br><p>Best regards,<br><strong>{sender_name}</strong></p>
</div>"""
    },
    "Social Media Management": {
        "subject": "Your competitors are growing on social — {business} should too",
        "body": """<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#db2777">Hi {business},</h2>
<p>I checked {business}'s social media presence and see a huge opportunity to grow your audience and turn followers into paying customers.</p>
<p>Our Social Media Management includes:</p>
<ul><li>📸 30 posts/month (custom graphics + captions)</li><li>📅 Content calendar & scheduling</li><li>💬 Comment & DM management</li><li>📊 Monthly analytics report</li><li>🎯 Paid ad management (optional)</li></ul>
<p><strong>We've helped clients grow from 500 to 50,000 followers in 6 months.</strong></p>
<p>Can I put together a free content plan for {business} as a sample of what we'd do?</p>
<br><p>Best regards,<br><strong>{sender_name}</strong></p>
</div>"""
    },
    "App Development": {
        "subject": "An app could transform {business}'s customer experience 📱",
        "body": """<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#0891b2">Hi {business},</h2>
<p>Businesses with mobile apps see <strong>3x higher customer retention</strong> than those without. I believe {business} has a real opportunity to leverage this.</p>
<p>We build apps that:</p>
<ul><li>📲 Work on both iOS & Android</li><li>⚡ Are fast, beautiful & easy to use</li><li>🛒 Include features like booking, payments, loyalty programs</li><li>🔔 Push notifications to bring customers back</li></ul>
<p><strong>Full app delivered in 4–6 weeks, starting from ₹29,999.</strong></p>
<p>I'd love to understand your business better and propose a solution. Would you be open to a quick 20-minute discovery call?</p>
<br><p>Best regards,<br><strong>{sender_name}</strong></p>
</div>"""
    },
    "E-commerce Solutions": {
        "subject": "Start selling online — {business} is ready for e-commerce 🛍️",
        "body": """<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#ea580c">Hi {business},</h2>
<p>E-commerce sales are growing by <strong>23% every year</strong>, and businesses like {business} are perfectly positioned to tap into this. If you're not selling online yet, you're leaving serious money on the table.</p>
<p>We build e-commerce stores that:</p>
<ul><li>🏪 Look premium and convert visitors into buyers</li><li>💳 Accept all payment methods (UPI, cards, COD)</li><li>📦 Integrate with logistics providers</li><li>📊 Come with a full analytics dashboard</li></ul>
<p><strong>We set up your complete online store in 7 days.</strong></p>
<p>Want a free demo store built for {business}? Reply and I'll get started!</p>
<br><p>Best regards,<br><strong>{sender_name}</strong></p>
</div>"""
    },
    "UI/UX Design": {
        "subject": "Your users deserve a better experience — {business} 🖥️",
        "body": """<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#4f46e5">Hi {business},</h2>
<p>A confusing interface costs you customers. <strong>88% of users won't return after a bad experience</strong> — and great UI/UX design directly increases conversions and revenue.</p>
<p>Our UI/UX Design services include:</p>
<ul><li>🎨 Full product redesign (web & mobile)</li><li>🧪 User research & usability testing</li><li>📐 Wireframes → Prototypes → Final designs</li><li>💡 Figma/Adobe XD deliverables ready for dev</li></ul>
<p><strong>Our designs have increased client conversions by an average of 67%.</strong></p>
<p>I'd love to do a free UX review of {business}'s current interface. Interested?</p>
<br><p>Best regards,<br><strong>{sender_name}</strong></p>
</div>"""
    },
    "Branding & Graphic Design": {
        "subject": "Build a brand {business} will be proud of 🏆",
        "body": """<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#b45309">Hi {business},</h2>
<p>Strong branding isn't just about looking good — it's about being remembered, trusted, and chosen over competitors. I believe {business} has the potential for a truly powerful brand identity.</p>
<p>Our Branding packages include:</p>
<ul><li>🎯 Brand strategy & positioning</li><li>🎨 Logo + complete visual identity</li><li>📋 Brand guidelines document</li><li>📄 Business cards, letterheads, social media kit</li><li>📦 Packaging design (if needed)</li></ul>
<p><strong>Complete brand package delivered in 10 business days.</strong></p>
<p>Can I share our branding portfolio with you? I think you'll love what we've done for businesses like yours.</p>
<br><p>Best regards,<br><strong>{sender_name}</strong></p>
</div>"""
    },
    "CMS Development": {
        "subject": "Manage your website yourself — no developers needed, {business} 💻",
        "body": """<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#0f766e">Hi {business},</h2>
<p>Tired of depending on developers for every small website change? We build <strong>powerful CMS-powered websites</strong> that let you update content, add pages, and publish blogs yourself — in minutes.</p>
<p>We work with:</p>
<ul><li>⚡ WordPress (most popular, easiest to use)</li><li>🛠️ Custom CMS solutions for specific needs</li><li>🔒 Secure, fast, and SEO-ready by default</li><li>📱 Fully mobile-responsive</li></ul>
<p><strong>Training included — you'll be fully in control of your website.</strong></p>
<p>Would you like to see a live demo of how easy it is to manage? Book a 15-minute call!</p>
<br><p>Best regards,<br><strong>{sender_name}</strong></p>
</div>"""
    },
    "Website Maintenance": {
        "subject": "Is {business}'s website up-to-date and secure? 🔒",
        "body": """<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#dc2626">Hi {business},</h2>
<p><strong>43% of cyberattacks target small businesses</strong>, and outdated websites are the #1 vulnerability. Is {business}'s website regularly backed up, updated, and secured?</p>
<p>Our Website Maintenance plans include:</p>
<ul><li>🔄 Weekly updates (plugins, themes, core)</li><li>💾 Daily automated backups</li><li>🛡️ Security monitoring & malware removal</li><li>⚡ Speed optimization & uptime monitoring</li><li>✏️ Up to 2 hours of content changes/month</li></ul>
<p><strong>From just ₹2,499/month — less than one coffee a day.</strong></p>
<p>I'll do a free security audit of {business}'s website and share the report. Want me to proceed?</p>
<br><p>Best regards,<br><strong>{sender_name}</strong></p>
</div>"""
    }
}

@app.route('/api/campaigns-list')
def campaigns_list():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, service, subject, body, sent_count, created_on, status FROM campaigns ORDER BY created_on DESC")
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        'id': r[0], 'name': r[1], 'service': r[2], 'subject': r[3],
        'body': r[4], 'sent_count': r[5], 'created_on': r[6], 'status': r[7]
    } for r in rows])

@app.route('/api/templates')
def get_templates():
    return jsonify(EMAIL_TEMPLATES)

@app.route('/api/templates/<service>')
def get_template(service):
    t = EMAIL_TEMPLATES.get(service, {})
    return jsonify(t)


# ─── GMB SCRAPER ─────────────────────────────────────────────────────────────
gmb_jobs = {}  # job_id -> { process, logs, status, city, country, category }

@app.route('/gmb-scraper')
def gmb_scraper_page():
    return render_template('gmb_scraper.html')

@app.route('/whatsapp')
def whatsapp_page():
    return render_template('whatsapp.html')

@app.route('/api/gmb/start', methods=['POST'])
def gmb_start():
    data = request.json or {}
    city     = (data.get('city')     or 'Auckland').strip()
    country  = (data.get('country')  or 'New Zealand').strip()
    category = (data.get('category') or 'restaurant').strip()
    service  = (data.get('service_needed') or 'Website Development').strip()
    limit    = max(1, min(int(data.get('limit') or 20), 300))

    # Only one job at a time
    for job in gmb_jobs.values():
        if job.get('status') == 'running':
            return jsonify({'success': False, 'error': 'A scraper is already running. Stop it first.'})

    job_id = str(uuid.uuid4())[:8]
    scraper_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gmb_scraper')

    try:
        proc = subprocess.Popen(
            ['node', 'scraper.js',
             f'--city={city}', f'--country={country}',
             f'--category={category}', f'--limit={limit}'],
            cwd=scraper_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding='utf-8', errors='replace'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': f'Could not start Node.js: {e}'})

    gmb_jobs[job_id] = {
        'process': proc, 'logs': [], 'status': 'running',
        'city': city, 'country': country, 'category': category, 'limit': limit, 'service_needed': service,
    }

    def _read_output():
        try:
            for line in proc.stdout:
                gmb_jobs[job_id]['logs'].append(line.rstrip())
        except Exception:
            pass
        proc.wait()
        if gmb_jobs[job_id]['status'] == 'running':
            gmb_jobs[job_id]['status'] = 'done' if proc.returncode == 0 else 'error'

    threading.Thread(target=_read_output, daemon=True).start()
    return jsonify({'success': True, 'job_id': job_id})

@app.route('/api/gmb/status/<job_id>')
def gmb_status(job_id):
    job = gmb_jobs.get(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404

    offset = _safe_int(request.args.get('offset', 0), 0)
    new_logs = job['logs'][offset:]

    # Load leads from the JSON output file when done
    leads = []
    if job['status'] in ('done', 'error'):
        leads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'leads_data')
        safe_city = re.sub(r'[^a-z0-9_-]', '_', job['city'].lower())
        safe_cat  = re.sub(r'[^a-z0-9_-]', '_', job['category'].lower())
        pattern   = os.path.join(leads_dir, f'gmb_leads_{safe_city}_{safe_cat}_*.json')
        files     = sorted(glob_module.glob(pattern), key=os.path.getmtime, reverse=True)
        if files:
            try:
                with open(files[0], encoding='utf-8') as f:
                    leads = json.load(f).get('leads', [])
            except Exception:
                pass

    # Service-based view filter at backend level:
    # Website/App services -> no_website only
    # SEO/Marketing services -> poor_seo only
    service = (job.get('service_needed') or '').lower()
    seo_keys = ['seo', 'google ads', 'ppc', 'marketing', 'social media', 'content marketing', 'email marketing', 'gmb optimization', 'local seo']
    web_keys = ['website', 'wordpress', 'landing page', 'e-commerce', 'mobile app']
    if any(k in service for k in seo_keys):
        leads = [l for l in leads if (l.get('lead_type') or '').lower() == 'poor_seo']
    elif any(k in service for k in web_keys):
        leads = [l for l in leads if (l.get('lead_type') or 'no_website').lower() != 'poor_seo']

    return jsonify({'success': True, 'status': job['status'], 'new_logs': new_logs, 'leads': leads})

@app.route('/api/gmb/stop', methods=['POST'])
def gmb_stop():
    for job in gmb_jobs.values():
        if job.get('status') == 'running':
            try:
                job['process'].terminate()
                job['status'] = 'stopped'
            except Exception:
                pass
    return jsonify({'success': True})

@app.route('/api/gmb/import', methods=['POST'])
def gmb_import():
    data         = request.json or {}
    leads_list   = data.get('leads', [])
    service      = (data.get('service_needed') or 'Website Development').strip()
    inserted     = 0
    inserted_with_email = 0
    inserted_without_email = 0
    duplicate_email = 0
    duplicate_no_email = 0
    invalid_email = 0
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    for lead in leads_list:
        try:
            location = f"{lead.get('city','')}, {lead.get('country','')}".strip(', ')
            raw_phone = re.sub(r'[\uE000-\uF8FF]', '', (lead.get('phone') or '')).strip()
            phone_match = re.search(r'[\+\d][\d\s\-().]{5,}', raw_phone)
            phone = phone_match.group(0).strip() if phone_match else re.sub(r'[^\d\s+\-(). ]', '', raw_phone).strip()
            website_url = lead.get('website_url') or ''
            raw_email = lead.get('email', '')
            email_v = _normalize_email(raw_email)
            if (raw_email or '').strip() and not email_v:
                invalid_email += 1
            lead_type   = lead.get('lead_type') or 'no_website'
            seo_score   = lead.get('seo_score', '')
            seo_issues  = lead.get('seo_issues') or ''
            notes_parts = [
                f"Rating: {lead.get('rating','N/A')}",
                f"Reviews: {lead.get('reviews','0')}",
                f"GMB: {lead.get('gmb_url','')}",
                f"Type: {lead_type}",
            ]
            if lead_type == 'poor_seo':
                notes_parts.append(f"SEO Score: {seo_score}/100")
                if seo_issues:
                    notes_parts.append(f"SEO Issues: {seo_issues}")
            notes = ' | '.join(notes_parts)
            if email_v:
                c.execute("SELECT id FROM leads WHERE lower(email)=lower(?) LIMIT 1", (email_v,))
                if c.fetchone():
                    duplicate_email += 1
                    continue
                c.execute(
                    '''INSERT OR IGNORE INTO leads
                       (business_name, email, phone, website, location, service_needed, source, notes)
                       VALUES (?,?,?,?,?,?,?,?)''',
                    (lead.get('name',''), email_v, phone,
                     website_url, location, service, 'gmb-scraper', notes)
                )
                if c.rowcount:
                    inserted += 1
                    inserted_with_email += 1
            else:
                # For no-email leads, dedupe by business + phone + website + source.
                c.execute("""SELECT id FROM leads
                             WHERE source='gmb-scraper' AND business_name=? AND phone=? AND website=? LIMIT 1""",
                          (lead.get('name',''), phone, website_url))
                if not c.fetchone():
                    c.execute(
                        '''INSERT INTO leads
                           (business_name, email, phone, website, location, service_needed, source, notes)
                           VALUES (?,?,?,?,?,?,?,?)''',
                        (lead.get('name',''), None, phone,
                         website_url, location, service, 'gmb-scraper', notes)
                    )
                    if c.rowcount:
                        inserted += 1
                        inserted_without_email += 1
                else:
                    duplicate_no_email += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({
        'success': True,
        'inserted': inserted,
        'inserted_with_email': inserted_with_email,
        'inserted_without_email': inserted_without_email,
        'duplicate_email': duplicate_email,
        'duplicate_no_email': duplicate_no_email,
        'invalid_email': invalid_email
    })

@app.route('/api/gmb/publish-sheets', methods=['POST'])
def gmb_publish_sheets():
    import urllib.request as urlreq
    data         = request.json or {}
    leads_list   = data.get('leads', [])
    webhook_url  = (data.get('webhook_url') or '').strip()

    if not webhook_url:
        # Try from saved settings
        webhook_url = get_setting('gmb_sheets_webhook') or ''

    if not webhook_url:
        return jsonify({'success': False, 'error': 'Google Sheets webhook URL not set. Settings mein add karo.'})

    if not leads_list:
        return jsonify({'success': False, 'error': 'No leads to publish'})

    # Save webhook URL for future use
    try:
        conn2 = sqlite3.connect(DB_PATH)
        c2 = conn2.cursor()
        c2.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('gmb_sheets_webhook', webhook_url))
        conn2.commit()
        conn2.close()
    except Exception:
        pass

    payload = json.dumps({'leads': leads_list}).encode('utf-8')
    try:
        req = urlreq.Request(webhook_url, data=payload,
                             headers={'Content-Type': 'application/json'}, method='POST')
        with urlreq.urlopen(req, timeout=20) as resp:
            body = resp.read().decode('utf-8', errors='replace')
        return jsonify({'success': True, 'response': body, 'published': len(leads_list)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/gmb/get-sheets-webhook')
def gmb_get_sheets_webhook():
    return jsonify({'webhook_url': get_setting('gmb_sheets_webhook') or ''})


# ─── LINKEDIN AUTOMATION ──────────────────────────────────────────────────────

_li_sessions = {}   # key -> {session, csrf, member_id, logged_in}
_li_login_status = {'step': '', 'done': False, 'error': ''}
_HAS_LI_API = False  # linkedin-api package not used anymore (using Selenium instead)

def _li_set_step(msg):
    _li_login_status['step'] = msg
    logging.info(f'[LinkedIn] {msg}')

def _li_login(email, password):
    """Login to LinkedIn using a VISIBLE Chrome browser window (user can watch + solve CAPTCHA)."""
    if not email or not password:
        return None, 'Email aur password dono required hain.'
    _li_login_status.update({'step': 'Starting browser...', 'done': False, 'error': ''})
    driver = None
    try:
        _li_set_step('Chrome browser open ho raha hai...')
        driver = _make_chrome_driver()

        _li_set_step('LinkedIn login page khol raha hai...')
        driver.get('https://www.linkedin.com/login')
        time.sleep(4)

        # Use JS to fill form — avoids ChromeDriver 146 find_element crash
        _li_set_step('Typing email address...')
        driver.execute_script("""
        var e = document.getElementById('username') || document.querySelector('input[name="session_key"]');
        if(e){ e.value=arguments[0]; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); }
        """, email)
        time.sleep(0.5)

        _li_set_step("Typing password...")
        driver.execute_script("""
        var e = document.getElementById('password') || document.querySelector('input[name="session_password"]');
        if(e){ e.value=arguments[0]; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); }
        """, password)
        time.sleep(0.5)

        _li_set_step('Clicking login button...')
        driver.execute_script("""
        var btn = document.querySelector('button[type="submit"]') || document.querySelector('.sign-in-form__submit-btn');
        if(btn) btn.click();
        """)

        _li_set_step('Login ho raha hai... (agar CAPTCHA aaye to manually solve karo)')
        # Wait for feed or verify page — up to 60s so user can solve CAPTCHA if needed
        for _ in range(60):
            cur = driver.current_url
            if 'feed' in cur or 'mynetwork' in cur or 'jobs' in cur or 'messaging' in cur:
                break
            if 'challenge' in cur or 'checkpoint' in cur or 'captcha' in cur:
                _li_set_step('CAPTCHA/Challenge detected — please solve it in the browser window!')
            time.sleep(1)

        cur = driver.current_url
        if 'feed' not in cur and 'mynetwork' not in cur and 'jobs' not in cur:
            driver.quit()
            return None, 'Login nahi hua. Browser mein manually login karo phir dobara try karo.'

        _li_set_step('Login successful! Extracting session cookies...')
        selenium_cookies = driver.get_cookies()
        li_at = ''
        jsessionid = ''
        for c in selenium_cookies:
            if c['name'] == 'li_at':
                li_at = c['value']
            if c['name'] == 'JSESSIONID':
                jsessionid = c['value'].strip('"')

        driver.quit()

        if not li_at:
            return None, 'Login hua but li_at cookie nahi mili. Please try again.'

        # Build requests session with extracted cookies
        import requests as _req
        sess = _req.Session()
        sess.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        sess.cookies.set('li_at', li_at, domain='.linkedin.com')
        sess.cookies.set('JSESSIONID', f'"{jsessionid}"', domain='.linkedin.com')

        info = {'session': sess, 'csrf': jsessionid, 'li_at': li_at,
                'member_id': '', 'logged_in': True, 'email': email}
        _li_sessions[email] = info
        _li_sessions['__cookie__'] = info

        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('linkedin_email',?)", (email,))
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('linkedin_password',?)", (password,))
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('linkedin_li_at',?)", (li_at,))
        conn.commit(); conn.close()

        _li_login_status.update({'step': 'Done!', 'done': True, 'error': ''})
        return info, None

    except Exception as e:
        if driver:
            try: driver.quit()
            except Exception: pass
        err = str(e)
        _li_login_status.update({'step': '', 'done': False, 'error': err})
        return None, err

def _li_get_session(email='', password=''):
    """Get cached session. Auto-rebuilds from saved credentials or cookie."""
    # 1. Try in-memory cache
    for key in [email, '__cookie__']:
        if key and key in _li_sessions and _li_sessions[key].get('logged_in'):
            return _li_sessions[key], None
    s = get_all_settings()
    saved_email = email or s.get('linkedin_email', '')
    saved_pass  = password or s.get('linkedin_password', '')
    saved_li_at = s.get('linkedin_li_at', '')
    # 2. Re-login with credentials if li_at not available
    # (Selenium login is interactive so we skip auto re-login here)
    # 3. Rebuild from saved li_at cookie
    if saved_li_at:
        try:
            import requests as _req
            sess = _req.Session()
            sess.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            sess.cookies.set('li_at', saved_li_at, domain='.linkedin.com')
            sess.get('https://www.linkedin.com/feed/', timeout=12)
            jsessionid = sess.cookies.get('JSESSIONID', '').strip('"')
            info = {'session': sess, 'csrf': jsessionid, 'li_at': saved_li_at,
                    'member_id': '', 'logged_in': True, 'email': saved_email}
            _li_sessions['__cookie__'] = info
            return info, None
        except Exception as e:
            return None, str(e)
    return None, 'LinkedIn connected nahi hai. Pehle login karo.'

def _li_headers(info):
    return {
        'csrf-token': info['csrf'],
        'X-Restli-Protocol-Version': '2.0.0',
        'X-Li-Lang': 'en_US',
        'Accept': 'application/vnd.linkedin.normalized+json+2.1',
        'X-Li-Track': '{"clientVersion":"1.13.1","mpVersion":"1.13.1","osName":"web","timezoneOffset":5.5,"deviceFormFactor":"DESKTOP","mpName":"voyager-web"}',
    }

def _li_parse_graphql_results(data):
    """Parse LinkedIn GraphQL search response into our result format."""
    results = []
    try:
        clusters = (data.get('data', {})
                    .get('searchDashClustersByAll', {})
                    .get('elements', []))
        for cluster in clusters:
            for item_wrap in cluster.get('items', []):
                entity = item_wrap.get('item', {}).get('entityResult', {})
                if not entity:
                    continue
                name = entity.get('title', {}).get('text', '') if isinstance(entity.get('title'), dict) else ''
                subtitle = entity.get('primarySubtitle', {}).get('text', '') if isinstance(entity.get('primarySubtitle'), dict) else ''
                summary = entity.get('summary', {}).get('text', '') if isinstance(entity.get('summary'), dict) else ''
                nav_url = entity.get('navigationUrl', '') or ''
                actor_url = entity.get('actorNavigationUrl', '') or ''
                tracking_urn = entity.get('trackingUrn', '') or ''
                profile_url = actor_url if actor_url.startswith('http') else (
                    'https://www.linkedin.com' + actor_url if actor_url.startswith('/') else '')
                post_url = nav_url if 'feed/update' in str(nav_url) else (
                    f'https://www.linkedin.com/feed/update/{tracking_urn}/' if tracking_urn else '')
                email_f, phone_f = _extract_email_phone_from_text(summary)
                results.append({
                    'platform': 'linkedin', 'author': name, 'subtitle': subtitle,
                    'profile_url': profile_url, 'post_text': (summary or '')[:600],
                    'post_url': post_url, 'post_urn': tracking_urn,
                    'email': email_f, 'phone': phone_f,
                })
    except Exception:
        pass
    return results

def _li_parse_blended_results(data):
    """Parse LinkedIn old blended search response."""
    results = []
    try:
        elements = data.get('data', {}).get('elements', [])
        for elem in elements:
            hit = elem.get('hitInfo', {})
            content = hit.get('com.linkedin.voyager.search.SearchContent', {})
            if not content:
                continue
            actor = content.get('actor', {})
            name = actor['name'].get('text', '') if isinstance(actor.get('name'), dict) else ''
            subtitle = actor['subDescription'].get('text', '') if isinstance(actor.get('subDescription'), dict) else ''
            nav = actor.get('navigationUrl', '') if isinstance(actor, dict) else ''
            profile_url = ('https://www.linkedin.com' + nav) if str(nav).startswith('/') else (nav or '')
            commentary = ''
            comm = content.get('commentary', {})
            if isinstance(comm, dict):
                txt = comm.get('text', {})
                commentary = txt.get('text', '') if isinstance(txt, dict) else str(txt or '')
            entity_urn = content.get('entityUrn', '')
            post_url = f'https://www.linkedin.com/feed/update/{entity_urn}/' if entity_urn else ''
            email_f, phone_f = _extract_email_phone_from_text(commentary)
            results.append({
                'platform': 'linkedin', 'author': name, 'subtitle': subtitle,
                'profile_url': profile_url, 'post_text': (commentary or '')[:600],
                'post_url': post_url, 'post_urn': entity_urn,
                'email': email_f, 'phone': phone_f,
            })
    except Exception:
        pass
    return results

_li_scan_status = {'step': '', 'done': False, 'error': ''}
_li_scan_results_store = {'results': [], 'count': 0, 'commented': 0, 'auto_saved': 0, 'error': None}

def _make_chrome_driver():
    """Create a visible Chrome WebDriver compatible with Chrome 115+."""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    import tempfile

    opts = webdriver.ChromeOptions()
    opts.add_argument('--start-maximized')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-extensions')
    opts.add_argument('--disable-infobars')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_argument('--log-level=3')
    # Fresh temp profile — avoids user's extensions/flags causing GetHandleVerifier crash
    tmp_profile = tempfile.mkdtemp(prefix='chrome_leadpro_')
    opts.add_argument(f'--user-data-dir={tmp_profile}')
    opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    # NO experimental options — they cause GetHandleVerifier crash on Chrome 115+
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return driver

# ─── INSTAGRAM AUTOMATION ──────────────────────────────────────────────────────
_ig_login_status = {'step': '', 'done': False, 'error': ''}
_ig_dm_status    = {'step': '', 'done': False, 'error': '', 'sent': 0, 'total': 0}
_ig_client       = None   # instagrapi Client instance

def _ig_set_step(msg, status_dict):
    status_dict['step'] = msg
    logging.info(f'[Instagram] {msg}')

def _ig_login(email, password):
    global _ig_client
    _ig_login_status.update({'step': 'Connecting to Instagram...', 'done': False, 'error': ''})
    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired, TwoFactorRequired, ChallengeRequired, BadPassword

        cl = Client()
        cl.delay_range = [2, 5]

        # Try loading saved session first
        session_file = os.path.join(os.path.dirname(DB_PATH), f'ig_session_{email}.json')
        session_loaded = False
        if os.path.exists(session_file):
            _ig_set_step('Loading saved session...', _ig_login_status)
            try:
                cl.load_settings(session_file)
                cl.login(email, password)
                session_loaded = True
            except Exception:
                session_loaded = False

        if not session_loaded:
            _ig_set_step('Logging in to Instagram...', _ig_login_status)
            try:
                cl.login(email, password)
            except TwoFactorRequired:
                _ig_login_status.update({'step': '2FA required — check your phone/email for the code.', 'done': False, 'error': '2FA_REQUIRED'})
                return
            except ChallengeRequired:
                _ig_login_status.update({'step': 'Instagram requires verification. Try again in a few minutes.', 'done': False, 'error': 'CHALLENGE_REQUIRED'})
                return
            except BadPassword:
                _ig_login_status.update({'step': '', 'done': False, 'error': 'Wrong username or password.'})
                return

        # Save session for future use
        cl.dump_settings(session_file)
        set_setting('ig_email', email)

        _ig_client = cl
        _ig_login_status.update({'step': f'Connected! Logged in as @{cl.username}', 'done': True, 'error': ''})

    except Exception as e:
        err = str(e)
        logging.error(f'[Instagram Login] {err}')
        _ig_login_status.update({'step': '', 'done': False, 'error': err})



def _ig_dm_campaign(niche_kw, message_tpl, max_count, delay_sec):
    """Find niche profiles without a website and send them a DM via instagrapi."""
    global _ig_client
    _ig_dm_status.update({'step': 'Starting DM campaign...', 'done': False,
                          'error': '', 'sent': 0, 'total': 0})
    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired

        cl = _ig_client
        if cl is None:
            # Try reloading from saved session
            email = get_setting('ig_email') or ''
            session_file = os.path.join(os.path.dirname(DB_PATH), f'ig_session_{email}.json')
            if email and os.path.exists(session_file):
                cl = Client()
                cl.load_settings(session_file)
                _ig_client = cl
            else:
                _ig_dm_status.update({'done': True, 'error': 'Please login to Instagram first.'})
                return

        tag = niche_kw.strip().lstrip('#').replace(' ', '')
        _ig_set_step(f'Searching hashtag #{tag} for profiles...', _ig_dm_status)

        # Get recent medias from hashtag
        try:
            medias = cl.hashtag_medias_recent(tag, amount=50)
        except LoginRequired:
            _ig_dm_status.update({'done': True, 'error': 'Session expired. Please login again.'})
            return

        # Collect unique usernames from media owners
        seen = set()
        usernames = []
        for m in medias:
            try:
                uname = m.user.username
                if uname and uname not in seen:
                    seen.add(uname)
                    usernames.append(uname)
            except Exception:
                continue

        _ig_dm_status['total'] = len(usernames)
        _ig_set_step(f'Found {len(usernames)} profiles. Checking bios...', _ig_dm_status)

        sent_count = 0
        for uname in usernames:
            if sent_count >= max_count:
                break
            try:
                _ig_set_step(f'Checking @{uname} ({sent_count}/{max_count} sent)...', _ig_dm_status)
                user_info = cl.user_info_by_username(uname)

                # Skip if they already have a website
                if user_info.external_url:
                    _ig_set_step(f'@{uname} has a website — skipping.', _ig_dm_status)
                    time.sleep(1)
                    continue

                # Build personalised message
                name_display = (user_info.full_name or uname).strip() or uname
                msg_text = (message_tpl
                            .replace('{name}', name_display)
                            .replace('{username}', f'@{uname}')
                            .replace('{niche}', niche_kw))

                _ig_set_step(f'Sending DM to @{uname}...', _ig_dm_status)
                user_id = user_info.pk
                cl.direct_send(msg_text, user_ids=[user_id])

                sent_count += 1
                _ig_dm_status['sent'] = sent_count
                _ig_set_step(f'{sent_count}/{max_count} DMs sent. Last: @{uname}', _ig_dm_status)

                # Save to social_leads
                try:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute('''INSERT OR IGNORE INTO social_leads
                        (platform,author,profile_url,post_text,status) VALUES (?,?,?,?,?)''',
                        ('instagram', uname,
                         f'https://www.instagram.com/{uname}/',
                         f'DM sent | Niche: {niche_kw} | No website in bio',
                         'messaged'))
                    conn.commit(); conn.close()
                except Exception:
                    pass

                # Polite delay (anti-ban)
                wait = delay_sec + random.uniform(3, 8)
                _ig_set_step(f'Waiting {int(wait)}s before next DM...', _ig_dm_status)
                time.sleep(wait)

            except Exception as ex:
                logging.info(f'[Instagram DM] Error for @{uname}: {ex}')
                time.sleep(3)
                continue

        _ig_dm_status.update({
            'step': f'Done! {sent_count} DMs sent successfully.',
            'done': True, 'sent': sent_count
        })

    except Exception as e:
        err = str(e)
        logging.error(f'[Instagram DM] {err}')
        _ig_dm_status.update({'step': '', 'done': True, 'error': err})


def _li_set_scan_step(msg):
    _li_scan_status['step'] = msg
    logging.info(f'[LinkedIn Scan] {msg}')

def _li_search_posts(info, keywords, count=25):
    """Search LinkedIn posts using VISIBLE Chrome browser — user can see everything."""
    _li_scan_status.update({'step': 'Browser shuru ho raha hai...', 'done': False, 'error': ''})
    results = []
    driver = None
    li_at = info.get('li_at', '') or get_setting('linkedin_li_at')

    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        _li_set_scan_step('Chrome browser khul raha hai...')
        driver = _make_chrome_driver()

        # Set login cookie
        _li_set_scan_step('LinkedIn session load ho raha hai...')
        driver.get('https://www.linkedin.com')
        time.sleep(2)
        driver.add_cookie({'name': 'li_at', 'value': li_at, 'domain': '.linkedin.com', 'path': '/'})

        # Search each keyword, collect posts
        keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
        seen_keys = set()

        for kw in keyword_list[:4]:   # max 4 keywords per scan
            if len(results) >= count:
                break
            _li_set_scan_step(f'Searching: "{kw}"...')
            kw_enc = quote_plus(kw)
            driver.get(f'https://www.linkedin.com/search/results/content/?keywords={kw_enc}&sortBy=date_posted&origin=GLOBAL_SEARCH_HEADER')
            time.sleep(4)

            # Check if still logged in
            if 'authwall' in driver.current_url or 'login' in driver.current_url:
                driver.quit()
                _li_scan_status.update({'step': '', 'done': False, 'error': 'Session expire ho gayi.'})
                return [], 'Session expire ho gayi. Dobara "Login to LinkedIn" click karo.'

            _li_set_scan_step(f'Posts load ho rahe hain: "{kw}"...')
            # Slow scroll — LinkedIn uses virtual list, scrolling to bottom removes top items
            # Capture page_source AFTER each scroll batch to get all items
            for scroll_i in range(4):
                driver.execute_script(f'window.scrollBy(0, {800 * (scroll_i + 1)})')
                time.sleep(2)

            _li_set_scan_step(f'Posts parse kar raha hai: "{kw}"...')

            # ── Parse page_source with BeautifulSoup using role="listitem" ────
            # (LinkedIn uses virtual DOM — page_source captures items JS cannot)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            containers = soup.select('[role="listitem"]')

            # Fallback to any older selectors
            if not containers:
                containers = (
                    soup.select('li.reusable-search__result-container') or
                    soup.select('[data-urn*="activity"]') or
                    []
                )

            logging.info(f'[LinkedIn] kw="{kw}" containers found: {len(containers)}')

            # Save debug HTML if nothing found
            if not containers:
                debug_path = os.path.join('data', 'li_debug.html')
                try:
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write(driver.page_source)
                    logging.info(f'[LinkedIn] Debug HTML saved to {debug_path}')
                except Exception:
                    pass

            for container in containers:
                if len(results) >= count:
                    break
                try:
                    full_text = container.get_text(separator='\n', strip=True)

                    # Strip "Feed post" prefix LinkedIn SSR adds
                    full_text = re.sub(r'^Feed post\s*', '', full_text, flags=re.IGNORECASE)

                    lines = [l.strip() for l in full_text.split('\n') if l.strip()]

                    # ── Author + profile URL ──────────────────────────────────
                    link_el = container.find('a', href=lambda h: h and ('/in/' in h or '/company/' in h))
                    profile_url = ''
                    if link_el:
                        href = link_el.get('href', '')
                        profile_url = href.split('?')[0]
                        if not profile_url.startswith('http'):
                            profile_url = 'https://www.linkedin.com' + profile_url

                    # Author = first non-empty line (or link text)
                    name = ''
                    if link_el:
                        name = link_el.get_text(strip=True).split('\n')[0].strip()
                    if not name and lines:
                        name = lines[0]

                    # ── Post text ─────────────────────────────────────────────
                    # Everything after "Follow" line (skips actor block)
                    post_text = full_text
                    follow_idx = full_text.find('\nFollow\n')
                    if follow_idx == -1:
                        follow_idx = full_text.find(' Follow ')
                    if follow_idx != -1:
                        post_text = full_text[follow_idx + 7:].strip()
                    # Remove trailing engagement noise
                    post_text = re.sub(r'\s*\d[\d,]*\s*(reactions?|comments?|reposts?|likes?|shares?).*$',
                                       '', post_text, flags=re.IGNORECASE | re.DOTALL).strip()

                    # Subtitle = second line before "Follow"
                    subtitle = lines[1] if len(lines) > 1 else ''

                    dedup_key = (profile_url or name) + post_text[:60]
                    if dedup_key in seen_keys or not name:
                        continue
                    seen_keys.add(dedup_key)

                    email_f, phone_f = _extract_email_phone_from_text(post_text)
                    results.append({
                        'platform': 'linkedin',
                        'author': name,
                        'subtitle': subtitle,
                        'profile_url': profile_url,
                        'post_text': post_text[:600],
                        'post_url': profile_url,
                        'post_urn': '',
                        'email': email_f,
                        'phone': phone_f,
                    })
                except Exception as ex:
                    logging.info(f'[LinkedIn] parse error: {ex}')
                    continue

            time.sleep(random.uniform(2, 3))

        # Save fresh cookies
        try:
            for ck in driver.get_cookies():
                if ck['name'] == 'JSESSIONID':
                    info['csrf'] = ck['value'].strip('"')
                if ck['name'] == 'li_at':
                    info['li_at'] = ck['value']
        except Exception:
            pass

        driver.quit()
        _li_set_scan_step(f'Done! {len(results)} posts mile.')
        _li_scan_status['done'] = True
        return results, (None if results else 'Koi post nahi mila. Keywords change karo ya dobara try karo.')

    except Exception as e:
        if driver:
            try: driver.quit()
            except Exception: pass
        err = str(e)
        _li_scan_status.update({'step': '', 'done': False, 'error': err})
        return [], err

def _li_post_comment(info, post_urn, comment_text):
    """Post a comment on a LinkedIn post via Voyager API."""
    try:
        sess = info['session']
        member_id = info.get('member_id', '')
        payload = {
            'actor': f'urn:li:fsd_profile:{member_id}' if member_id else '',
            'message': {'attributes': [], 'text': comment_text}
        }
        enc_urn = quote_plus(post_urn)
        url = f'https://www.linkedin.com/voyager/api/socialActions/{enc_urn}/comments'
        hdrs = _li_headers(info)
        hdrs['Content-Type'] = 'application/json'
        r = sess.post(url, json=payload, headers=hdrs, timeout=18)
        return r.status_code in [200, 201], r.text
    except Exception as e:
        return False, str(e)

def _li_build_comment(template, name, keywords):
    service = (keywords or '').split(',')[0].strip() or 'your requirement'
    first_name = (name or 'there').split()[0]
    return template.replace('{name}', first_name).replace('{service}', service)

def _linkedin_monitor_loop():
    """Background thread: periodically scan LinkedIn and auto-comment."""
    while True:
        try:
            s = get_all_settings()
            if s.get('linkedin_auto_monitor', '0') == '1':
                email = s.get('linkedin_email', '')
                password = s.get('linkedin_password', '')
                keywords = s.get('social_keywords', '')
                template = s.get('linkedin_comment_template', '')
                do_comment = s.get('linkedin_comment_auto', '0') == '1'
                if email and password and keywords:
                    info, err = _li_get_session(email, password)
                    if not err and info:
                        results, _ = _li_search_posts(info, keywords)
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        for r in results:
                            post_url = r.get('post_url', '')
                            post_urn = r.get('post_urn', '')
                            name = r.get('author', '')
                            comment = _li_build_comment(template, name, keywords)
                            # skip if already seen
                            c.execute("SELECT id,commented FROM social_leads WHERE post_url=?", (post_url,))
                            row = c.fetchone()
                            commented = 0
                            if do_comment and post_urn and not row:
                                ok, _ = _li_post_comment(info, post_urn, comment)
                                if ok:
                                    commented = 1
                                time.sleep(random.uniform(12, 25))
                            if not row:
                                c.execute("""INSERT OR IGNORE INTO social_leads
                                    (platform,author,subtitle,profile_url,post_text,post_url,post_urn,
                                     email,phone,reply_draft,status,commented,found_on)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,'new',?,datetime('now','localtime'))""",
                                    ('linkedin', name, r.get('subtitle',''), r.get('profile_url',''),
                                     r.get('post_text',''), post_url, post_urn,
                                     r.get('email',''), r.get('phone',''), comment, commented))
                                # auto-save if contact found
                                if r.get('email') or r.get('phone'):
                                    try:
                                        c.execute("""INSERT OR IGNORE INTO leads
                                            (business_name,email,phone,source,status,notes,added_on)
                                            VALUES (?,?,?,'linkedin','new',?,datetime('now','localtime'))""",
                                            (name, r.get('email',''), r.get('phone',''), post_url))
                                    except Exception:
                                        pass
                        conn.commit()
                        conn.close()
        except Exception as e:
            logging.warning(f'LinkedIn monitor error: {e}')
        interval = _safe_int(get_setting('linkedin_monitor_interval'), 30)
        time.sleep(interval * 60)

@app.route('/api/social/linkedin/login-status')
def api_linkedin_login_status():
    return jsonify(_li_login_status)

@app.route('/api/social/linkedin/scan-status')
def api_linkedin_scan_status():
    resp = dict(_li_scan_status)
    if resp.get('done'):
        resp.update(_li_scan_results_store)
    return jsonify(resp)

@app.route('/api/social/linkedin/login', methods=['POST'])
def api_linkedin_login():
    data = request.json or {}
    email    = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()
    li_at_val = (data.get('li_at') or '').strip().strip('"').strip("'")

    # ── Option A: email + password (visible Chrome browser) ───────────────────
    if email and password:
        _li_login_status.update({'step': 'Initializing...', 'done': False, 'error': ''})
        def _do_login():
            _li_login(email, password)
        threading.Thread(target=_do_login, daemon=True).start()
        return jsonify({'success': True, 'async': True,
                        'message': 'Browser khul raha hai! Status check karte raho.'})

    # ── Option B: li_at cookie paste ──────────────────────────────────────────
    if li_at_val:
        try:
            import requests as _req
            sess = _req.Session()
            sess.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            sess.cookies.set('li_at', li_at_val, domain='.linkedin.com')
            sess.get('https://www.linkedin.com/feed/', timeout=12)
            jsessionid = sess.cookies.get('JSESSIONID', '').strip('"')
            me_r = sess.get('https://www.linkedin.com/voyager/api/me',
                            headers={'csrf-token': jsessionid,
                                     'X-Restli-Protocol-Version': '2.0.0',
                                     'Accept': 'application/vnd.linkedin.normalized+json+2.1'},
                            timeout=10)
            if me_r.status_code == 401:
                return jsonify({'success': False, 'error': 'Cookie invalid ya expired. Browser se fresh li_at copy karo.'})
            member_id = ''
            display_email = ''
            if me_r.status_code == 200:
                for item in me_r.json().get('included', []):
                    urn = item.get('entityUrn', '')
                    if 'miniProfile' in urn or 'fsd_profile' in urn:
                        member_id = urn.split(':')[-1]
            info = {'session': sess, 'csrf': jsessionid, 'li_at': li_at_val,
                    'member_id': member_id, 'logged_in': True, 'email': display_email}
            _li_sessions['__cookie__'] = info
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('linkedin_li_at',?)", (li_at_val,))
            conn.commit(); conn.close()
            return jsonify({'success': True, 'email': display_email, 'member_id': member_id})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    return jsonify({'success': False, 'error': 'Email+password ya li_at cookie required hai.'})

@app.route('/api/social/linkedin/scan-comment', methods=['POST'])
def api_linkedin_scan_comment():
    data = request.json or {}
    keywords = (data.get('keywords') or '').strip()
    do_comment = data.get('auto_comment', False)
    comment_tpl = (data.get('comment_template') or '').strip()
    s = get_all_settings()
    email = s.get('linkedin_email', '')
    password = s.get('linkedin_password', '')
    if not email or not password:
        return jsonify({'success': False, 'error': 'LinkedIn credentials not set. Please login first.'})
    info, err = _li_get_session(email, password)
    if err:
        return jsonify({'success': False, 'error': err})
    if not keywords:
        keywords = s.get('social_keywords', 'need website')
    if comment_tpl:
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('linkedin_comment_template',?)", (comment_tpl,))
        conn2.commit(); conn2.close()
    else:
        comment_tpl = s.get('linkedin_comment_template', '')

    def _do_scan():
        results, scan_err = _li_search_posts(info, keywords)
        commented_count = 0
        auto_saved = 0
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for r in results:
            post_urn = r.get('post_urn', '')
            post_url = r.get('post_url', '')
            name = r.get('author', '')
            comment = _li_build_comment(comment_tpl, name, keywords)
            r['reply_draft'] = comment
            commented = 0
            if do_comment and post_urn:
                c.execute("SELECT id FROM social_leads WHERE post_url=? AND commented=1", (post_url,))
                if not c.fetchone():
                    ok, _ = _li_post_comment(info, post_urn, comment)
                    if ok:
                        commented = 1
                        commented_count += 1
                    time.sleep(random.uniform(8, 18))
            r['commented'] = bool(commented)
            try:
                c.execute("""INSERT OR IGNORE INTO social_leads
                    (platform,author,subtitle,profile_url,post_text,post_url,post_urn,
                     email,phone,reply_draft,status,commented,found_on)
                    VALUES (?,?,?,?,?,?,?,?,?,?,'new',?,datetime('now','localtime'))""",
                    ('linkedin', name, r.get('subtitle',''), r.get('profile_url',''),
                     r.get('post_text',''), post_url, post_urn,
                     r.get('email',''), r.get('phone',''), comment, commented))
            except Exception:
                pass
            if r.get('email') or r.get('phone'):
                try:
                    c.execute("""INSERT OR IGNORE INTO leads
                        (business_name,email,phone,source,status,notes,added_on)
                        VALUES (?,?,?,'linkedin','new',?,datetime('now','localtime'))""",
                        (name, r.get('email',''), r.get('phone',''), post_url))
                    if c.rowcount:
                        auto_saved += 1
                except Exception:
                    pass
        conn.commit(); conn.close()
        _li_scan_results_store.update({'results': results, 'count': len(results),
                                       'commented': commented_count, 'auto_saved': auto_saved,
                                       'error': scan_err})

    _li_scan_results_store.update({'results': [], 'count': 0, 'commented': 0, 'auto_saved': 0, 'error': None})
    threading.Thread(target=_do_scan, daemon=True).start()
    return jsonify({'success': True, 'async': True})

@app.route('/api/social/linkedin/settings', methods=['POST'])
def api_linkedin_settings():
    data = request.json or {}
    conn = sqlite3.connect(DB_PATH)
    for key in ['linkedin_auto_monitor', 'linkedin_monitor_interval',
                 'linkedin_comment_auto', 'linkedin_comment_template', 'social_keywords']:
        if key in data:
            conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(data[key])))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/social/linkedin/status')
def api_linkedin_status():
    s = get_all_settings()
    email = s.get('linkedin_email', '')
    logged_in = (('__cookie__' in _li_sessions and _li_sessions['__cookie__'].get('logged_in', False))
                 or (email and email in _li_sessions and _li_sessions[email].get('logged_in', False))
                 or bool(s.get('linkedin_li_at', '')))
    return jsonify({
        'logged_in': logged_in,
        'email': email,
        'auto_monitor': s.get('linkedin_auto_monitor', '0') == '1',
        'auto_comment': s.get('linkedin_comment_auto', '0') == '1',
        'monitor_interval': s.get('linkedin_monitor_interval', '30'),
        'comment_template': s.get('linkedin_comment_template', ''),
    })


# ─── INSTAGRAM ROUTES ────────────────────────────────────────────────────────

@app.route('/api/social/instagram/login', methods=['POST'])
def ig_login_route():
    data = request.get_json() or {}
    email    = data.get('email', '').strip()
    password = data.get('password', '').strip()
    if not email or not password:
        return jsonify({'success': False, 'error': 'Username and password are required.'})
    _ig_login_status.update({'step': 'Starting...', 'done': False, 'error': ''})
    threading.Thread(target=_ig_login, args=(email, password), daemon=True).start()
    return jsonify({'success': True})

@app.route('/api/social/instagram/login-status')
def ig_login_status():
    return jsonify(_ig_login_status)

@app.route('/api/social/instagram/status')
def ig_status():
    connected = _ig_client is not None
    email = get_setting('ig_email') or ''
    username = ''
    if connected:
        try:
            username = _ig_client.username or ''
        except Exception:
            pass
    return jsonify({'connected': connected, 'email': email, 'username': username})

@app.route('/api/social/instagram/dm', methods=['POST'])
def ig_dm_route():
    data = request.get_json() or {}
    niche     = data.get('niche', '').strip()
    msg_tpl   = data.get('message', '').strip()
    max_count = int(data.get('max_count', 10))
    delay_sec = int(data.get('delay', 30))
    if not niche or not msg_tpl:
        return jsonify({'success': False, 'error': 'Niche aur message template required hain.'})
    _ig_dm_status.update({'step': 'Starting...', 'done': False, 'error': '', 'sent': 0, 'total': 0})
    threading.Thread(target=_ig_dm_campaign,
                     args=(niche, msg_tpl, max_count, delay_sec), daemon=True).start()
    return jsonify({'success': True})

@app.route('/api/social/instagram/dm-status')
def ig_dm_status():
    return jsonify(_ig_dm_status)

@app.route('/api/social/instagram/logout', methods=['POST'])
def ig_logout_route():
    global _ig_client
    try:
        if _ig_client:
            _ig_client.logout()
    except Exception:
        pass
    _ig_client = None
    email = get_setting('ig_email') or ''
    session_file = os.path.join(os.path.dirname(DB_PATH), f'ig_session_{email}.json')
    if os.path.exists(session_file):
        try: os.remove(session_file)
        except Exception: pass
    return jsonify({'success': True})

# ─── SOCIAL LEADS ROUTES ──────────────────────────────────────────────────────

def _extract_email_phone_from_text(text):
    emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text or '')
    phones = re.findall(r'(?:\+?91[\-\s]?)?[6-9]\d{9}|(?:\+?[1-9][\d\s\-\(\)]{8,}\d)', text or '')
    return (emails[0] if emails else ''), (phones[0] if phones else '')

def _sanitize_social_error(err):
    e = (err or '').strip()
    if not e:
        return ''
    lo = e.lower()
    if 'timed out' in lo or 'connecttimeout' in lo or 'max retries exceeded' in lo:
        return 'Network timeout while fetching social results. Try again, switch network, or use VPN.'
    if 'linkedin returned 404' in lo:
        return 'LinkedIn endpoint changed or blocked for this session. Try fresh li_at cookie.'
    if len(e) > 220:
        return e[:220] + '...'
    return e

def _first_name(author):
    raw = (author or '').strip().lstrip('@')
    if not raw:
        return 'there'
    return raw.split()[0][:40]

def _build_social_reply_draft(author, service):
    person = _first_name(author)
    svc = (service or 'Website Development').strip()
    return (
        f"Hi {person}, I can help you with {svc}. "
        f"If you want, I can share a quick plan and pricing on your email."
    )

def _auto_save_social_lead(conn, lead):
    email_a = (lead.get('email') or '').strip().lower()
    phone_a = (lead.get('phone') or '').strip()
    name = (lead.get('author') or '').strip() or 'Social Lead'
    service = (lead.get('service') or 'Website Development').strip()
    platform = (lead.get('platform') or 'social').strip()
    post_url = (lead.get('post_url') or '').strip()
    note = f'{platform}: {post_url}' if post_url else platform
    c = conn.cursor()
    if email_a:
        c.execute("SELECT id FROM leads WHERE lower(email)=lower(?)", (email_a,))
        if c.fetchone():
            return False
        c.execute("""INSERT INTO leads
            (business_name,email,phone,source,status,service_needed,notes,added_on)
            VALUES (?,?,?,'social','new',?,?,datetime('now','localtime'))""",
            (name, email_a, phone_a, service, note))
        return bool(c.rowcount)
    if phone_a:
        c.execute("""SELECT id FROM leads
                     WHERE phone=? AND business_name=? AND source='social'""", (phone_a, name))
        if c.fetchone():
            return False
        c.execute("""INSERT INTO leads
            (business_name,email,phone,source,status,service_needed,notes,added_on)
            VALUES (?,NULL,?,'social','new',?,?,datetime('now','localtime'))""",
            (name, phone_a, service, note))
        return bool(c.rowcount)
    return False

def _scan_linkedin(li_at, keywords):
    results = []
    error = None
    try:
        import requests as _req

        # Accept raw cookie value OR full cookie string like "li_at=...; JSESSIONID=..."
        li_raw = (li_at or '').strip()
        if 'li_at=' in li_raw:
            try:
                li_raw = li_raw.split('li_at=', 1)[1].split(';', 1)[0].strip()
            except Exception:
                li_raw = li_raw.strip()
        li_raw = li_raw.strip().strip('"').strip("'")

        def _to_post(u):
            """Normalize one LinkedIn content object into our social lead shape."""
            actor = u.get('actor', {}) if isinstance(u, dict) else {}
            name = actor.get('name', {}).get('text', '') if isinstance(actor.get('name'), dict) else (actor.get('name') or '')
            subtitle = actor.get('subDescription', {}).get('text', '') if isinstance(actor.get('subDescription'), dict) else (actor.get('subDescription') or '')
            nav = actor.get('navigationUrl', '') if isinstance(actor, dict) else ''
            profile_url = ('https://www.linkedin.com' + nav) if nav and str(nav).startswith('/') else (nav or '')
            commentary = ''
            comm = u.get('commentary', {}) if isinstance(u, dict) else {}
            if isinstance(comm, dict):
                txt = comm.get('text', {})
                commentary = txt.get('text', '') if isinstance(txt, dict) else str(txt)
            elif isinstance(comm, str):
                commentary = comm
            entity_urn = (u.get('entityUrn', '') if isinstance(u, dict) else '') or ''
            post_url = f'https://www.linkedin.com/feed/update/{entity_urn}/' if entity_urn else ''
            email, phone = _extract_email_phone_from_text(commentary)
            return {
                'platform': 'linkedin',
                'author': (name or '')[:120],
                'subtitle': (subtitle or '')[:220],
                'profile_url': (profile_url or '')[:500],
                'post_text': (commentary or '')[:600],
                'post_url': (post_url or '')[:500],
                'email': (email or '')[:220],
                'phone': (phone or '')[:80],
            }

        def _parse_voyager_payload(payload):
            out = []
            # Variant 1: old payload style
            elements = payload.get('data', {}).get('elements', []) if isinstance(payload, dict) else []
            for elem in elements:
                hit = elem.get('hitInfo', {}) if isinstance(elem, dict) else {}
                content = hit.get('com.linkedin.voyager.search.SearchContent', {}) if isinstance(hit, dict) else {}
                if content:
                    out.append(_to_post(content))

            # Variant 2: sometimes content objects appear under included/elements directly
            if not out and isinstance(payload, dict):
                candidates = []
                for k in ('included', 'elements'):
                    v = payload.get(k, [])
                    if isinstance(v, list):
                        candidates.extend(v)
                for item in candidates:
                    if not isinstance(item, dict):
                        continue
                    # Heuristic: content-like objects have commentary/entityUrn/actor combos
                    if any(x in item for x in ('commentary', 'entityUrn', 'actor')):
                        p = _to_post(item)
                        if p.get('post_text') or p.get('post_url') or p.get('author'):
                            out.append(p)
            # cleanup
            clean = []
            seen = set()
            for r in out:
                sig = (r.get('author', ''), r.get('post_text', ''), r.get('post_url', ''))
                if sig in seen:
                    continue
                seen.add(sig)
                # Keep entries even when commentary is missing; many LinkedIn payloads hide full text.
                if (r.get('post_text') or '').strip() or (r.get('author') or '').strip() or (r.get('post_url') or '').strip():
                    clean.append(r)
            return clean[:40]

        def _parse_html_fallback(html):
            out = []
            # Try to pull visible text around update URLs
            links = re.findall(r'https://www\.linkedin\.com/feed/update/urn:li:[^"\'\s<]+', html or '')
            links = list(dict.fromkeys(links))[:40]
            for link in links:
                idx = (html or '').find(link)
                start = max(0, idx - 500)
                end = min(len(html or ''), idx + 600)
                chunk = (html or '')[start:end]
                text = re.sub(r'<[^>]+>', ' ', chunk)
                text = re.sub(r'\s+', ' ', text).strip()
                email, phone = _extract_email_phone_from_text(text)
                out.append({
                    'platform': 'linkedin',
                    'author': '',
                    'subtitle': '',
                    'profile_url': '',
                    'post_text': text[:600],
                    'post_url': link,
                    'email': email,
                    'phone': phone,
                })
            return out[:25]

        session = _req.Session()
        session.cookies.set('li_at', li_raw, domain='.linkedin.com')
        session.cookies.set('li_at', li_raw, domain='linkedin.com')
        r0 = session.get('https://www.linkedin.com/',
                         headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'},
                         timeout=12)
        # Quick auth check
        auth_probe = session.get('https://www.linkedin.com/feed/', headers={'User-Agent': 'Mozilla/5.0'}, timeout=12, allow_redirects=True)
        if '/login' in (auth_probe.url or '') or '/checkpoint/' in (auth_probe.url or ''):
            return [], 'LinkedIn session invalid/expired. Please copy fresh li_at cookie after login.'
        jsessionid = session.cookies.get('JSESSIONID', '').strip('"')
        csrf_token = jsessionid or ''
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/vnd.linkedin.normalized+json+2.1',
            'X-Li-Lang': 'en_US',
            'X-Restli-Protocol-Version': '2.0.0',
            'csrf-token': csrf_token,
            'X-Li-Track': '{"clientVersion":"1.13.1","mpVersion":"1.13.1","osName":"web","timezoneOffset":5.5,"deviceFormFactor":"DESKTOP","mpName":"voyager-web"}',
        }
        kw_enc = quote_plus(keywords)
        voyager_urls = [
            (f'https://www.linkedin.com/voyager/api/search/blended'
             f'?count=20&filters=List(resultType->CONTENT)'
             f'&keywords={kw_enc}&origin=GLOBAL_SEARCH_HEADER&q=all&start=0'),
            (f'https://www.linkedin.com/voyager/api/search/cluster'
             f'?count=20&filters=List(resultType->CONTENT)'
             f'&keywords={kw_enc}&origin=GLOBAL_SEARCH_HEADER&q=all&start=0'),
        ]

        last_status = None
        for url in voyager_urls:
            r = session.get(url, headers=headers, timeout=15)
            last_status = r.status_code
            if r.status_code == 401:
                return [], 'LinkedIn session expired. Please update your li_at cookie.'
            if r.status_code != 200:
                continue
            try:
                payload = r.json()
            except Exception:
                continue
            parsed = _parse_voyager_payload(payload)
            if parsed:
                return parsed, None

        # HTML fallback when LinkedIn changes voyager endpoints
        html_url = f'https://www.linkedin.com/search/results/content/?keywords={kw_enc}&origin=GLOBAL_SEARCH_HEADER'
        rh = session.get(html_url, headers={'User-Agent': headers['User-Agent']}, timeout=15)
        if rh.status_code == 200:
            parsed_html = _parse_html_fallback(rh.text)
            if parsed_html:
                return parsed_html, None

        if last_status:
            # Public index fallback (works even when voyager endpoints are blocked/changed)
            ddg_q = f"site:linkedin.com/posts {keywords}"
            fb = []

            # 1) DuckDuckGo HTML mirrors
            ddg_urls = [
                f"https://html.duckduckgo.com/html/?q={quote_plus(ddg_q)}",
                f"https://duckduckgo.com/html/?q={quote_plus(ddg_q)}",
            ]
            for ddg_url in ddg_urls:
                try:
                    rd = requests.get(ddg_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                    soup = BeautifulSoup(rd.text, 'lxml')
                    for item in soup.select('.result')[:25]:
                        a = item.select_one('a.result__a')
                        sn = item.select_one('.result__snippet')
                        if not a:
                            continue
                        href = (a.get('href') or '').strip()
                        if 'duckduckgo.com/l/?' in href and 'uddg=' in href:
                            q = parse_qs(urlparse(href).query)
                            href = unquote((q.get('uddg', [''])[0] or '').strip())
                        if 'linkedin.com' not in href:
                            continue
                        title = (a.get_text(' ', strip=True) or '')[:140]
                        snippet = (sn.get_text(' ', strip=True) if sn else '')[:600]
                        email, phone = _extract_email_phone_from_text(snippet)
                        fb.append({
                            'platform': 'linkedin',
                            'author': title,
                            'subtitle': 'public-index-fallback',
                            'profile_url': '',
                            'post_text': snippet,
                            'post_url': href,
                            'email': email,
                            'phone': phone,
                        })
                    if fb:
                        break
                except Exception:
                    continue

            # 2) Bing fallback (often works where DDG is blocked)
            if not fb:
                try:
                    bing_url = f"https://www.bing.com/search?q={quote_plus(ddg_q)}&count=30"
                    rb = requests.get(bing_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                    soup = BeautifulSoup(rb.text, 'lxml')
                    for li in soup.select('li.b_algo')[:30]:
                        a = li.select_one('h2 a')
                        sn = li.select_one('.b_caption p')
                        if not a:
                            continue
                        href = (a.get('href') or '').strip()
                        if 'linkedin.com' not in href:
                            continue
                        title = (a.get_text(' ', strip=True) or '')[:140]
                        snippet = (sn.get_text(' ', strip=True) if sn else '')[:600]
                        email, phone = _extract_email_phone_from_text(snippet)
                        fb.append({
                            'platform': 'linkedin',
                            'author': title,
                            'subtitle': 'bing-fallback',
                            'profile_url': '',
                            'post_text': snippet,
                            'post_url': href,
                            'email': email,
                            'phone': phone,
                        })
                except Exception:
                    pass

            if fb:
                return fb, 'LinkedIn API blocked; using public indexed posts fallback.'
            return [], f'LinkedIn returned {last_status}. Endpoint changed or session blocked.'
        return [], 'LinkedIn scan failed. Try again with fresh li_at cookie.'
    except Exception as e:
        error = str(e)
    return results, error

def _scan_twitter(keywords):
    results = []
    error = None
    try:
        nitter_hosts = ['nitter.privacydev.net', 'nitter.poast.org', 'nitter.unixfox.eu']
        html = None
        for host in nitter_hosts:
            try:
                r = requests.get(f'https://{host}/search?q={quote_plus(keywords)}&f=tweets',
                                 headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                if r.status_code == 200 and 'tweet-content' in r.text:
                    html = r.text
                    break
            except Exception:
                continue
        if not html:
            return [], 'Could not reach Twitter search. Nitter mirrors may be down — try again later.'
        soup = BeautifulSoup(html, 'html.parser')
        for tweet in soup.select('.timeline-item')[:20]:
            author_el = tweet.select_one('.username')
            content_el = tweet.select_one('.tweet-content')
            link_el = tweet.select_one('a.tweet-link')
            author = author_el.text.strip() if author_el else ''
            content = content_el.text.strip() if content_el else ''
            href = link_el.get('href', '') if link_el else ''
            post_url = ('https://twitter.com' + href) if href and href.startswith('/') else href
            email, phone = _extract_email_phone_from_text(content)
            results.append({
                'platform': 'twitter',
                'author': author,
                'subtitle': '',
                'profile_url': f'https://twitter.com/{author.lstrip("@")}' if author else '',
                'post_text': content[:600],
                'post_url': post_url,
                'email': email,
                'phone': phone,
            })
    except Exception as e:
        error = str(e)
    return results, error

def _scan_facebook(keywords):
    """Scrape public Facebook posts via keyword search."""
    results = []
    error = None
    try:
        r = requests.get(
            f'https://www.facebook.com/public/{quote_plus(keywords)}',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            timeout=12
        )
        soup = BeautifulSoup(r.text, 'html.parser')
        for item in soup.select('[data-testid="post_message"]')[:15]:
            content = item.text.strip()
            if not content:
                continue
            email, phone = _extract_email_phone_from_text(content)
            results.append({
                'platform': 'facebook',
                'author': '',
                'subtitle': '',
                'profile_url': '',
                'post_text': content[:600],
                'post_url': 'https://www.facebook.com/search/posts/?q=' + quote_plus(keywords),
                'email': email,
                'phone': phone,
            })
        if not results:
            error = 'Facebook public search is restricted. Try searching manually at facebook.com and paste post text in the manual section.'
    except Exception as e:
        error = str(e)
    return results, error

def _scan_instagram(keywords):
    """Scrape Instagram hashtag/keyword posts."""
    results = []
    error = None
    try:
        tag = keywords.replace(' ', '').replace(',', '')
        r = requests.get(
            f'https://www.instagram.com/explore/tags/{quote_plus(tag)}/',
            headers={
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': 'text/html,application/xhtml+xml',
            },
            timeout=12
        )
        data_match = re.search(r'window\._sharedData\s*=\s*(\{.+?\});</script>', r.text)
        if data_match:
            jd = json.loads(data_match.group(1))
            edges = jd.get('entry_data', {}).get('TagPage', [{}])[0].get('graphql', {}).get('hashtag', {}).get('edge_hashtag_to_media', {}).get('edges', [])
            for edge in edges[:15]:
                node = edge.get('node', {})
                caption = node.get('edge_media_to_caption', {}).get('edges', [{}])[0].get('node', {}).get('text', '')
                shortcode = node.get('shortcode', '')
                email, phone = _extract_email_phone_from_text(caption)
                results.append({
                    'platform': 'instagram',
                    'author': '',
                    'subtitle': '',
                    'profile_url': '',
                    'post_text': (caption or '')[:600],
                    'post_url': f'https://www.instagram.com/p/{shortcode}/' if shortcode else '',
                    'email': email,
                    'phone': phone,
                })
        if not results:
            error = 'Instagram is restricting scraping. Try using the manual paste section below.'
    except Exception as e:
        error = str(e)
    return results, error

def _scan_ddg_web(keywords, site_filters=None, platform='web'):
    results = []
    error = None
    try:
        q = keywords
        if site_filters:
            q = f"{keywords} " + " OR ".join([f"site:{s}" for s in site_filters])
        r = requests.get(
            f'https://html.duckduckgo.com/html/?q={quote_plus(q)}',
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=15
        )
        soup = BeautifulSoup(r.text, 'html.parser')
        items = soup.select('.result')
        for item in items[:25]:
            a = item.select_one('.result__a')
            sn = item.select_one('.result__snippet')
            if not a:
                continue
            href = (a.get('href') or '').strip()
            title = (a.get_text(' ', strip=True) or '').strip()
            snippet = (sn.get_text(' ', strip=True) if sn else '').strip()
            if 'duckduckgo.com/l/?' in href and 'uddg=' in href:
                try:
                    qd = parse_qs(urlparse(href).query)
                    href = unquote((qd.get('uddg', [''])[0] or '').strip())
                except Exception:
                    pass
            email, phone = _extract_email_phone_from_text(snippet)
            results.append({
                'platform': platform,
                'author': title[:140] or 'Lead',
                'subtitle': urlparse(href).netloc if href else '',
                'profile_url': href,
                'post_text': snippet[:600],
                'post_url': href,
                'email': email,
                'phone': phone,
            })
        if not results:
            error = 'No matching public posts found for this keyword.'
    except Exception as e:
        error = str(e)
    return results, error

def _scan_reddit(keywords):
    return _scan_ddg_web(keywords, ['reddit.com'], 'reddit')

def _scan_jobboards(keywords):
    return _scan_ddg_web(
        keywords,
        ['upwork.com', 'fiverr.com', 'freelancer.com', 'guru.com', 'indeed.com', 'linkedin.com/jobs'],
        'jobboard'
    )

def _scan_directories(keywords):
    return _scan_ddg_web(
        keywords,
        ['yelp.com', 'yellowpages.com', 'clutch.co', 'justdial.com', 'bing.com/maps', 'google.com/maps'],
        'directory'
    )

def _save_social_results(results):
    settings = get_all_settings()
    auto_save = settings.get('social_auto_save', '1') == '1'
    default_service = settings.get('social_default_service', 'Website Development')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    saved = 0
    auto_saved = 0
    drafted = 0
    for r in results:
        try:
            reply_draft = _build_social_reply_draft(r.get('author', ''), default_service)
            if reply_draft:
                drafted += 1
            c.execute("""SELECT id FROM social_leads
                         WHERE platform=? AND author=? AND post_url=? AND post_text=?
                         LIMIT 1""",
                      (r['platform'], r.get('author', ''), r.get('post_url', ''), r.get('post_text', '')))
            existing = c.fetchone()
            if existing:
                social_id = existing[0]
            else:
                c.execute("""INSERT INTO social_leads
                    (platform,author,subtitle,profile_url,post_text,post_url,email,phone,reply_draft,status,found_on)
                    VALUES (?,?,?,?,?,?,?,?,?,'new',datetime('now','localtime'))""",
                    (r['platform'], r['author'], r.get('subtitle', ''), r.get('profile_url', ''),
                     r.get('post_text', ''), r.get('post_url', ''), r.get('email', ''), r.get('phone', ''), reply_draft))
                saved += 1
                social_id = c.lastrowid

            if auto_save and (r.get('email') or r.get('phone')):
                inserted = _auto_save_social_lead(conn, {
                    'author': r.get('author', ''),
                    'email': r.get('email', ''),
                    'phone': r.get('phone', ''),
                    'platform': r.get('platform', ''),
                    'post_url': r.get('post_url', ''),
                    'service': default_service,
                })
                if inserted:
                    auto_saved += 1
                if social_id:
                    c.execute("UPDATE social_leads SET status='saved' WHERE id=?", (social_id,))
        except Exception:
            pass
    conn.commit()
    conn.close()
    return {'saved': saved, 'auto_saved': auto_saved, 'drafted': drafted}

@app.route('/social')
def social_page():
    s = get_all_settings()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM social_leads ORDER BY found_on DESC LIMIT 300")
    leads = [dict(r) for r in c.fetchall()]
    conn.close()
    return render_template('social.html',
        leads=leads,
        initial_platform=(request.args.get('platform') or '').strip().lower(),
        li_at=s.get('linkedin_li_at', ''),
        li_email=s.get('linkedin_email', ''),
        li_comment_tpl=s.get('linkedin_comment_template', ''),
        social_keywords=s.get('social_keywords', 'need website,website development,need SEO'),
        social_auto_save=s.get('social_auto_save', '1'),
        brand_primary=s.get('brand_primary', '#2563eb'),
    )

@app.route('/api/social/scan', methods=['POST'])
def api_social_scan():
    data = request.json or {}
    platform = data.get('platform', 'linkedin')
    keywords = (data.get('keywords') or '').strip()
    li_at_new = (data.get('li_at') or '').strip()
    s = get_all_settings()
    if li_at_new:
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('linkedin_li_at',?)", (li_at_new,))
        conn2.commit(); conn2.close()
        s['linkedin_li_at'] = li_at_new
    if keywords:
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('social_keywords',?)", (keywords,))
        conn2.commit(); conn2.close()
    if not keywords:
        keywords = s.get('social_keywords', 'need website')
    results, error = [], None
    if platform == 'linkedin':
        li_at = li_at_new or s.get('linkedin_li_at', '')
        if not li_at:
            return jsonify({'success': False, 'error': 'LinkedIn li_at cookie is required.'})
        results, error = _scan_linkedin(li_at, keywords)
    elif platform == 'twitter':
        results, error = _scan_twitter(keywords)
    elif platform == 'facebook':
        results, error = _scan_facebook(keywords)
    elif platform == 'instagram':
        results, error = _scan_instagram(keywords)
    elif platform == 'reddit':
        results, error = _scan_reddit(keywords)
    elif platform == 'jobboard':
        results, error = _scan_jobboards(keywords)
    elif platform == 'directory':
        results, error = _scan_directories(keywords)
    save_stats = _save_social_results(results)
    return jsonify({'success': True, 'results': results, 'error': _sanitize_social_error(error),
                    'count': len(results), 'saved': save_stats.get('saved', 0),
                    'auto_saved': save_stats.get('auto_saved', 0),
                    'drafted': save_stats.get('drafted', 0)})

@app.route('/api/social/manual', methods=['POST'])
def api_social_manual():
    """Save a manually pasted post as a social lead."""
    data = request.json or {}
    platform = data.get('platform', 'manual')
    post_text = (data.get('post_text') or '').strip()
    author = (data.get('author') or '').strip()
    profile_url = (data.get('profile_url') or '').strip()
    if not post_text:
        return jsonify({'success': False, 'error': 'Post text is required.'})
    email, phone = _extract_email_phone_from_text(post_text)
    s = get_all_settings()
    default_service = s.get('social_default_service', 'Website Development')
    reply_draft = _build_social_reply_draft(author, default_service)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO social_leads
        (platform,author,subtitle,profile_url,post_text,post_url,email,phone,reply_draft,status,found_on)
        VALUES (?,?,?,?,?,?,?,?,?,'new',datetime('now','localtime'))""",
        (platform, author, '', profile_url, post_text, profile_url, email, phone, reply_draft))
    lid = c.lastrowid
    auto_saved = False
    if s.get('social_auto_save', '1') == '1' and (email or phone):
        auto_saved = _auto_save_social_lead(conn, {
            'author': author,
            'email': email,
            'phone': phone,
            'platform': platform,
            'post_url': profile_url,
            'service': default_service,
        })
        if auto_saved:
            c.execute("UPDATE social_leads SET status='saved' WHERE id=?", (lid,))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': lid, 'email': email, 'phone': phone, 'auto_saved': bool(auto_saved)})

@app.route('/api/social/save-lead', methods=['POST'])
def api_social_save_lead():
    data = request.json or {}
    name    = (data.get('author') or '').strip()
    email_a = (data.get('email') or '').strip()
    phone_a = (data.get('phone') or '').strip()
    platform = data.get('platform', '')
    post_url  = (data.get('post_url') or '').strip()
    sid = data.get('id')
    if not name and not email_a and not phone_a:
        return jsonify({'success': False, 'error': 'No contact info to save.'})
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        email_value = email_a if email_a else None
        c.execute("""INSERT OR IGNORE INTO leads
            (business_name,email,phone,source,status,notes,added_on)
            VALUES (?,?,?,'social','new',?,datetime('now','localtime'))""",
            (name or 'Social Lead', email_value, phone_a, f'{platform}: {post_url}'))
        lead_id = c.lastrowid
        if sid:
            c.execute("UPDATE social_leads SET status='saved' WHERE id=?", (sid,))
        conn.commit(); conn.close()
        return jsonify({'success': True, 'lead_id': lead_id})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/social/delete/<int:sid>', methods=['POST'])
def api_social_delete(sid):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM social_leads WHERE id=?", (sid,))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/social/leads')
def api_social_leads():
    platform = request.args.get('platform', '')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if platform:
        c.execute("SELECT * FROM social_leads WHERE platform=? ORDER BY found_on DESC LIMIT 300", (platform,))
    else:
        c.execute("SELECT * FROM social_leads ORDER BY found_on DESC LIMIT 300")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/linkedin')
def linkedin_page():
    return redirect(url_for('social_page'))


# ─── CALENDAR / BOOKING ROUTES ────────────────────────────────────────────────

def _get_booked_slots():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT slot_datetime FROM bookings WHERE status != 'cancelled'")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows

def _generate_slots(days_ahead=14, start_hour=9, end_hour=18, slot_minutes=60):
    from datetime import timedelta
    booked = set(_get_booked_slots())
    slots = {}
    today = datetime.now()
    for i in range(1, days_ahead + 1):
        day = today + timedelta(days=i)
        if day.weekday() >= 5:
            continue
        date_str = day.strftime('%Y-%m-%d')
        day_slots = []
        current = day.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        end = day.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        while current < end:
            slot_dt_str = current.strftime('%Y-%m-%d %H:%M')
            if slot_dt_str not in booked:
                day_slots.append(current.strftime('%H:%M'))
            current += timedelta(minutes=slot_minutes)
        if day_slots:
            slots[date_str] = day_slots
    return slots

@app.route('/book')
def booking_page():
    s = get_all_settings()
    slots = _generate_slots(
        int(s.get('booking_days_ahead', 14)),
        int(s.get('booking_start_hour', 9)),
        int(s.get('booking_end_hour', 18)),
        int(s.get('booking_slot_minutes', 60))
    )
    return render_template('book.html',
        slots_json=json.dumps(slots),
        title=s.get('booking_title', 'Book a Free Discovery Call'),
        subtitle=s.get('booking_subtitle', 'Pick a time that works for you — 15 minutes, no pressure.'),
        sender_name=s.get('sender_name', 'Our Team'),
        brand_primary=s.get('brand_primary', '#2563eb'),
    )

@app.route('/api/book', methods=['POST'])
def api_book():
    data = request.json or {}
    name    = (data.get('name') or '').strip()
    email_addr = (data.get('email') or '').strip()
    company = (data.get('company') or '').strip()
    phone   = (data.get('phone') or '').strip()
    slot    = (data.get('slot') or '').strip()
    message = (data.get('message') or '').strip()
    if not name or not email_addr or not slot:
        return jsonify({'success': False, 'error': 'Name, email and slot are required.'})
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM bookings WHERE slot_datetime=? AND status!='cancelled'", (slot,))
    if c.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': 'This slot was just booked. Please choose another time.'})
    c.execute("""INSERT INTO bookings (name,email,company,phone,slot_datetime,message,status,created_on)
                 VALUES (?,?,?,?,?,?,'pending',datetime('now','localtime'))""",
              (name, email_addr, company, phone, slot, message))
    booking_id = c.lastrowid
    conn.commit()
    conn.close()
    threading.Thread(target=_send_booking_confirmation, args=(name, email_addr, company, slot), daemon=True).start()
    threading.Thread(target=_send_booking_notification, args=(name, email_addr, company, phone, slot, message), daemon=True).start()
    return jsonify({'success': True, 'booking_id': booking_id})

def _send_booking_confirmation(name, email_addr, company, slot):
    try:
        s = get_all_settings()
        smtp_host = s.get('smtp_host', '')
        smtp_port = int(s.get('smtp_port', 465))
        smtp_user = s.get('smtp_user', '')
        smtp_pass = s.get('smtp_pass', '')
        sender_name = s.get('sender_name', 'Our Team')
        brand_primary = s.get('brand_primary', '#2563eb')
        if not smtp_user or not smtp_pass:
            return
        try:
            dt = datetime.strptime(slot, '%Y-%m-%d %H:%M')
            slot_readable = dt.strftime('%A, %B %d %Y at %I:%M %p')
        except Exception:
            slot_readable = slot
        subject = f"Booking Confirmed — {slot_readable}"
        body = f"""<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#333;">
<div style="background:{brand_primary};padding:32px 24px;border-radius:12px 12px 0 0;text-align:center;">
  <h1 style="color:#fff;font-size:22px;margin:0;">Booking Confirmed!</h1>
</div>
<div style="background:#fff;padding:32px 24px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;border-top:none;">
  <p style="font-size:16px;">Hi <strong>{name}</strong>,</p>
  <p style="color:#444;">Your call has been booked successfully.</p>
  <div style="background:#f8fafc;border-left:4px solid {brand_primary};padding:16px 20px;border-radius:0 8px 8px 0;margin:20px 0;">
    <p style="margin:0 0 6px;font-size:15px;"><strong>Date & Time:</strong> {slot_readable}</p>
    {f'<p style="margin:0;font-size:15px;"><strong>Company:</strong> {company}</p>' if company else ''}
  </div>
  <p style="color:#444;">We will reach out with call details shortly. Need to reschedule? Just reply to this email.</p>
  <p style="margin-top:28px;color:#444;">Looking forward to speaking with you!<br><br>Best regards,<br><strong>{sender_name}</strong></p>
</div></div>"""
        import ssl
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{sender_name} <{smtp_user}>"
        msg['To'] = email_addr
        msg['Date'] = formatdate(localtime=True)
        msg.attach(MIMEText(body, 'html'))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as srv:
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, [email_addr], msg.as_string())
    except Exception as e:
        logging.warning(f"Booking confirmation email failed: {e}")

def _send_booking_notification(name, email_addr, company, phone, slot, message):
    try:
        s = get_all_settings()
        smtp_host = s.get('smtp_host', '')
        smtp_port = int(s.get('smtp_port', 465))
        smtp_user = s.get('smtp_user', '')
        smtp_pass = s.get('smtp_pass', '')
        sender_name = s.get('sender_name', 'Our Team')
        if not smtp_user or not smtp_pass:
            return
        try:
            dt = datetime.strptime(slot, '%Y-%m-%d %H:%M')
            slot_readable = dt.strftime('%A, %B %d %Y at %I:%M %p')
        except Exception:
            slot_readable = slot
        subject = f"New Meeting Booked — {name} ({slot_readable})"
        body = f"""<div style="font-family:Arial,sans-serif;max-width:480px;color:#333;">
<h2 style="color:#2563eb;">New Booking Alert</h2>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
  <tr><td style="padding:8px 0;font-weight:600;width:90px;">Name:</td><td>{name}</td></tr>
  <tr><td style="padding:8px 0;font-weight:600;">Email:</td><td>{email_addr}</td></tr>
  <tr><td style="padding:8px 0;font-weight:600;">Company:</td><td>{company or '—'}</td></tr>
  <tr><td style="padding:8px 0;font-weight:600;">Phone:</td><td>{phone or '—'}</td></tr>
  <tr><td style="padding:8px 0;font-weight:600;">Slot:</td><td><strong>{slot_readable}</strong></td></tr>
  <tr><td style="padding:8px 0;font-weight:600;">Message:</td><td>{message or '—'}</td></tr>
</table>
<p><a href="http://localhost:5000/calendar">View all bookings</a></p></div>"""
        import ssl
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{sender_name} <{smtp_user}>"
        msg['To'] = smtp_user
        msg['Date'] = formatdate(localtime=True)
        msg.attach(MIMEText(body, 'html'))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as srv:
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, [smtp_user], msg.as_string())
    except Exception as e:
        logging.warning(f"Booking notification email failed: {e}")

@app.route('/calendar')
def calendar_page():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM bookings ORDER BY slot_datetime ASC")
    bookings = [dict(r) for r in c.fetchall()]
    conn.close()
    s = get_all_settings()
    return render_template('calendar.html', bookings=bookings,
                           sender_name=s.get('sender_name', 'Our Team'),
                           brand_primary=s.get('brand_primary', '#2563eb'))

@app.route('/api/bookings')
def api_get_bookings():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM bookings ORDER BY slot_datetime ASC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/bookings/<int:bid>/update', methods=['POST'])
def api_update_booking(bid):
    data = request.json or {}
    status = data.get('status', 'confirmed')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE bookings SET status=? WHERE id=?", (status, bid))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/calendar/slots')
def api_calendar_slots():
    s = get_all_settings()
    slots = _generate_slots(
        int(s.get('booking_days_ahead', 14)),
        int(s.get('booking_start_hour', 9)),
        int(s.get('booking_end_hour', 18)),
        int(s.get('booking_slot_minutes', 60))
    )
    return jsonify(slots)


if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    init_db()
    threading.Thread(target=_auto_sender_loop, daemon=True).start()
    threading.Thread(target=_inbox_sync_loop, daemon=True).start()
    threading.Thread(target=_opencrawl_loop, daemon=True).start()
    threading.Thread(target=_linkedin_monitor_loop, daemon=True).start()
    print("\nLeadPro is running at: http://localhost:5000\n")
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)



