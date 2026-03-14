// GMB Scraper Configuration
module.exports = {
  // Browser settings
  browser: {
    headless: true,           // Set to false to see the browser in action (useful for debugging)
    slowMo: 0,                // Slow down actions by N ms (useful for debugging)
    timeout: 30000,           // Default timeout in ms
    viewport: { width: 1280, height: 800 },
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
  },

  // Delay settings (in milliseconds) - randomized to avoid detection
  delays: {
    betweenBusinesses: { min: 2000, max: 5000 },   // Delay between processing each business
    afterScroll: { min: 1500, max: 3000 },           // Delay after scrolling the results list
    afterClick: { min: 1000, max: 2500 },             // Delay after clicking a business
    pageLoad: { min: 2000, max: 4000 },               // Delay waiting for page/panel to load
    betweenSearchRetries: { min: 3000, max: 6000 },   // Delay between retries
  },

  // Retry settings
  retries: {
    maxSearchRetries: 3,       // Max retries for the search page
    maxBusinessRetries: 2,     // Max retries for individual business pages
  },

  // Scraper limits
  limits: {
    defaultLimit: 20,          // Default number of leads if --limit not specified
    maxScrollAttempts: 60,     // More scrolls = more results loaded = more no-website businesses at the end
    scrollStepPx: 800,         // Larger scroll steps to reach bottom faster
  },

  // SEO analysis settings
  seo: {
    poorScoreThreshold: 60,   // Score below this = "poor SEO" lead (0-100)
    checkTimeout: 15000,      // Max ms to wait when loading a business website for SEO check
    // Scoring weights (deducted from 100 when issue found)
    weights: {
      noTitle: 20, titleTooShort: 10, titleTooLong: 5,
      noMetaDesc: 20, metaDescTooShort: 10, metaDescTooLong: 5,
      noH1: 15, multipleH1: 8,
      noHttps: 15,
      notMobileFriendly: 15,
      imagesNoAlt: 8,
      noSchema: 7,
      noCanonical: 5,
    },
  },

  // Output settings
  output: {
    directory: '../leads_data',  // Output directory relative to gmb_scraper folder
    csvHeaders: [
      { id: 'name', title: 'name' },
      { id: 'phone', title: 'phone' },
      { id: 'email', title: 'email' },
      { id: 'address', title: 'address' },
      { id: 'city', title: 'city' },
      { id: 'country', title: 'country' },
      { id: 'category', title: 'category' },
      { id: 'rating', title: 'rating' },
      { id: 'reviews', title: 'reviews' },
      { id: 'gmb_url', title: 'gmb_url' },
      { id: 'has_website', title: 'has_website' },
      { id: 'website_url', title: 'website_url' },
      { id: 'lead_type', title: 'lead_type' },
      { id: 'seo_score', title: 'seo_score' },
      { id: 'seo_issues', title: 'seo_issues' },
    ],
  },

  // CAPTCHA detection strings
  captcha: {
    indicators: [
      'captcha',
      'unusual traffic',
      'automated queries',
      'verify you',
      'not a robot',
      'recaptcha',
    ],
  },

  // Google Maps selectors (update if Google changes their UI)
  selectors: {
    searchBox: 'input#searchboxinput',
    searchButton: 'button#searchbox-searchbutton',
    resultsPanel: 'div[role="feed"]',
    resultItem: 'div[role="feed"] > div > div[jsaction]',
    businessName: 'h1.DUwDvf, h1[data-attrid="title"]',
    address: 'button[data-item-id="address"] .Io6YTe, [data-item-id="address"] .fontBodyMedium',
    phone: 'button[data-item-id^="phone"] .Io6YTe, [data-tooltip="Copy phone number"] .fontBodyMedium',
    websiteButton: 'a[data-item-id="authority"], a[href*="website"], button[data-item-id="authority"]',
    rating: 'div.F7nice span[aria-hidden="true"]',
    reviewCount: 'div.F7nice span[aria-label*="review"]',
    category: 'button.DkEaL',
  },
};
