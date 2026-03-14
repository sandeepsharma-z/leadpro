# ⚡ LeadPro - Lead Generation + Bulk Email Engine

Apna complete lead generation aur bulk email system — 100% local, 24/7 running.

---

## 🚀 SETUP (5 Minutes)

### Step 1: Python Install Karo
Download karo: https://www.python.org/downloads/
✅ Installation mein "Add Python to PATH" checkbox zaroor tick karo

### Step 2: LeadPro Start Karo

**Windows pe:**
```
START_WINDOWS.bat  ← Double click karo
```

**Mac/Linux pe:**
```bash
chmod +x START_MAC_LINUX.sh
./START_MAC_LINUX.sh
```

### Step 3: Browser Open Karo
http://localhost:5000

---

## ⚙️ PEHLI BAAR SETUP

### Email Configure Karo (Settings Page)
1. http://localhost:5000/settings pe jao
2. Fill karo:
   - **SMTP Host**: smtp.hostinger.com
   - **SMTP Port**: 465
   - **Email**: apna@yourdomain.com (Hostinger wala)
   - **Password**: Hostinger email password
   - **Sender Name**: Teri Agency ka naam
3. "Save Settings" click karo
4. "Test Connection" se verify karo

---

## 📋 KAISE USE KARO

### METHOD 1: Manual Lead Add
1. Dashboard pe "Quick Add Lead" form bharo
2. Business name, email, phone, service select karo
3. "Add Lead" click karo

### METHOD 2: CSV Import (Bulk)
1. Dashboard pe CSV format mein leads paste karo:
   ```
   Business Name, Email, Phone, Website, Location, Service
   Sharma Dhaba, sharma@gmail.com, 9812345678, , Delhi, Website Development
   ```
2. "Import Leads" click karo

### METHOD 3: Auto Scraper
```bash
# Restaurants in Delhi jo website development chahte hain
python scraper.py --niche "restaurant" --location "Delhi" --service "Website Development"

# Hotels in Mumbai for SEO
python scraper.py --niche "hotel" --location "Mumbai" --service "SEO"

# Gyms in Bangalore for branding
python scraper.py --niche "gym" --location "Bangalore" --service "Branding"
```

---

## 📧 EMAIL CAMPAIGNS

### Campaign Banao
1. http://localhost:5000/campaigns pe jao
2. Service select karo (template auto-load hoga)
3. Subject aur body customize karo
4. "Save Campaign" click karo

### Bulk Email Bhejo
1. http://localhost:5000/leads pe jao
2. Leads select karo (checkbox use karo)
3. "Send Emails" click karo
4. Campaign select karo
5. "Start Sending" — ho gaya! 🚀

### Variables jo use kar sakte ho
- `{business}` — Business ka naam
- `{service}` — Service naam
- `{sender_name}` — Teri agency ka naam

---

## 📊 SERVICES INCLUDED
- ✅ Website Development
- ✅ SEO (Search Engine Optimization)  
- ✅ Logo Design
- ✅ Social Media Management
- ✅ App Development
- ✅ E-commerce Solutions
- ✅ UI/UX Design
- ✅ Branding & Graphic Design
- ✅ CMS Development
- ✅ Website Maintenance

---

## 🔄 24/7 RUN KARNE KE LIYE

### Windows (Task Scheduler):
1. Task Scheduler open karo
2. "Create Basic Task" → "When computer starts"
3. Action: Start a program → python → Arguments: `C:\path\to\leadpro\app.py`

### Background mein run karo (Windows):
```batch
start /min python app.py
```

---

## ⚠️ IMPORTANT NOTES

1. **Hostinger Limits**: Shared hosting pe ~200-500 emails/day allowed
2. **Delay**: Minimum 3 seconds between emails (spam avoid karne ke liye)
3. **Scraper**: Google kabhi kabhi block kar sakta hai, VPN use karo ya slow karo
4. **Database**: `data/leads.db` mein sab data save hota hai — backup lena mat bhoolna!

---

## 🗂️ FILES
```
leadpro/
├── app.py              ← Main server (ye hi run karo)
├── scraper.py          ← Lead scraper
├── requirements.txt    ← Dependencies
├── START_WINDOWS.bat   ← Windows startup
├── START_MAC_LINUX.sh  ← Mac/Linux startup
├── data/
│   └── leads.db        ← Database (auto-create hoga)
└── templates/          ← HTML pages
```

---

Made with ❤️ for Indian agencies | LeadPro v1.0
