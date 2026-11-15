"""Open-Meteo: thời tiết và chất lượng không khí theo tọa độ (miễn phí, không cần khóa)."""
import sys
import urllib.parse
from datetime import datetime

from infrastructure.web import fetch_json

FORECAST = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"


def daily(place, day):
    """Dự báo từng ngày (day=0 là hôm nay, kèm nhiệt độ lúc này); trả JSON gốc của Open-Meteo."""
    lat, lon = place
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Asia/Bangkok", "forecast_days": day + 1,
    })
    return fetch_json(f"{FORECAST}?{q}")


def air_now(place, fields="us_aqi,pm2_5"):
    """Chỉ số không khí hiện tại: {"us_aqi", "pm2_5"} (hoặc các trường fields)."""
    lat, lon = place
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon,
                                "current": fields, "timezone": "Asia/Bangkok"})
    return fetch_json(f"{AIR}?{q}")["current"]


def hourly(place, days=2):
    """Dự báo theo giờ: mỗi giờ một dict time/feel/rain_prob/rain/humid/uv/aqi (aqi None nếu lỗi)."""
    lat, lon = place
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "forecast_days": days, "timezone": "Asia/Bangkok",
        "hourly": "apparent_temperature,precipitation_probability,precipitation,relative_humidity_2m,uv_index",
    })
    h = fetch_json(f"{FORECAST}?{q}")["hourly"]
    try:
        q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "hourly": "us_aqi",
                                    "forecast_days": days, "timezone": "Asia/Bangkok"})
        a = fetch_json(f"{AIR}?{q}")["hourly"]
        aqi = dict(zip(a["time"], a["us_aqi"]))
    except Exception as e:
        print(f"[lỗi] AQI theo giờ: {e!r}", file=sys.stderr)
        aqi = {}
    return [{"time": datetime.fromisoformat(t), "feel": feel, "rain_prob": prob or 0, "rain": rain or 0,
             "humid": humid or 0, "uv": uv or 0, "aqi": aqi.get(t)}
            for t, feel, prob, rain, humid, uv in zip(
                h["time"], h["apparent_temperature"], h["precipitation_probability"], h["precipitation"],
                h["relative_humidity_2m"], h["uv_index"])]


def minutely(place, slots):
    """Mưa theo từng 15 phút: [(giờ, mm mưa, mã thời tiết)], lấy `slots` mốc đầu."""
    lat, lon = place
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "minutely_15": "precipitation,weather_code",
        "forecast_minutely_15": slots, "timezone": "Asia/Bangkok",
    })
    m = fetch_json(f"{FORECAST}?{q}")["minutely_15"]
    return list(zip(m["time"], m["precipitation"], m["weather_code"]))
