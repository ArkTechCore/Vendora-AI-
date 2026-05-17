import json
from hashlib import sha1
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.utils import timezone


TIMEOUT = 2.5


def get_smart_signals(user):
    if user.is_super_admin():
        return []
    store = _store_for_user(user)
    return [
        _weather_signal(store),
        _holiday_signal(),
        _recall_signal(),
    ]


def _store_for_user(user):
    if user.is_manager():
        return user.store
    return user.client.stores.filter(is_active=True).first()


def _weather_signal(store):
    if not store:
        return _offline_signal("Weather", "Add a business or store address to unlock prep and staffing weather signals.", "Open-Meteo")
    queries = _weather_queries(store)
    query_key = "|".join(queries) or store.name
    cache_key = f"smart:weather:{_cache_slug(query_key)}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        location = None
        for query in queries:
            location = _geocode(query)
            if location:
                break
        if not location:
            return _offline_signal("Weather", "Add a city or full business address to show local demand signals.", "Open-Meteo")
        forecast_url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "daily": "temperature_2m_max,precipitation_probability_max",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
            "forecast_days": 3,
        })
        data = _fetch_json(forecast_url)
        daily = data.get("daily", {})
        high = daily.get("temperature_2m_max", [None])[0]
        rain = daily.get("precipitation_probability_max", [0])[0] or 0
        if high is None:
            raise ValueError("Weather forecast missing temperature.")
        if rain >= 55:
            body = f"{location['name']}: {rain}% rain chance today. Watch delivery timing and dine-in traffic."
            tone = "warn"
        elif high >= 85:
            body = f"{location['name']}: high near {high:.0f}F. Prep cold drinks, dairy storage checks, and delivery packaging."
            tone = "warn"
        else:
            body = f"{location['name']}: high near {high:.0f}F with {rain}% rain chance. Normal prep signal."
            tone = "ok"
        signal = {"title": "Weather demand signal", "body": body, "source": "Open-Meteo", "tone": tone}
    except Exception:
        signal = _offline_signal("Weather", "Weather signal unavailable right now. It will retry automatically.", "Open-Meteo")
    cache.set(cache_key, signal, 60 * 30)
    return signal


def _holiday_signal():
    today = timezone.localdate()
    cache_key = f"smart:holidays:US:{today.year}:{today.isoformat()}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        url = f"https://date.nager.at/api/v3/PublicHolidays/{today.year}/US"
        holidays = _fetch_json(url)
        upcoming = []
        for holiday in holidays:
            holiday_date = timezone.datetime.fromisoformat(holiday["date"]).date()
            days = (holiday_date - today).days
            if 0 <= days <= 14:
                upcoming.append((days, holiday["name"], holiday_date))
        if upcoming:
            days, name, holiday_date = upcoming[0]
            when = "today" if days == 0 else f"in {days} day(s)"
            body = f"{name} is {when} ({holiday_date}). Plan staffing, prep, paid-outs, and inventory counts early."
            tone = "warn" if days <= 3 else "ok"
        else:
            body = "No US public holiday in the next 14 days. Normal planning window."
            tone = "ok"
        signal = {"title": "Holiday prep signal", "body": body, "source": "Nager.Date", "tone": tone}
    except Exception:
        signal = _offline_signal("Holiday", "Holiday signal unavailable right now. It will retry automatically.", "Nager.Date")
    cache.set(cache_key, signal, 60 * 60 * 6)
    return signal


def _recall_signal():
    cache_key = "smart:food_recall:recent"
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        url = "https://api.fda.gov/food/enforcement.json?" + urlencode({
            "limit": 1,
            "sort": "report_date:desc",
        })
        data = _fetch_json(url)
        result = (data.get("results") or [{}])[0]
        if not result:
            signal = {"title": "Food recall watch", "body": "No recent public food recall data found right now.", "source": "openFDA", "tone": "ok"}
        else:
            product = _short_text(result.get("product_description", "recent food recall"), 42)
            reason = _short_text(result.get("reason_for_recall", "review supplier alerts"), 54)
            date = _format_fda_date(result.get("report_date", ""))
            body = f"FDA recall {date}: {product}. Check stock and vendor invoices. Reason: {reason}."
            signal = {"title": "Food recall watch", "body": body, "source": "openFDA", "tone": "warn"}
    except Exception:
        signal = _offline_signal("Food recall", "Food recall signal unavailable right now. It will retry automatically.", "openFDA")
    cache.set(cache_key, signal, 60 * 60 * 6)
    return signal


def _format_fda_date(value):
    if len(value or "") == 8:
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return "recently"


def _short_text(value, limit):
    text = " ".join(str(value or "").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    trimmed = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return f"{trimmed}..."


def _geocode(query):
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode({
        "name": query,
        "count": 1,
        "language": "en",
        "format": "json",
    })
    data = _fetch_json(url)
    results = data.get("results") or []
    return results[0] if results else None


def _weather_queries(store):
    client = store.client
    values = [
        store.address.strip(),
        getattr(client, "full_address", "").strip(),
        _join_address(client.city, client.state, client.country),
        _join_address(client.postal_code, client.country),
        client.city,
        store.name,
    ]
    queries = []
    for value in values:
        if value and value not in queries:
            queries.append(value)
    return queries


def _join_address(*parts):
    return ", ".join(str(part).strip() for part in parts if str(part).strip())


def _fetch_json(url):
    request = Request(url, headers={"User-Agent": "VendoraOps/1.0"})
    with urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _offline_signal(title, body, source="Free public API"):
    return {"title": f"{title} signal", "body": body, "source": source, "tone": "warn"}


def _cache_slug(value):
    return sha1(str(value).lower().encode("utf-8")).hexdigest()
