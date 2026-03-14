"""
LeadPro - Lead Scraper Helper
==============================
Run this separately to scrape leads from Google search
and auto-add them to your LeadPro database.

Usage:
    python scraper.py --service "Website Development" --location "Delhi" --niche "restaurant"
    python scraper.py --service "SEO" --location "Mumbai" --niche "hotel"
    python scraper.py --service "Logo Design" --location "Bangalore" --niche "gym"

Requirements: pip install requests beautifulsoup4 lxml
"""

import requests, sqlite3, time, re, argparse, json
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse

DB_PATH = "data/leads.db"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

SERVICE_MAP = {
    "website": "Website Development",
    "seo": "SEO (Search Engine Optimization)",
    "logo": "Logo Design",
    "social": "Social Media Management",
    "app": "App Development",
    "ecommerce": "E-commerce Solutions",
    "uiux": "UI/UX Design",
    "branding": "Branding & Graphic Design",
    "cms": "CMS Development",
    "maintenance": "Website Maintenance",
}

def extract_email(text):
    """Extract email addresses from text."""
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text)
    # Filter out common false positives
    bad = ['example.com', 'sentry.io', 'domain.com', 'email.com', 'wixpress.com']
    return [e for e in emails if not any(b in e for b in bad)]

def extract_phone(text):
    """Extract Indian phone numbers from text."""
    pattern = r'(?:\+91[-\s]?)?[6-9]\d{9}'
    phones = re.findall(pattern, text.replace(' ','').replace('-',''))
    return phones[0] if phones else ''

def scrape_google(query, pages=3):
    """Scrape Google search results for business info."""
    results = []
    for page in range(pages):
        url = f"https://www.google.com/search?q={quote_plus(query)}&start={page*10}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, 'lxml')
            for result in soup.select('.tF2Cxc, .g'):
                title_el = result.select_one('h3')
                link_el = result.select_one('a[href]')
                snippet_el = result.select_one('.VwiC3b, .s3v9rd')
                if title_el and link_el:
                    href = link_el.get('href','')
                    if href.startswith('/url?q='):
                        href = href.split('/url?q=')[1].split('&')[0]
                    results.append({
                        'title': title_el.get_text(),
                        'url': href,
                        'snippet': snippet_el.get_text() if snippet_el else ''
                    })
            time.sleep(2)
        except Exception as e:
            print(f"Search error: {e}")
    return results

def scrape_business_contact(url):
    """Visit a business website and extract contact info."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(resp.text, 'lxml')
        text = soup.get_text()
        # Try contact page too
        contact_links = soup.find_all('a', href=True)
        contact_url = None
        for link in contact_links:
            if 'contact' in link.get('href','').lower():
                href = link['href']
                if href.startswith('http'):
                    contact_url = href
                else:
                    contact_url = url.rstrip('/') + '/' + href.lstrip('/')
                break
        if contact_url:
            try:
                cr = requests.get(contact_url, headers=HEADERS, timeout=6)
                text += BeautifulSoup(cr.text, 'lxml').get_text()
            except: pass
        emails = extract_email(text)
        phone = extract_phone(text)
        return emails[0] if emails else '', phone
    except Exception as e:
        return '', ''

def save_lead(business_name, email, phone, website, location, service):
    """Save a lead to the database."""
    if not email:
        return False
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO leads
            (business_name, email, phone, website, location, service_needed, source)
            VALUES (?,?,?,?,?,?,?)''',
            (business_name, email, phone, website, location, service, 'scraper'))
        inserted = c.rowcount
        conn.commit()
        conn.close()
        return bool(inserted)
    except Exception as e:
        print(f"DB error: {e}")
        return False

def run_scraper(service, location, niche, pages=3):
    """Main scraper function."""
    print(f"\n🔍 Searching: {niche} businesses in {location}")
    print(f"📌 Service to pitch: {service}")
    print("─" * 50)
    
    queries = [
        f"{niche} {location} contact email",
        f"{niche} shop {location} phone number",
        f"best {niche} in {location} email",
        f"{niche} {location} site:justdial.com OR site:indiamart.com",
    ]
    
    found = 0
    for query in queries:
        print(f"\n🌐 Query: {query}")
        results = scrape_google(query, pages=2)
        
        for r in results:
            url = r['url']
            if not url.startswith('http'): continue
            domain = urlparse(url).netloc
            if any(skip in domain for skip in ['google','youtube','facebook','instagram','twitter','linkedin','justdial','indiamart']): 
                # For directories, try to get info from snippet
                emails = extract_email(r['snippet'])
                phone = extract_phone(r['snippet'])
                if emails:
                    if save_lead(r['title'], emails[0], phone, url, location, service):
                        print(f"  ✓ {r['title']} → {emails[0]}")
                        found += 1
                continue
            
            print(f"  🌐 Visiting: {domain}")
            email, phone = scrape_business_contact(url)
            if email:
                if save_lead(r['title'], email, phone, url, location, service):
                    print(f"  ✓ {r['title']} → {email}")
                    found += 1
                else:
                    print(f"  ↩ Duplicate: {email}")
            time.sleep(1.5)
    
    print(f"\n✅ Done! Added {found} new leads to database.")
    print("🚀 Open http://localhost:5000/leads to view & email them!")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='LeadPro Scraper')
    parser.add_argument('--service', default='Website Development', help='Service to pitch')
    parser.add_argument('--location', default='Delhi', help='Target city')
    parser.add_argument('--niche', default='restaurant', help='Business type to target')
    parser.add_argument('--pages', type=int, default=3, help='Search pages')
    args = parser.parse_args()
    
    service = SERVICE_MAP.get(args.service.lower(), args.service)
    run_scraper(service, args.location, args.niche, args.pages)
