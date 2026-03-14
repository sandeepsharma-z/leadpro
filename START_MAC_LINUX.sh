#!/bin/bash
echo ""
echo " =========================================="
echo "  LeadPro - Lead Generation Engine v1.0"
echo " =========================================="
echo ""

# Install dependencies
echo "[1/3] Installing dependencies..."
pip3 install flask requests beautifulsoup4 lxml pypdf python-docx openpyxl -q 2>/dev/null || pip install flask requests beautifulsoup4 lxml pypdf python-docx openpyxl -q

# Create data folder
mkdir -p data

echo "[2/3] Starting LeadPro server..."
echo ""
echo "  Open your browser at: http://localhost:5000"
echo "  Press Ctrl+C to stop"
echo ""

# Open browser (Mac)
sleep 2 && open http://localhost:5000 2>/dev/null &

# Run the app
python3 app.py || python app.py

