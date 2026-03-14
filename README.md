# LeadPro - Lead Generation and Outreach Platform

LeadPro is a local-first lead generation and outreach system for agencies.  
It includes lead capture, GMB scraping, campaign management, social lead intake, and bulk email workflows.

## Quick Start (5 Minutes)

### 1) Install Python
Download and install Python from: https://www.python.org/downloads/  
During installation, enable: `Add Python to PATH`.

### 2) Start LeadPro

Windows:
```bat
START_WINDOWS.bat
```

Mac/Linux:
```bash
chmod +x START_MAC_LINUX.sh
./START_MAC_LINUX.sh
```

### 3) Open in Browser
`http://localhost:5000`

## First-Time Setup

Open `http://localhost:5000/settings` and configure:
- SMTP Host (example: `smtp.hostinger.com`)
- SMTP Port (example: `465`)
- SMTP User Email
- SMTP Password
- Sender Name

Then click:
1. `Save Settings`
2. `Test Connection`

## Main Features

- Dashboard and quick lead capture
- CSV and document lead import
- GMB scraper workflow
- Cold leads and all leads management
- Campaign builder and bulk sending
- Email logs and inbox tracking
- Social lead scanner (LinkedIn/X/Facebook/Instagram/manual)
- Booking calendar and scheduling

## Usage Examples

### Manual Lead Add
1. Open Dashboard.
2. Fill business name, email, phone, and service.
3. Click `Add Lead`.

### CSV Import
Use format:
```csv
Business Name,Email,Phone,Website,Location,Service
Example Business,owner@example.com,9812345678,,Delhi,Website Development
```

### Scraper CLI Examples
```bash
python scraper.py --niche "restaurant" --location "Delhi" --service "Website Development"
python scraper.py --niche "hotel" --location "Mumbai" --service "SEO"
python scraper.py --niche "gym" --location "Bangalore" --service "Branding"
```

## Campaign Variables

You can use these placeholders in templates:
- `{business}`
- `{service}`
- `{sender_name}`

## Suggested Production Notes

1. Respect your SMTP provider sending limits.
2. Keep delays between emails to reduce spam risk.
3. Scraping sources may rate-limit; add retry and pacing.
4. Back up your database regularly.

Database path:
`data/leads.db`

## Project Structure

```text
leadpro/
|-- app.py
|-- scraper.py
|-- requirements.txt
|-- START_WINDOWS.bat
|-- START_MAC_LINUX.sh
|-- data/
|   |-- leads.db
|-- templates/
|-- gmb_scraper/
```

## Version

LeadPro v1.0
