"""Currency detection and USD conversion utilities."""

import re

# Approximate exchange rates from 1 USD.  Update periodically.
USD_RATES: dict[str, float] = {
    "USD": 1.0,
    "INR": 83.5,
    "GBP": 0.79,
    "EUR": 0.92,
    "JPY": 149.5,
    "AUD": 1.53,
    "CAD": 1.35,
    "SGD": 1.34,
    "AED": 3.67,
    "BRL": 4.97,
    "MXN": 17.2,
    "PLN": 3.98,
    "CZK": 22.8,
    "RON": 4.57,
    "HUF": 360.0,
    "ZAR": 18.6,
    "PHP": 56.5,
    "IDR": 15700.0,
    "MYR": 4.72,
    "THB": 35.2,
    "VND": 24500.0,
    "KRW": 1330.0,
    "TWD": 31.8,
    "HKD": 7.82,
    "CNY": 7.24,
    "NZD": 1.63,
    "CHF": 0.90,
    "SEK": 10.4,
    "NOK": 10.7,
    "DKK": 6.88,
    "ILS": 3.76,
    "TRY": 32.5,
    "SAR": 3.75,
    "QAR": 3.64,
    "PKR": 278.0,
    "BDT": 110.0,
    "LKR": 305.0,
}

# Currency symbol / keyword → currency code
_SYMBOL_MAP = [
    (r'₹|INR|Rs\.?\s', "INR"),
    (r'£|GBP', "GBP"),
    (r'€|EUR', "EUR"),
    (r'¥|JPY|jpy', "JPY"),
    (r'A\$|AUD', "AUD"),
    (r'C\$|CAD', "CAD"),
    (r'S\$|SGD', "SGD"),
    (r'AED|Dh\b|dirham', "AED"),
    (r'R\b|ZAR|rand', "ZAR"),
    (r'CHF', "CHF"),
    (r'NZD|NZ\$', "NZD"),
    (r'HKD|HK\$', "HKD"),
    (r'BRL|R\$', "BRL"),
    (r'\$', "USD"),  # plain $ → USD (check last after A$, C$, S$ etc.)
]

# Location keyword → most likely currency
_LOCATION_CURRENCY = {
    "india": "INR",
    "united kingdom": "GBP",
    " uk": "GBP",
    "london": "GBP",
    "germany": "EUR",
    "france": "EUR",
    "netherlands": "EUR",
    "spain": "EUR",
    "italy": "EUR",
    "portugal": "EUR",
    "poland": "PLN",
    "czech": "CZK",
    "hungary": "HUF",
    "romania": "RON",
    "sweden": "SEK",
    "norway": "NOK",
    "denmark": "DKK",
    "switzerland": "CHF",
    "australia": "AUD",
    "canada": "CAD",
    "singapore": "SGD",
    "uae": "AED",
    "dubai": "AED",
    "japan": "JPY",
    "south africa": "ZAR",
    "brazil": "BRL",
    "mexico": "MXN",
    "new zealand": "NZD",
    "hong kong": "HKD",
    "israel": "ILS",
    "turkey": "TRY",
    "saudi": "SAR",
    "qatar": "QAR",
}


def detect_currency(salary_str: str, location: str = "") -> str:
    """Detect the currency code from a salary string or job location."""
    text = (salary_str or "").strip()
    for pattern, code in _SYMBOL_MAP:
        if re.search(pattern, text, re.IGNORECASE):
            return code

    loc = (location or "").lower()
    for keyword, code in _LOCATION_CURRENCY.items():
        if keyword in loc:
            return code

    return "USD"  # default


def usd_to(amount_usd: float, target_currency: str) -> float:
    """Convert a USD amount to the target currency."""
    rate = USD_RATES.get(target_currency.upper(), 1.0)
    return amount_usd * rate


def salary_in_usd(salary_str: str, location: str = "") -> float | None:
    """
    Extract the maximum numeric value from a salary string and convert to USD.
    Returns None if no numeric value found.
    """
    if not salary_str or not salary_str.strip():
        return None

    currency = detect_currency(salary_str, location)
    nums = re.findall(r'[\d,]+', salary_str)
    if not nums:
        return None

    max_num = max(int(n.replace(",", "")) for n in nums)

    # Heuristic: values under 1000 are likely monthly (e.g. "₹80k" already parsed as 80)
    # Values like "80k" — the 'k' suffix handling
    if "k" in salary_str.lower():
        multiplier = 1000
    else:
        multiplier = 1

    max_num *= multiplier
    rate = USD_RATES.get(currency.upper(), 1.0)
    return max_num / rate if rate else max_num
