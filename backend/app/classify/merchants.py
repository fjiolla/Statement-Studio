"""Known Indian merchants / billers, keyed by category.

Each alias is matched as a substring of the narration with separators removed,
so "SWIGGY", "Swiggy Ltd", "swiggy@icici" and "SWIGGYINSTAMART" all hit.
Order matters only within overlapping aliases (longer first is handled in code).
"""
from __future__ import annotations

import re

MERCHANTS: dict[str, dict[str, list[str]]] = {
    "food": {
        "Swiggy": ["swiggy", "bundl technologies"], "Zomato": ["zomato"], "Domino's": ["dominos", "jubilant food"],
        "McDonald's": ["mcdonald", "hardcastle"], "KFC": ["kfc"], "Pizza Hut": ["pizzahut"], "Starbucks": ["starbucks", "tata starbucks"],
        "Burger King": ["burgerking"], "Subway": ["subway"], "Haldiram's": ["haldiram"], "Barbeque Nation": ["barbequenation"],
        "Chaayos": ["chaayos"], "Cafe Coffee Day": ["cafecoffeeday", "coffee day"], "EatSure": ["eatsure", "rebel foods"],
        "Faasos": ["faasos"], "Box8": ["box8"], "Wow! Momo": ["wowmomo"], "Third Wave Coffee": ["thirdwave"],
    },
    "groceries": {
        "Blinkit": ["blinkit", "grofers"], "Zepto": ["zepto", "kiranakart"], "BigBasket": ["bigbasket", "supermarket grocery supplies"],
        "Swiggy Instamart": ["instamart"], "DMart": ["dmart", "avenue supermarts"], "JioMart": ["jiomart"],
        "Reliance Fresh": ["reliancefresh", "reliance retail", "reliancesmart", "smart bazaar"], "More": ["moreretail", "more supermarket"],
        "Spencer's": ["spencers"], "Nature's Basket": ["naturesbasket"], "Milkbasket": ["milkbasket"], "Country Delight": ["countrydelight"],
        "Licious": ["licious"], "FreshToHome": ["freshtohome"], "Star Bazaar": ["starbazaar"], "Ratnadeep": ["ratnadeep"],
    },
    "shopping": {
        "Amazon": ["amazon", "amzn"], "Flipkart": ["flipkart", "fkrt"], "Myntra": ["myntra"], "Ajio": ["ajio"], "Nykaa": ["nykaa"],
        "Meesho": ["meesho"], "Tata CLiQ": ["tatacliq"], "Croma": ["croma", "infiniti retail"], "Reliance Digital": ["reliancedigital"],
        "Decathlon": ["decathlon"], "IKEA": ["ikea"], "Lifestyle": ["lifestyle stores", "landmark group"], "Westside": ["westside", "trent"],
        "Shoppers Stop": ["shoppersstop"], "Pantaloons": ["pantaloons"], "H&M": ["hennes", "h&m"], "Zara": ["zara", "inditex"],
        "Uniqlo": ["uniqlo"], "Reliance Retail": ["reliance"], "Lenskart": ["lenskart"], "FirstCry": ["firstcry"], "Pepperfry": ["pepperfry"], "Urban Company": ["urbancompany", "urbanclap"],
        "Snapdeal": ["snapdeal"], "Apple Store": ["applestore", "apple india"], "Samsung": ["samsung"], "Vijay Sales": ["vijaysales"],
    },
    "travel": {
        "Uber": ["uber"], "Ola": ["olacabs", "ani technologies", "ola "], "Rapido": ["rapido", "roppen"], "IRCTC": ["irctc"],
        "MakeMyTrip": ["makemytrip"], "Goibibo": ["goibibo", "ibibo"], "Cleartrip": ["cleartrip"], "Yatra": ["yatra"],
        "EaseMyTrip": ["easemytrip"], "IndiGo": ["indigo", "interglobe"], "Air India": ["airindia"], "Vistara": ["vistara"],
        "Akasa Air": ["akasa"], "SpiceJet": ["spicejet"], "RedBus": ["redbus"], "Paytm Bus": ["paytm bus", "paytmbus"],
        "Delhi Metro": ["dmrc", "delhi metro"], "Mumbai Metro": ["mmrda", "mumbai metro"], "FASTag": ["fastag", "netc"],
        "Oyo": ["oyo", "oravel"], "Airbnb": ["airbnb"], "Booking.com": ["booking.com", "bookingcom"], "Zoomcar": ["zoomcar"], "BluSmart": ["blusmart"],
    },
    "fuel": {
        "Indian Oil": ["indianoil", "iocl", "indian oil"], "HPCL": ["hpcl", "hindustan petroleum", "hp petrol", "hppay"],
        "BPCL": ["bpcl", "bharat petroleum"], "Shell": ["shell"], "Nayara": ["nayara"], "Jio-bp": ["jiobp", "jio-bp"],
    },
    "utilities": {
        "Airtel": ["airtel", "bharti hexacom"], "Jio": ["reliance jio", "jio prepaid", "jio postpaid", "jiofiber", "rjio", "jiomobility"],
        "Vi": ["vodafone", "idea cellular", "vodafoneidea", "vi postpaid", "vodafoneindia"], "BSNL": ["bsnl"],
        "Tata Power": ["tatapower"], "Adani Electricity": ["adanielectricity", "adani electricity"], "BESCOM": ["bescom"],
        "MSEDCL": ["msedcl", "mahadiscom"], "BSES": ["bses"], "TNEB": ["tneb", "tangedco"], "Torrent Power": ["torrentpower"],
        "Tata Play": ["tatasky", "tataplay"], "Dish TV": ["dishtv"], "ACT Fibernet": ["actfibernet", "atria convergence"],
        "Mahanagar Gas": ["mahanagargas", "mgl"], "Indraprastha Gas": ["igl", "indraprastha gas"], "Hathway": ["hathway"],
        "Electricity Bill": ["electricity", "power distribution", "discom"], "Water Bill": ["water supply", "jal board"],
        "Bharat Sanchar": ["bharatsanchar", "bharat sanchar"],
    },
    "entertainment": {
        "Netflix": ["netflix"], "Spotify": ["spotify"], "Disney+ Hotstar": ["hotstar", "novi digital"], "Prime Video": ["primevideo", "amazon prime"],
        "YouTube": ["youtube", "google youtube"], "BookMyShow": ["bookmyshow", "bigtree"], "PVR INOX": ["pvr", "inox"],
        "Google Play": ["google play", "googleplay"], "Apple Services": ["apple.com", "itunes", "apple services"], "JioCinema": ["jiocinema"],
        "SonyLIV": ["sonyliv"], "ZEE5": ["zee5"], "Steam": ["steam"], "Audible": ["audible"], "Brevo (Sendinblue)": ["sendinblue", "brevo"],
        "Google Workspace": ["google workspace", "gsuite"], "Microsoft": ["microsoft", "msft"], "Adobe": ["adobe"], "Canva": ["canva"],
        "Zoom": ["zoom.us", "zoomvideo"], "OpenAI": ["openai", "chatgpt"], "Dream11": ["dream11"], "AWS": ["aws", "amazon web services"],
    },
    "health": {
        "Apollo": ["apollo"], "PharmEasy": ["pharmeasy"], "Tata 1mg": ["1mg"], "Netmeds": ["netmeds"], "Practo": ["practo"],
        "MedPlus": ["medplus"], "Fortis": ["fortis"], "Max Healthcare": ["max healthcare", "maxhealth"], "Manipal Hospitals": ["manipal"],
        "Cult.fit": ["cultfit", "cure.fit", "curefit"], "Thyrocare": ["thyrocare"], "Dr Lal PathLabs": ["lalpath"],
    },
    "education": {
        "BYJU'S": ["byju"], "Unacademy": ["unacademy", "sorting hat"], "Coursera": ["coursera"], "Udemy": ["udemy"],
        "upGrad": ["upgrad"], "Vedantu": ["vedantu"], "PhysicsWallah": ["physicswallah", "pw live"], "Simplilearn": ["simplilearn"],
    },
    "investment": {
        "Zerodha": ["zerodha"], "Groww": ["groww", "nextbillion"], "Upstox": ["upstox", "rksv"], "Angel One": ["angelone", "angel broking"],
        "Kuvera": ["kuvera"], "Paytm Money": ["paytmmoney"], "ICICI Direct": ["icicidirect", "icici securities", "eba"],
        "HDFC Securities": ["hdfcsec"], "Coin by Zerodha": ["coin zerodha"], "Indian Clearing Corp": ["indian clearing", "iccl"],
        "NSE Clearing": ["nsccl", "nse clearing"], "BSE StAR MF": ["bse star", "bsestarmf"], "CAMS": ["cams"], "KFintech": ["kfintech", "karvy"],
        "Mutual Fund": ["mutual fund", "mutualfund", " mf ", "sip "], "PPF": ["ppf"], "NPS": ["nps trust", "national pension"],
        "Sovereign Gold Bond": ["sgb", "sovereign gold"],
    },
    "insurance": {
        "LIC": ["lic of india", "licindia", "life insurance corp", "lic premium"], "Policybazaar": ["policybazaar"],
        "HDFC Life": ["hdfclife", "hdfc life"], "ICICI Prudential": ["icicipru", "icici prudential"], "SBI Life": ["sbilife", "sbi life"],
        "Star Health": ["starhealth", "star health"], "Max Life": ["maxlife"], "Tata AIG": ["tataaig"], "Bajaj Allianz": ["bajajallianz", "bajaj allianz"],
        "Acko": ["acko"], "Digit Insurance": ["godigit", "go digit"], "Niva Bupa": ["nivabupa", "max bupa"], "Care Health": ["care health", "religare"],
        "PMSBY / PMJJBY": ["pmsby", "pmjjby", "pmjby"],
    },
    "loan": {
        "Bajaj Finance": ["bajaj fin", "bajajfinance", "bajfinance"], "Home Credit": ["home credit", "homecrindfin", "homecr"],
        "Kissht": ["kissht", "onemi"], "KreditBee": ["kreditbee"], "MoneyView": ["moneyview", "whizdm"], "Navi": ["navi finserv"],
        "Tata Capital": ["tatacapital"], "HDFC Ltd": ["hdfc ltd", "hdfc home loan"], "LIC Housing": ["lichousing", "lic housing"],
        "Fullerton": ["fullerton"], "Cholamandalam": ["cholamandalam", "chola"], "Muthoot": ["muthoot"], "Manappuram": ["manappuram"],
        "Poonawalla Fincorp": ["poonawalla"], "Aditya Birla Finance": ["aditya birla fin", "abfl"], "IIFL": ["iifl"], "SI Creva": ["si creva", "sicreva"],
        "Slice": ["slice"], "LazyPay": ["lazypay"], "Simpl": ["simpl"], "TP ACH Home": ["tp ach home"],
    },
    "wallet": {
        "Paytm Wallet": ["paytm wallet", "add money paytm", "one97", "paytm"], "MobiKwik": ["mobikwik", "mobiwik", "one mobikwik"],
        "PhonePe Wallet": ["phonepe wallet"], "Amazon Pay": ["amazon pay", "amazonpay"], "Freecharge": ["freecharge"],
    },
    "card_payment": {
        "CRED": ["cred club", "dreamplug", "cred "], "SBI Card": ["sbi cards", "sbicard", "sbi card"], "Card bill payment": ["credit card payment", "cc payment",
        "card payment", "kotakcards", "hdfc cards", "icici cards", "axis cards", "billdkkotakcards", "pavc", "amex"],
    },
    "rent": {
        "NoBroker": ["nobroker"], "NestAway": ["nestaway"], "Housing.com": ["housing.com"], "MagicBricks": ["magicbricks"],
        "Society Maintenance": ["maintenance", "society", "mygate", "nobrokerhood"], "Rent": ["rent "],
    },
}


def _squash(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum() or ch in "&.@")


ALIAS_INDEX: list[tuple[str, str, str, str]] = []  # (squashed alias, raw alias, merchant, category)
for _cat, _merchants in MERCHANTS.items():
    for _merchant, _aliases in _merchants.items():
        for _a in _aliases:
            ALIAS_INDEX.append((_squash(_a), _a, _merchant, _cat))
ALIAS_INDEX.sort(key=lambda t: -len(t[0]))


def find_merchant(text: str) -> tuple[str, str, str] | None:
    """Return (merchant, category, alias) for the longest alias found in `text`."""
    low = " " + (text or "").lower() + " "
    sq = _squash(text or "")
    for alias_sq, alias_raw, merchant, cat in ALIAS_INDEX:
        if len(alias_sq) < 3:
            continue
        # short or space-padded aliases must match on word boundaries in the spaced text
        if alias_raw != alias_raw.strip() or len(alias_sq) <= 4:
            needle = alias_raw.strip().lower()
            # short aliases must stand alone: "uber" in "/UBER INDIA/" yes, in "SUBERB" no
            if needle and re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", low):
                return merchant, cat, alias_raw.strip()
            continue
        if alias_sq in sq:
            return merchant, cat, alias_raw
    return None
