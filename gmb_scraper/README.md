# GMB Lead Scraper

Scrapes **Google Maps** for businesses that **do NOT have a website** — your hottest leads.

---

## Requirements

| Tool | Minimum version |
|------|----------------|
| Node.js | 18+ |
| npm | 9+ |
| PHP (optional) | 7.4+ |

---

## Installation

```bash
# 1. Navigate into the scraper folder
cd C:\wamp64\www\LeadPro\gmb_scraper

# 2. Install Node dependencies
npm install

# 3. Install Playwright's Chromium browser
npx playwright install chromium
```

---

## Usage

### Basic command

```bash
node scraper.js --city="Auckland" --country="New Zealand" --category="restaurant" --limit=50
```

### Test run (5 leads only — do this first!)

```bash
npm test
# or
node scraper.js --city="Auckland" --country="New Zealand" --category="cafe" --limit=5
```

### More examples

```bash
# Plumbers in Sydney
node scraper.js --city="Sydney" --country="Australia" --category="plumber" --limit=30

# Dentists in London
node scraper.js --city="London" --country="United Kingdom" --category="dentist" --limit=25

# Hairdressers in Toronto
node scraper.js --city="Toronto" --country="Canada" --category="hair salon" --limit=40

# Electricians in Cape Town
node scraper.js --city="Cape Town" --country="South Africa" --category="electrician" --limit=20
```

---

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--city` | Auckland | Target city |
| `--country` | New Zealand | Target country |
| `--category` | restaurant | Business type (any GMB category) |
| `--limit` | 20 | Maximum number of leads to collect |

---

## Output

Results are saved to `C:\wamp64\www\LeadPro\leads_data\` in two formats:

- **CSV**: `gmb_leads_{city}_{category}_{timestamp}.csv`
- **JSON**: `gmb_leads_{city}_{category}_{timestamp}.json`

### CSV columns

| Column | Description |
|--------|-------------|
| `name` | Business name |
| `phone` | Phone number |
| `email` | Email (if visible on GMB page) |
| `address` | Full street address |
| `city` | City searched |
| `country` | Country searched |
| `category` | Business category |
| `rating` | Google star rating |
| `reviews` | Number of reviews |
| `gmb_url` | Direct Google Maps URL |
| `has_website` | Always "No" for collected leads |

---

## PHP Integration

```php
<?php
// From any PHP file in the LeadPro project:
include 'gmb_scraper/run_scraper.php';

// Run the scraper
$leads = runGMBScraper('Auckland', 'New Zealand', 'restaurant', 50);

// Use the leads
foreach ($leads as $lead) {
    echo $lead['name'] . ' — ' . $lead['phone'] . PHP_EOL;
}

// Or display as an HTML table
echo leadsToHtmlTable($leads);
?>
```

### Run PHP wrapper from CLI (test)

```bash
php gmb_scraper/run_scraper.php
```

---

## Configuration (`config.js`)

Key settings you can tweak:

```js
browser: {
  headless: true,   // Set false to watch the browser (good for debugging)
},
delays: {
  betweenBusinesses: { min: 2000, max: 5000 },  // ms — increase if getting blocked
},
```

---

## Troubleshooting

### "Results panel not found"
Google Maps changed their HTML. Try running with `headless: false` in `config.js` to see what's happening visually.

### CAPTCHA detected
- Slow down: increase delay values in `config.js`
- Use a VPN
- Run at off-peak hours
- Use a residential proxy (advanced)

### "No leads found"
- The category may not exist exactly — try broader terms (`cafe` → `coffee shop`)
- Google Maps may have returned 0 results for that city/category combination
- Selectors may need updating — see `config.js → selectors`

### Playwright browser install fails
```bash
# Try forcing reinstall
npx playwright install --force chromium
```

### Node version error
```bash
node --version   # must be 18+
# If older, download Node 18+ from https://nodejs.org
```

### Windows path issues
All paths use `path.join()` internally — should work on Windows automatically.

---

## Rate Limiting Tips

- Start with `--limit=5` to test
- Run no more than 3–4 searches per hour
- Add longer delays in `config.js` for large batches
- Do not run multiple instances simultaneously

---

## Updating Selectors

If the scraper stops working after a Google Maps update, the HTML selectors in `config.js` need updating:

1. Open `config.js` → find the `selectors` section
2. Open Google Maps in Chrome DevTools
3. Inspect the element and update the selector string

---

## Legal Notice

This tool is for personal business research only. Use responsibly and in accordance with Google's Terms of Service. Do not use for mass automated scraping.
