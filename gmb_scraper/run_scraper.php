<?php
/**
 * GMB Scraper PHP Wrapper
 * Executes the Node.js GMB scraper from PHP and returns parsed leads.
 *
 * Example usage:
 *   include 'gmb_scraper/run_scraper.php';
 *   $leads = runGMBScraper('Auckland', 'New Zealand', 'restaurant', 50);
 *   print_r($leads);
 */

/**
 * Run the GMB scraper and return an array of leads.
 *
 * @param string $city      City to search in
 * @param string $country   Country to search in
 * @param string $category  Business category (e.g. restaurant, cafe, plumber)
 * @param int    $limit     Maximum number of leads to collect
 * @param bool   $debug     Set true to print raw command output
 * @return array            Array of lead arrays, or empty array on failure
 */
function runGMBScraper(string $city, string $country, string $category, int $limit = 20, bool $debug = false): array
{
    // Path to the gmb_scraper directory (same directory as this file)
    $scraperDir  = __DIR__;
    $scraperScript = $scraperDir . DIRECTORY_SEPARATOR . 'scraper.js';
    $leadsDataDir  = realpath($scraperDir . DIRECTORY_SEPARATOR . '..' . DIRECTORY_SEPARATOR . 'leads_data');

    // Validate node is available
    exec('node --version 2>&1', $nodeOut, $nodeCode);
    if ($nodeCode !== 0) {
        error_log('GMB Scraper: node.js not found. Install Node.js 18+.');
        return [];
    }

    // Sanitize inputs (shell-escape each argument)
    $cityEsc     = escapeshellarg($city);
    $countryEsc  = escapeshellarg($country);
    $categoryEsc = escapeshellarg($category);
    $limitInt    = (int) $limit;

    // Build command
    // On Windows we prepend "node" explicitly
    $command = sprintf(
        'node %s --city=%s --country=%s --category=%s --limit=%d 2>&1',
        escapeshellarg($scraperScript),
        $cityEsc,
        $countryEsc,
        $categoryEsc,
        $limitInt
    );

    if ($debug) {
        echo "<pre>Running: $command</pre>";
    }

    // Execute (allow up to 10 minutes for large scrapes)
    $previousTimeout = ini_get('max_execution_time');
    set_time_limit(600);

    exec($command, $output, $exitCode);

    set_time_limit((int) $previousTimeout);

    if ($debug) {
        echo '<pre>' . htmlspecialchars(implode("\n", $output)) . '</pre>';
    }

    if ($exitCode !== 0) {
        error_log('GMB Scraper failed with exit code ' . $exitCode);
        return [];
    }

    // Find the most recently created JSON file matching this run
    if (!$leadsDataDir || !is_dir($leadsDataDir)) {
        error_log('GMB Scraper: leads_data directory not found at ' . $leadsDataDir);
        return [];
    }

    $safeCity     = preg_replace('/[^a-z0-9_\-]/', '_', strtolower($city));
    $safeCategory = preg_replace('/[^a-z0-9_\-]/', '_', strtolower($category));
    $pattern      = $leadsDataDir . DIRECTORY_SEPARATOR . "gmb_leads_{$safeCity}_{$safeCategory}_*.json";

    $files = glob($pattern);
    if (empty($files)) {
        error_log('GMB Scraper: no JSON output file found matching ' . $pattern);
        return [];
    }

    // Sort by modification time, newest first
    usort($files, fn($a, $b) => filemtime($b) - filemtime($a));
    $latestFile = $files[0];

    $raw = file_get_contents($latestFile);
    if ($raw === false) {
        error_log('GMB Scraper: could not read file ' . $latestFile);
        return [];
    }

    $data = json_decode($raw, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        error_log('GMB Scraper: JSON parse error — ' . json_last_error_msg());
        return [];
    }

    return $data['leads'] ?? [];
}

/**
 * Format leads as an HTML table (helper for quick display).
 *
 * @param array $leads  Return value of runGMBScraper()
 * @return string       HTML table string
 */
function leadsToHtmlTable(array $leads): string
{
    if (empty($leads)) {
        return '<p>No leads found.</p>';
    }

    $cols    = array_keys($leads[0]);
    $headers = implode('', array_map(fn($c) => "<th>" . htmlspecialchars($c) . "</th>", $cols));

    $rows = '';
    foreach ($leads as $lead) {
        $cells = implode('', array_map(fn($c) => "<td>" . htmlspecialchars($lead[$c] ?? '') . "</td>", $cols));
        $rows .= "<tr>$cells</tr>\n";
    }

    return "<table border='1' cellpadding='6' cellspacing='0'>\n<thead><tr>$headers</tr></thead>\n<tbody>\n$rows</tbody>\n</table>";
}


// ─── Quick Demo (only runs when this file is called directly) ─────────────────
if (php_sapi_name() === 'cli' && basename(__FILE__) === basename($_SERVER['SCRIPT_FILENAME'])) {
    echo "GMB Scraper PHP Wrapper — Demo Mode\n";
    echo "Running a 5-lead test scrape for Auckland restaurants…\n\n";

    $leads = runGMBScraper('Auckland', 'New Zealand', 'restaurant', 5, true);

    if (empty($leads)) {
        echo "No leads returned.\n";
    } else {
        echo "Leads found: " . count($leads) . "\n\n";
        foreach ($leads as $i => $lead) {
            echo ($i + 1) . ". " . ($lead['name'] ?? 'N/A') . "\n";
            echo "   Phone  : " . ($lead['phone']   ?? 'N/A') . "\n";
            echo "   Address: " . ($lead['address'] ?? 'N/A') . "\n";
            echo "   Rating : " . ($lead['rating']  ?? 'N/A') . "\n";
            echo "\n";
        }
    }
}
