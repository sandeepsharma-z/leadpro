#!/usr/bin/env node
/**
 * GMB Lead Scraper
 * Scrapes Google Maps for businesses WITHOUT websites
 * Usage: node scraper.js --city="Auckland" --country="New Zealand" --category="restaurant" --limit=50
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const minimist = require('minimist');
const { createObjectCsvWriter } = require('csv-writer');
const config = require('./config');

// ─── Parse CLI Arguments ────────────────────────────────────────────────────
const args = minimist(process.argv.slice(2), {
  string: ['city', 'country', 'category'],
  number: ['limit'],
  default: {
    city: 'Auckland',
    country: 'New Zealand',
    category: 'restaurant',
    limit: config.limits.defaultLimit,
  },
});

const { city, country, category, limit } = args;

// ─── Helpers ────────────────────────────────────────────────────────────────
function randomDelay(range) {
  const ms = Math.floor(Math.random() * (range.max - range.min + 1)) + range.min;
  return new Promise((r) => setTimeout(r, ms));
}

function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
}

function log(msg, level = 'INFO') {
  const time = new Date().toLocaleTimeString();
  const prefix = { INFO: '  ', WARN: '⚠ ', ERROR: '✗ ', OK: '✓ ' }[level] || '  ';
  console.log(`[${time}] ${prefix} ${msg}`);
}

function sanitizeFilename(str) {
  return str.replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
}

function collectEmailsFromText(text) {
  if (!text) return [];
  const decoded = String(text)
    .replace(/\s*\[at\]\s*/gi, '@')
    .replace(/\s*\(at\)\s*/gi, '@')
    .replace(/\s+at\s+/gi, '@')
    .replace(/\s*\[dot\]\s*/gi, '.')
    .replace(/\s*\(dot\)\s*/gi, '.')
    .replace(/\s+dot\s+/gi, '.');
  const matches = decoded.match(/[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g) || [];
  const cleaned = matches
    .map((e) => e.toLowerCase().trim().replace(/^[<>"'(\[]+|[<>"')\].,;:!?]+$/g, ''))
    .filter((e) => e && !e.includes('example') && !e.includes('@2x') && !e.includes('sentry'));
  return [...new Set(cleaned)];
}

// ─── SEO Checker ─────────────────────────────────────────────────────────────
async function checkWebsiteSEO(page, websiteUrl) {
  const w = config.seo.weights;
  const issues = [];
  let score = 100;

  try {
    await page.goto(websiteUrl, { waitUntil: 'domcontentloaded', timeout: config.seo.checkTimeout });

    // 1. Page Title
    const title = await page.title().catch(() => '');
    if (!title.trim())            { issues.push('No page title');          score -= w.noTitle; }
    else if (title.length < 20)   { issues.push('Title too short');        score -= w.titleTooShort; }
    else if (title.length > 65)   { issues.push('Title too long');         score -= w.titleTooLong; }

    // 2. Meta Description
    const metaDesc = await page.$eval('meta[name="description"]', el => el.getAttribute('content') || '').catch(() => '');
    if (!metaDesc.trim())            { issues.push('No meta description');       score -= w.noMetaDesc; }
    else if (metaDesc.length < 50)   { issues.push('Meta desc too short');       score -= w.metaDescTooShort; }
    else if (metaDesc.length > 165)  { issues.push('Meta desc too long');        score -= w.metaDescTooLong; }

    // 3. H1 Tag
    const h1Count = await page.$$eval('h1', els => els.length).catch(() => 0);
    if (h1Count === 0)      { issues.push('No H1 heading');              score -= w.noH1; }
    else if (h1Count > 1)   { issues.push(`Multiple H1s (${h1Count})`);  score -= w.multipleH1; }

    // 4. HTTPS
    if (!websiteUrl.startsWith('https://')) {
      issues.push('No HTTPS (insecure)');
      score -= w.noHttps;
    }

    // 5. Mobile Viewport
    const hasViewport = await page.$('meta[name="viewport"]').catch(() => null);
    if (!hasViewport) { issues.push('Not mobile-friendly');  score -= w.notMobileFriendly; }

    // 6. Images missing alt text
    const missingAlt = await page.$$eval('img', imgs => imgs.filter(img => !img.getAttribute('alt')).length).catch(() => 0);
    if (missingAlt > 2) { issues.push(`${missingAlt} images missing alt`);  score -= w.imagesNoAlt; }

    // 7. Schema / Structured Data
    const hasSchema = await page.$('script[type="application/ld+json"]').catch(() => null);
    if (!hasSchema) { issues.push('No schema markup');  score -= w.noSchema; }

    // 8. Canonical Tag
    const canonical = await page.$('link[rel="canonical"]').catch(() => null);
    if (!canonical) { issues.push('No canonical tag');  score -= w.noCanonical; }

    // 9. Email extraction — mailto links (most reliable) then body text
    let websiteEmail = '';
    try {
      const mailtos = await page.$$eval('a[href^="mailto:"]',
        els => els.map(el => el.href.replace('mailto:', '').split('?')[0].trim())
                  .filter(e => e && e.includes('@') && !e.includes('example'))
      );
      if (mailtos.length) websiteEmail = mailtos[0];
    } catch(_) {}

    if (!websiteEmail) {
      try {
        const bodyText = await page.innerText('body').catch(() => '');
        const emails = collectEmailsFromText(bodyText);
        if (emails.length) websiteEmail = emails[0];
      } catch(_) {}
    }

    return { score: Math.max(0, score), issues, checked: true, email: websiteEmail };
  } catch (e) {
    return { score: null, issues: ['Could not load website'], checked: false, email: '' };
  }
}

// ─── CAPTCHA Detection ───────────────────────────────────────────────────────
async function checkForCaptcha(page) {
  const content = (await page.content()).toLowerCase();
  for (const indicator of config.captcha.indicators) {
    if (content.includes(indicator)) {
      return true;
    }
  }
  return false;
}

// ─── Extract Business Details ─────────────────────────────────────────────────
async function extractBusinessDetails(page, gmbUrl, cityArg, countryArg, categoryArg) {
  const details = {
    name: '',
    phone: '',
    email: '',
    address: '',
    city: cityArg,
    country: countryArg,
    category: categoryArg,
    rating: '',
    reviews: '',
    gmb_url: gmbUrl,
    has_website: 'No',
    website_url: '',
    lead_type: 'no_website',
    seo_score: '',
    seo_issues: '',
  };

  try {
    // Business name
    const nameEl = await page.$(config.selectors.businessName);
    if (nameEl) details.name = (await nameEl.innerText()).trim();

    // Check for website button
    // The "authority" link points to the business's external website (not google.com)
    const websiteEl = await page.$('a[data-item-id="authority"]');
    if (websiteEl) {
      const href = await websiteEl.getAttribute('href') || '';
      // Only count as website if the link goes to an external non-Google URL
      if (href && !href.includes('google.com') && !href.startsWith('/') && href.startsWith('http')) {
        details.has_website = 'Yes';
        details.website_url = href;
        // Don't return early — caller will check SEO
      }
    }

    // Address
    try {
      const addrEl = await page.$('button[data-item-id="address"]');
      if (addrEl) {
        const raw = await addrEl.innerText();
        // Remove Private Use Area / Powerline font chars and clean up
        details.address = raw.replace(/[\uE000-\uF8FF]/g, '').replace(/\n/g, ', ').trim().replace(/^,\s*/, '');
      }
    } catch (_) {}

    // Phone
    try {
      const phoneEl = await page.$('button[data-item-id^="phone:tel"]');
      if (phoneEl) {
        const raw = await phoneEl.innerText();
        // Extract only phone digits, +, spaces, hyphens, parentheses
        const match = raw.match(/[\+\d][\d\s\-().]{5,}/);
        details.phone = match ? match[0].trim() : raw.replace(/[^\d\s+\-(). ]/g, '').trim();
      }
    } catch (_) {}

    // Rating
    try {
      const ratingEl = await page.$('div.F7nice span[aria-hidden="true"]');
      if (ratingEl) details.rating = (await ratingEl.innerText()).trim();
    } catch (_) {}

    // Reviews count
    try {
      const reviewEl = await page.$('div.F7nice span[aria-label]');
      if (reviewEl) {
        const label = await reviewEl.getAttribute('aria-label');
        const match = label && label.match(/([\d,]+)/);
        if (match) details.reviews = match[1].replace(/,/g, '');
      }
    } catch (_) {}

    // Category (from type button near top)
    try {
      const catEl = await page.$('button.DkEaL');
      if (catEl) details.category = (await catEl.innerText()).trim();
    } catch (_) {}

    // Email — Google Maps rarely shows email; try mailto + page text (including obfuscated patterns)
    try {
      let candidates = [];

      // 1) any visible mailto links
      try {
        const mailtos = await page.$$eval('a[href^="mailto:"]', (els) =>
          els.map((el) => (el.getAttribute('href') || '').replace(/^mailto:/i, '').split('?')[0].trim())
        );
        candidates.push(...mailtos);
      } catch (_) {}

      // 2) full panel text
      const pageText = await page.innerText('body').catch(() => '');
      candidates.push(...collectEmailsFromText(pageText));

      // 3) aria-labels and button text often contain contact details in Maps
      try {
        const labels = await page.$$eval('[aria-label]', (els) =>
          els.map((el) => el.getAttribute('aria-label') || '')
        );
        candidates.push(...collectEmailsFromText(labels.join(' | ')));
      } catch (_) {}

      const finalEmails = collectEmailsFromText(candidates.join(' | '));
      if (finalEmails.length) details.email = finalEmails[0];
    } catch (_) {}
  } catch (err) {
    log(`Error extracting details: ${err.message}`, 'WARN');
  }

  return details;
}

// ─── Scroll Results List to Load More ─────────────────────────────────────────
async function scrollResultsList(page, targetCount) {
  let previousCount = 0;
  let noChangeAttempts = 0;

  for (let i = 0; i < config.limits.maxScrollAttempts; i++) {
    // Count currently loaded result items
    const items = await page.$$(config.selectors.resultItem);
    const currentCount = items.length;

    if (currentCount >= targetCount) {
      log(`Loaded ${currentCount} results (target: ${targetCount})`);
      break;
    }

    if (currentCount === previousCount) {
      noChangeAttempts++;
      if (noChangeAttempts >= 3) {
        log(`No more results loading after ${currentCount} items`, 'WARN');
        break;
      }
    } else {
      noChangeAttempts = 0;
    }

    previousCount = currentCount;

    // Scroll inside the results feed panel
    const feed = await page.$(config.selectors.resultsPanel);
    if (feed) {
      await feed.evaluate((el, px) => { el.scrollTop += px; }, config.limits.scrollStepPx);
    } else {
      await page.evaluate((px) => { window.scrollBy(0, px); }, config.limits.scrollStepPx);
    }

    await randomDelay(config.delays.afterScroll);
  }

  return await page.$$(config.selectors.resultItem);
}

// ─── Main Scraper ─────────────────────────────────────────────────────────────
async function scrape() {
  console.log('\n══════════════════════════════════════════');
  console.log('  GMB Lead Scraper — Businesses Without Websites');
  console.log('══════════════════════════════════════════');
  console.log(`  City     : ${city}`);
  console.log(`  Country  : ${country}`);
  console.log(`  Category : ${category}`);
  console.log(`  Limit    : ${limit}`);
  console.log('══════════════════════════════════════════\n');

  // Ensure output directory exists
  const outputDir = path.resolve(__dirname, config.output.directory);
  if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

  const ts = timestamp();
  const safeCity = sanitizeFilename(city);
  const safeCat = sanitizeFilename(category);
  const baseName = `gmb_leads_${safeCity}_${safeCat}_${ts}`;
  const csvPath = path.join(outputDir, `${baseName}.csv`);
  const jsonPath = path.join(outputDir, `${baseName}.json`);

  const csvWriter = createObjectCsvWriter({
    path: csvPath,
    header: config.output.csvHeaders,
  });

  const leads = [];
  const seenNames = new Set();
  let skipped = 0;
  let errors = 0;

  let browser;
  try {
    log('Launching browser…');
    browser = await chromium.launch({
      headless: config.browser.headless,
      slowMo: config.browser.slowMo,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled'],
    });

    const context = await browser.newContext({
      userAgent: config.browser.userAgent,
      viewport: config.browser.viewport,
      locale: 'en-US',
    });

    // Block images and fonts to speed things up
    await context.route('**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot}', (route) => route.abort());

    const page = await context.newPage();
    page.setDefaultTimeout(config.browser.timeout);

    // ── Open Google Maps ──
    const searchQuery = `${category} in ${city}, ${country}`;
    const mapsUrl = `https://www.google.com/maps/search/${encodeURIComponent(searchQuery)}`;
    log(`Navigating to Google Maps: "${searchQuery}"`);

    await page.goto(mapsUrl, { waitUntil: 'networkidle', timeout: 45000 });
    await randomDelay(config.delays.pageLoad);

    // CAPTCHA check
    if (await checkForCaptcha(page)) {
      log('CAPTCHA detected! Aborting scraper. Try again later or use a VPN.', 'ERROR');
      await browser.close();
      process.exit(1);
    }

    // Accept cookies dialog if present
    try {
      const acceptBtn = await page.$('button[aria-label="Accept all"], form[action*="consent"] button');
      if (acceptBtn) {
        await acceptBtn.click();
        await randomDelay(config.delays.afterClick);
      }
    } catch (_) {}

    // Wait for results panel
    try {
      await page.waitForSelector(config.selectors.resultsPanel, { timeout: 15000 });
    } catch (_) {
      log('Results panel not found — Google Maps layout may have changed', 'ERROR');
      await browser.close();
      process.exit(1);
    }

    // ── Scroll to load enough results & collect place URLs ──
    // Load 4x the limit so we have plenty of lesser-known businesses at the bottom
    log(`Scrolling results to load at least ${limit * 4} items (more = better no-website chances)…`);
    await scrollResultsList(page, limit * 4);

    // Collect all place URLs from the result anchors (avoids click-and-back fragility)
    // Then REVERSE: less popular businesses (at the end) are more likely to have no website
    const placeUrls = await page.$$eval(
      'div[role="feed"] a[href*="/maps/place/"]',
      (anchors) => [...new Set(anchors.map((a) => a.href).filter((h) => h.includes('/maps/place/')))].reverse(),
    );
    log(`Found ${placeUrls.length} place URLs to process (starting from least popular)`, 'OK');

    if (placeUrls.length === 0) {
      log('No place URLs found. Google Maps may have changed its structure.', 'ERROR');
      await browser.close();
      return;
    }

    // ── Process each place URL directly ──
    let processed = 0;
    for (const placeUrl of placeUrls) {
      if (leads.length >= limit) break;
      processed++;
      const progress = `[${leads.length}/${limit} leads | item ${processed}/${placeUrls.length}]`;

      try {
        await page.goto(placeUrl, { waitUntil: 'networkidle', timeout: 30000 });
        await randomDelay(config.delays.afterClick);

        // Wait for the detail panel to load
        try {
          await page.waitForSelector(config.selectors.businessName, { timeout: 10000 });
        } catch (_) {
          log(`${progress} Detail panel didn't load, skipping`, 'WARN');
          errors++;
          continue;
        }

        const currentUrl = page.url();

        // CAPTCHA check mid-scrape
        if (await checkForCaptcha(page)) {
          log('CAPTCHA detected mid-scrape! Saving progress and aborting.', 'ERROR');
          break;
        }

        // Extract details
        const details = await extractBusinessDetails(page, currentUrl, city, country, category);

        if (!details.name) {
          log(`${progress} SKIP — could not extract business name`, 'WARN');
          errors++;
        } else if (seenNames.has(details.name)) {
          log(`${progress} SKIP "${details.name}" — duplicate`, 'WARN');
        } else if (details.has_website === 'Yes') {
          // Business has a website — check if SEO is poor
          log(`${progress} Has website — checking SEO for "${details.name}"…`);
          const seo = await checkWebsiteSEO(page, details.website_url);

          if (seo && seo.checked && seo.score < config.seo.poorScoreThreshold) {
            details.lead_type = 'poor_seo';
            details.seo_score = seo.score;
            details.seo_issues = seo.issues.join('; ');
            if (seo.email) details.email = seo.email;
            seenNames.add(details.name);
            leads.push(details);
            log(`${progress} SEO LEAD "${details.name}" | Score: ${seo.score}/100 | Email: ${seo.email || 'not found'} | Issues: ${seo.issues.join(', ')}`, 'OK');
          } else {
            const scoreStr = (seo && seo.checked) ? `score ${seo.score}/100 — good SEO` : 'could not check website';
            log(`${progress} SKIP "${details.name}" — website OK (${scoreStr})`, 'WARN');
            skipped++;
          }
        } else {
          details.lead_type = 'no_website';
          seenNames.add(details.name);
          leads.push(details);
          log(`${progress} NO-WEBSITE LEAD "${details.name}" | ${details.phone || 'no phone'} | ${details.address || 'no address'}`, 'OK');
        }

        await randomDelay(config.delays.betweenBusinesses);

      } catch (err) {
        log(`Error on item ${processed}: ${err.message}`, 'ERROR');
        errors++;
        await randomDelay(config.delays.betweenSearchRetries);
      }
    }

    await browser.close();

    // ── Save Results ──
    const noWebsiteCount = leads.filter(l => l.lead_type === 'no_website').length;
    const poorSeoCount = leads.filter(l => l.lead_type === 'poor_seo').length;
    console.log('\n══════════════════════════════════════════');
    log(`Scraping complete!`, 'OK');
    log(`  Total leads      : ${leads.length}`);
    log(`  No website leads : ${noWebsiteCount}`);
    log(`  Poor SEO leads   : ${poorSeoCount}`);
    log(`  Skipped (good)   : ${skipped}`);
    log(`  Errors           : ${errors}`);
    console.log('══════════════════════════════════════════');

    if (leads.length === 0) {
      log('No leads found. Try a different city/category or check if Google Maps layout has changed.', 'WARN');
      return;
    }

    // Write CSV
    await csvWriter.writeRecords(leads);
    log(`CSV saved : ${csvPath}`, 'OK');

    // Write JSON
    fs.writeFileSync(jsonPath, JSON.stringify({ meta: { city, country, category, limit, total: leads.length, timestamp: new Date().toISOString() }, leads }, null, 2));
    log(`JSON saved: ${jsonPath}`, 'OK');

    console.log('\nDone! Files saved to leads_data/\n');

  } catch (err) {
    log(`Fatal error: ${err.message}`, 'ERROR');
    if (browser) await browser.close().catch(() => {});
    process.exit(1);
  }
}

scrape();
