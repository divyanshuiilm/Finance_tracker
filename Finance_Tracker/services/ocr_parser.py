"""Smart parser for UPI receipt and screenshot text (Google Pay, PhonePe, Paytm, BHIM, etc.)."""

import re
from datetime import date, datetime
from typing import Any, Dict, Optional


CATEGORY_KEYWORDS = {
    "Food": [
        "swiggy", "zomato", "canteen", "cafe", "coffee", "restaurant", "pizza",
        "burger", "starbucks", "mcdonald", "kfc", "dhaba", "bakery", "tea",
        "chai", "biryani", "supermarket", "grocery", "zepto", "blinkit",
        "instamart", "bigbasket", "eats", "food", "kitchen", "hotel", "mess"
    ],
    "Transport": [
        "uber", "ola", "rapido", "metro", "irctc", "train", "bus", "flight",
        "indigo", "petrol", "fuel", "shell", "hpcl", "bpcl", "ioc", "auto",
        "cab", "parking", "toll", "fastag", "railway", "airways"
    ],
    "College": [
        "college", "university", "tuition", "fees", "books", "xerox", "print",
        "stationery", "exam", "library", "course", "udemy", "coursera",
        "school", "campus", "hostel", "education"
    ],
    "Entertainment": [
        "netflix", "spotify", "prime", "hotstar", "youtube", "pvr", "inox",
        "cinepolis", "bookmyshow", "game", "steam", "playstation", "movies",
        "theatre", "concert", "event"
    ],
    "Shopping": [
        "amazon", "flipkart", "myntra", "zara", "h&m", "ajio", "meesho",
        "nykaa", "clothing", "mall", "retail", "store", "mart", "bazaar"
    ],
    "Bills": [
        "bescom", "electricity", "water", "wifi", "broadband", "jio", "airtel",
        "vi", "vodafone", "recharge", "rent", "maintenance", "gas", "indane",
        "cylinder", "bill", "utility", "dth", "tatasky"
    ],
    "Health": [
        "apollo", "pharmacy", "medplus", "hospital", "clinic", "doctor",
        "medicine", "netmeds", "pharmeasy", "1mg", "gym", "fitness", "cult",
        "diagnostic", "dental", "care"
    ],
    "Investment": [
        "zerodha", "groww", "angel", "upstox", "mutual fund", "sip", "coin",
        "kuvera", "smallcase", "indmoney", "stocks", "shares"
    ],
    "Savings": [
        "savings", "deposit", "fd", "rd", "emergency", "reserve"
    ],
}


def parse_upi_text(raw_text: str) -> Dict[str, Any]:
    """Extract payment fields (amount, merchant, date, type, category) from OCR text."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    full_text = " ".join(lines)
    lower_text = full_text.lower()

    # 1. Determine Transaction Type
    is_income = any(keyword in lower_text for keyword in [
        "received from", "credited to", "cashback", "refund", "received ₹", "received rs"
    ])
    transaction_type = "income" if is_income else "expense"

    # 2. Extract Amount
    amount = extract_amount(lines, full_text)

    # 3. Extract Merchant / Recipient Name
    merchant = extract_merchant(lines, full_text)

    # 4. Extract Date
    transaction_date = extract_date(lines, full_text) or date.today().isoformat()

    # 5. Smart Category Detection
    category = detect_category(merchant, full_text)

    return {
        "transaction_type": transaction_type,
        "amount": amount,
        "transaction_date": transaction_date,
        "category": category,
        "payment_method": "UPI",
        "merchant": merchant,
        "note": f"Scanned from UPI receipt" if merchant else "",
        "raw_snippet": full_text[:200]
    }


def extract_amount(lines: list, full_text: str) -> Optional[float]:
    """Find rupee amounts in OCR text."""
    # Pattern 1: Symbol or label with currency (₹, Rs, INR) followed by number
    currency_patterns = [
        r"(?:₹|rs\.?|inr)\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?)",
        r"([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{2}))\s*(?:paid|sent|received|successful)",
        r"(?:paid|sent|amount|transfer)\s*(?:of)?\s*(?:₹|rs\.?|inr)?\s*([0-9]+(?:\.[0-9]{1,2})?)",
        r"(?:total|amount)\s*[:=]?\s*(?:₹|rs\.?|inr)?\s*([0-9]+(?:\.[0-9]{1,2})?)",
    ]

    for pattern in currency_patterns:
        matches = re.findall(pattern, full_text, flags=re.IGNORECASE)
        for match in matches:
            cleaned = match.replace(",", "").strip()
            try:
                val = float(cleaned)
                if 0.5 <= val <= 1000000:
                    return round(val, 2)
            except ValueError:
                continue

    # Fallback: scan lines for isolated monetary values
    for line in lines:
        match = re.search(r"^₹?\s*([0-9]+(?:\.[0-9]{2})?)$", line.strip())
        if match:
            try:
                val = float(match.group(1))
                if 0.5 <= val <= 1000000:
                    return round(val, 2)
            except ValueError:
                pass

    return None


def extract_merchant(lines: list, full_text: str) -> Optional[str]:
    """Extract recipient or merchant name from UPI text."""
    # Regex patterns for common UPI apps (GPay, PhonePe, Paytm, BHIM)
    merchant_patterns = [
        r"(?:paid to|payment to|sent to|transfer to|to:)\s+([A-Za-z0-9\s&'.\-]+?)(?:\s+(?:₹|rs|on|using|upi|success|completed|\d{1,2})|$)",
        r"(?:received from|from:)\s+([A-Za-z0-9\s&'.\-]+?)(?:\s+(?:₹|rs|on|using|upi|success|completed|\d{1,2})|$)",
        r"banking name\s*[:\-]?\s*([A-Za-z0-9\s&'.\-]+)",
        r"upi id\s*[:\-]?\s*([a-zA-Z0-9.\-_]+@[a-zA-Z]+)",
    ]

    for pattern in merchant_patterns:
        match = re.search(pattern, full_text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            candidate = clean_merchant_name(candidate)
            if candidate and len(candidate) >= 2:
                return candidate

    # Line-by-line inspection
    ignore_words = {
        "google pay", "phonepe", "paytm", "bhim", "upi", "completed", "successful",
        "transaction", "payment", "paid", "received", "details", "share", "view",
        "home", "done", "help", "rupee", "bank", "account", "check balance"
    }

    for i, line in enumerate(lines):
        lower_line = line.lower()
        if any(trigger in lower_line for trigger in ["paid to", "to ", "sent to"]):
            name = re.sub(r"^(?:paid to|to|sent to)\s*", "", line, flags=re.IGNORECASE).strip()
            name = clean_merchant_name(name)
            if name:
                return name
        # If a line follows "To"
        if lower_line == "to" and i + 1 < len(lines):
            next_line = clean_merchant_name(lines[i + 1])
            if next_line and next_line.lower() not in ignore_words:
                return next_line

    return None


def clean_merchant_name(name: str) -> str:
    """Clean up extracted merchant strings."""
    # Remove unwanted trailing/leading punctuation and symbols
    cleaned = re.sub(r"[^A-Za-z0-9\s&'.\-@]", "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Filter out common UI noise words
    noise = ["completed", "successful", "upi ref", "transaction id", "view details", "paid", "rupees"]
    for word in noise:
        cleaned = re.sub(rf"(?i)\b{word}\b", "", cleaned).strip()

    return cleaned.title() if cleaned else ""


MONTH_PATTERN = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"


def extract_date(lines: list, full_text: str) -> Optional[str]:
    """Parse transaction dates into ISO YYYY-MM-DD format."""
    current_year = date.today().year

    # 1. Format: 24 Aug 2026, 24 August 2026, 24 Aug, 2026
    pattern_dmy = rf"\b(\d{{1,2}})\s+({MONTH_PATTERN})(?:,?\s*|\s+)(\d{{4}})?\b"
    for match in re.finditer(pattern_dmy, full_text, flags=re.IGNORECASE):
        day = match.group(1)
        month_str = match.group(2)[:3].title()
        year = match.group(3) or str(current_year)
        try:
            parsed = datetime.strptime(f"{day} {month_str} {year}", "%d %b %Y")
            return parsed.date().isoformat()
        except ValueError:
            continue

    # 2. Format: Aug 24, 2026 or August 24, 2026
    pattern_mdy = rf"\b({MONTH_PATTERN})\s+(\d{{1,2}})(?:,?\s*|\s+)(\d{{4}})?\b"
    for match in re.finditer(pattern_mdy, full_text, flags=re.IGNORECASE):
        month_str = match.group(1)[:3].title()
        day = match.group(2)
        year = match.group(3) or str(current_year)
        try:
            parsed = datetime.strptime(f"{day} {month_str} {year}", "%d %b %Y")
            return parsed.date().isoformat()
        except ValueError:
            continue

    # 3. Numeric formats: YYYY-MM-DD or YYYY/MM/DD
    match = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", full_text)
    if match:
        try:
            return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        except Exception:
            pass

    # 4. Numeric formats: DD/MM/YYYY or DD-MM-YYYY
    match = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b", full_text)
    if match:
        d, m, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if y < 100:
            y += 2000
        try:
            return f"{y:04d}-{m:02d}-{d:02d}"
        except Exception:
            pass

    return None


def detect_category(merchant: Optional[str], full_text: str) -> str:
    """Predict category based on merchant name and full receipt text keywords."""
    combined = f"{merchant or ''} {full_text}".lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", combined):
                return category

    return "Food"  # College student default
