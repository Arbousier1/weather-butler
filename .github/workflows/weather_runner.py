#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌤️ 天气管家 - GitHub Actions 入口脚本
从环境变量读取配置，无需 .env 文件
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime
from pathlib import Path

# ============================================================
# 天气状况代码映射（中文）
# ============================================================
WEATHER_CONDITIONS_CN = {
    200: "雷阵雨（小）", 201: "雷阵雨（中）", 202: "雷阵雨（大）",
    210: "雷阵雨（小）", 211: "雷阵雨（中）", 212: "雷阵雨（大）",
    221: "雷阵雨伴冰雹", 230: "雷阵雨伴小雨", 231: "雷阵雨伴中雨", 232: "雷阵雨伴大雨",
    300: "毛毛雨（小）", 301: "毛毛雨（中）", 302: "毛毛雨（大）",
    310: "毛毛雨（小）", 311: "毛毛雨（中）", 312: "毛毛雨（大）",
    500: "小雨", 501: "中雨", 502: "大雨", 503: "暴雨", 504: "大暴雨",
    511: "冻雨", 520: "阵雨（小）", 521: "阵雨（中）", 522: "阵雨（大）",
    600: "小雪", 601: "中雪", 602: "大雪", 611: "雨夹雪",
    701: "薄雾", 711: "烟雾", 721: "霾", 741: "雾",
    761: "沙尘暴", 771: "大风", 781: "龙卷风",
    800: "晴", 801: "少云", 802: "多云", 803: "阴", 804: "阴天",
}

SEVERE_WEATHER_IDS = {
    200, 201, 202, 210, 211, 212, 221, 230, 231, 232,
    502, 503, 504, 511, 522,
    602, 616, 622,
    761, 762, 771, 781,
}

WIND_DIRECTIONS = ["北风","东北风","东风","东南风","南风","西南风","西风","西北风"]

# ============================================================
# 日志
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("WeatherButler")

# ============================================================
# 工具函数
# ============================================================

def wind_direction(deg):
    idx = round(deg / 45) % 8
    return WIND_DIRECTIONS[idx]

def temp_feeling(temp):
    if temp <= -10: return "极寒", "请穿厚羽绒服、戴帽子手套围巾"
    elif temp <= 0: return "严寒", "请穿羽绒服、戴帽子手套"
    elif temp <= 10: return "寒冷", "建议穿厚外套或毛衣"
    elif temp <= 18: return "微凉", "建议穿薄外套或长袖"
    elif temp <= 25: return "舒适", "温度适宜，穿着舒适"
    elif temp <= 30: return "温暖", "穿短袖即可，注意防晒"
    elif temp <= 35: return "炎热", "注意防暑降温，多喝水"
    else: return "酷热", "高温预警！尽量待在室内"

# ============================================================
# API 调用（多 Key 轮询）
# ============================================================

_key_index = 0

def get_next_key(keys):
    global _key_index
    if not keys: return ""
    key = keys[_key_index % len(keys)]
    _key_index += 1
    return key

def fetch_weather(lat, lon, keys, lang="zh_cn", units="metric"):
    if not keys:
        logger.error("❌ 未配置 API Key")
        return None
    for i in range(len(keys)):
        key = get_next_key(keys)
        logger.info(f"🔑 使用 Key: {key[:8]}... ({i+1}/{len(keys)})")
        url = "https://api.openweathermap.org/data/3.0/onecall"
        params = {"lat": lat, "lon": lon, "appid": key, "lang": lang, "units": units}
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"⚠️ Key {key[:8]}... 失败: {e}")
    logger.error("❌ 所有 API Key 均失败")
    return None

# 天气图标（用于 Bark 推送）
WEATHER_ICONS = {
    # 晴
    800: "☀️",  # 晴
    # 少云/多云
    801: "🌤️",  # 少云
    802: "⛅",  # 多云
    803: "🌥️",  # 阴
    804: "☁️",  # 阴天
    # 雨
    500: "🌧️",  # 小雨
    501: "🌧️",  # 中雨
    502: "🌧️",  # 大雨
    503: "⛈️",  # 暴雨
    504: "⛈️",  # 大暴雨
    511: "🌨️",  # 冻雨
    520: "🌦️",  # 阵雨
    521: "🌦️",  # 阵雨
    522: "🌧️",  # 阵雨
    # 雪
    600: "🌨️",  # 小雪
    601: "❄️",  # 中雪
    602: "❄️",  # 大雪
    611: "🌨️",  # 雨夹雪
    # 雷
    200: "⛈️",  # 雷阵雨
    201: "⛈️",  # 雷阵雨
    202: "⛈️",  # 雷阵雨
    210: "⛈️",
    211: "⛈️",
    212: "⛈️",
    221: "⛈️",
    # 雾/霾
    701: "🌫️",
    711: "🌫️",
    721: "😷",
    741: "🌫️",
    761: "🌪️",
    771: "💨",
    781: "🌪️",
    # 毛毛雨
    300: "🌧️",
    301: "🌧️",
    302: "🌧️",
    310: "🌧️",
    311: "🌧️",
    312: "🌧️",
}

def get_weather_icon(data):
    """获取天气图标和 OpenWeatherMap 图标 URL"""
    current = data.get("current", {})
    weather_list = current.get("weather", [])
    if not weather_list:
        return "🌤️", None
    wid = weather_list[0].get("id", 800)
    icon = WEATHER_ICONS.get(wid, "🌤️")
    # OpenWeatherMap 图标 URL
    icon_code = weather_list[0].get("icon", "01d")
    icon_url = f"https://openweathermap.org/img/wn/{icon_code}@2x.png"
    return icon, icon_url


# ============================================================
# 恶劣天气检测
# ============================================================

def check_severe_weather(data):
    alerts = []
    current = data.get("current", {})
    weather_list = current.get("weather", [])
    for w in weather_list:
        wid = w.get("id", 0)
        if wid in SEVERE_WEATHER_IDS:
            alerts.append({
                "message": f"⚠️ 当前天气恶劣：{WEATHER_CONDITIONS_CN.get(wid, w.get('description',''))}",
                "detail": w.get("description", ""),
            })
    wind_speed = current.get("wind_speed", 0)
    wind_gust = current.get("wind_gust", 0)
    if wind_gust >= 20 or wind_speed >= 15:
        alerts.append({
            "message": f"🌬️ 大风预警：风速 {wind_speed:.1f}m/s，阵风 {wind_gust:.1f}m/s",
            "detail": "注意固定户外物品，减少外出",
        })
    visibility = current.get("visibility", 10000)
    if visibility < 2000:
        alerts.append({
            "message": f"👁️ 能见度低：{visibility}m",
            "detail": "驾车请减速慢行，开雾灯",
        })
    temp = current.get("temp", 20)
    if temp <= -15:
        alerts.append({"message": f"🥶 极端低温：{temp:.1f}°C", "detail": "严寒天气，减少外出"})
    elif temp >= 40:
        alerts.append({"message": f"🔥 极端高温：{temp:.1f}°C", "detail": "高温预警！避免户外活动"})
    minutely = data.get("minutely", [])
    heavy_rain = sum(1 for m in minutely[:30] if m.get("precipitation", 0) > 2.0)
    if heavy_rain >= 5:
        alerts.append({"message": f"🌧️ 未来30分钟有强降水（{heavy_rain}分钟>2mm）", "detail": "请尽快携带雨具"})
    gov_alerts = data.get("alerts", [])
    for a in gov_alerts:
        event = a.get("event", "警报")
        desc = a.get("description", "")[:200]
        alerts.append({"message": f"🚨 政府警报：{event}", "detail": desc})
    return alerts

# ============================================================
# Bark 推送
# ============================================================

def send_bark(title, body, group="天气管家", sound="alarm.caf", url=None):
    bark_key = os.getenv("BARK_KEY", "")
    if not bark_key:
        logger.debug("Bark 未配置")
        return False
    import urllib.parse
    try:
        # 使用 POST 方式，Secret 不出现在 URL 中（避免 GitHub Actions 脱敏）
        api_url = f"https://api.day.app/{bark_key}"
        payload = {
            "title": title,
            "body": body,
            "group": group,
            "sound": sound,
        }
        if url:
            payload["icon"] = url
        resp = requests.post(api_url, data=payload, timeout=8)
        result = resp.json()
        if result.get("code") == 200:
            logger.info(f"📲 Bark 推送成功: {title[:30]}...")
            return True
        logger.warning(f"⚠️ Bark 推送失败: {result}")
    except Exception as e:
        logger.error(f"❌ Bark 推送异常: {e}")
    return False

def send_bark_alert(alerts, city):
    title = f"🚨 {city} 恶劣天气预警"
    body_parts = [a["message"] for a in alerts]
    if len(body_parts) > 5:
        body_parts = body_parts[:5]
    body = "\n".join(body_parts)
    if len(body) > 450:
        body = body[:447] + "..."
    send_bark(title, body, group="天气预警", sound="alarm.caf")

def send_bark_ai_report(data, location_info, report_type):
    city = location_info.get("city", "未知")
    label = "🌅 早安" if report_type == "morning" else ("☀️ 午后" if report_type == "afternoon" else "📋 天气快报")
    current = data.get("current", {})
    temp = current.get("temp", 0)
    weather_list = current.get("weather", [])
    weather_desc = WEATHER_CONDITIONS_CN.get(
        weather_list[0]["id"], weather_list[0].get("description", "未知")
    ) if weather_list else "未知"
    feels = current.get("feels_like", temp)
    humidity = current.get("humidity", 0)
    wind_speed = current.get("wind_speed", 0)
    uvi = current.get("uvi", 0)

    # 获取天气图标
    weather_icon, icon_url = get_weather_icon(data)

    ai_report = generate_ai_butler_report(data, location_info, report_type)
    if not ai_report or len(ai_report) < 30:
        send_bark_summary(data, location_info, report_type)
        return

    chinese_chars = sum(1 for c in ai_report if '\u4e00' <= c <= '\u9fff')
    if chinese_chars < 20:
        send_bark_summary(data, location_info, report_type)
        return

    body = ai_report.strip()
    if len(body) > 450:
        body = body[:447] + "..."

    # 固定格式的 Emoji 天气卡片（纯文本，无特殊符号，确保 iOS 渲染一致）
    uvi_level = "低" if uvi < 3 else ("中等" if uvi < 6 else ("高" if uvi < 8 else "很高"))
    weather_card = (
        f"📍 {city} {label}\n\n"
        f"{weather_icon} 当前 {temp:.0f}°C  体感 {feels:.0f}°C\n\n"
        f"💧 湿度 {humidity}%\n"
        f"🌬️ 风速 {wind_speed:.0f} m/s\n"
        f"☀️ UV指数 {uvi:.0f} ({uvi_level})\n"
        f"🌥️ {weather_desc}"
    )

    # 组装推送正文：卡片 + AI 分析
    body = ai_report.strip()
    if len(body) > 350:
        body = body[:347] + "..."

    # 固定标题格式：城市 + 天气 + 温度
    title = f"{city} {weather_icon} {weather_desc} {temp:.0f}°C"

    full_body = weather_card + "\n\n" + body

    if len(full_body) > 1000:
        # 太长就只用卡片 + 截断 AI 报告
        full_body = weather_card + "\n\n" + body[:400]

    send_bark(title, full_body, group=f"天气/{report_type}", sound="glass.caf")

def send_bark_summary(data, location_info, report_type):
    city = location_info.get("city", "未知")
    label = "🌅 早安" if report_type == "morning" else "☀️ 午后"
    current = data.get("current", {})
    temp = current.get("temp", 0)
    feels = current.get("feels_like", 0)
    humidity = current.get("humidity", 0)
    wind_speed = current.get("wind_speed", 0)
    weather_list = current.get("weather", [])
    weather_desc = WEATHER_CONDITIONS_CN.get(
        weather_list[0]["id"], weather_list[0].get("description", "未知")
    ) if weather_list else "未知"
    temp_feel, _ = temp_feeling(temp)
    body = f"{weather_desc} {temp:.0f}°C（体感 {feels:.0f}°C）| 湿度{humidity}% | 风速{wind_speed:.0f}m/s"
    send_bark(f"{label} | {city} {weather_desc} {temp:.0f}°C", body, group=f"天气汇总/{report_type}", sound="glass.caf")

# ============================================================
# OpenRouter AI
# ============================================================

def call_openrouter(messages, temperature=0.8, max_tokens=800):
    api_base = os.getenv("OPENROUTER_API_BASE", "").rstrip("/")
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_MODEL", "")
    if not api_base or not api_key or not model:
        logger.debug("OpenRouter 未完整配置")
        return None
    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://weather-butler.github.io",
        "X-Title": "Weather Butler",
    }
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"❌ OpenRouter API 失败: {e}")
    return None

def generate_ai_butler_report(data, location_info, report_type):
    city = location_info.get("city", "未知")
    region = location_info.get("region", "")
    location_str = f"{city}" + (f"，{region}" if region else "")
    current = data.get("current", {})
    daily = data.get("daily", [])
    hourly = data.get("hourly", [])
    alerts_data = data.get("alerts", [])

    temp = current.get("temp", 0)
    feels_like = current.get("feels_like", 0)
    humidity = current.get("humidity", 0)
    wind_speed = current.get("wind_speed", 0)
    wind_deg = current.get("wind_deg", 0)
    wind_gust = current.get("wind_gust", 0)
    visibility = current.get("visibility", 10000)
    pressure = current.get("pressure", 0)
    uvi = current.get("uvi", 0)
    weather_list = current.get("weather", [])
    weather_desc = WEATHER_CONDITIONS_CN.get(
        weather_list[0]["id"], weather_list[0].get("description", "未知")
    ) if weather_list else "未知"
    wind_dir = wind_direction(wind_deg)

    daily_summary = ""
    for i, d in enumerate(daily[:4]):
        d_time = datetime.fromtimestamp(d["dt"])
        weekday = ["周一","周二","周三","周四","周五","周六","周日"][d_time.weekday()]
        d_w = WEATHER_CONDITIONS_CN.get(d["weather"][0]["id"], d["weather"][0].get("description","")) if d.get("weather") else "未知"
        pop = d.get("pop", 0)
        pop_str = f"，降水{pop*100:.0f}%" if pop >= 0.2 else ""
        daily_summary += f"{weekday}：{d['temp']['min']:.0f}~{d['temp']['max']:.0f}°C，{d_w}{pop_str}\n"

    severe = check_severe_weather(data)
    severe_str = "\n".join(f"- {a['message']}" for a in severe) if severe else "无"
    alert_str = "\n".join(f"- {a.get('event','警报')}" for a in alerts_data) if alerts_data else "无"

    label = "🌅 早安" if report_type == "morning" else "☀️ 午后"
    time_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    system_prompt = """你是一位专业的天气管家，服务于宁波象山的居民。说话风格亲切、专业，像一位贴心的管家。

【强制要求】
- 必须全程用中文回答，不要出现任何英文单词
- 回复长度 200-350 字，自然段落，不用列表格式
- 内容：开场问候、当前天气、穿衣建议、出行提醒、今日活动、未来展望、结束祝福

【禁止】出现英文单词、markdown列表格式"""

    user_prompt = f"""地点：{location_str}
时间：{time_str}

当前：{weather_desc}，气温{temp:.1f}°C（体感{feels_like:.1f}°C），湿度{humidity}%，风力{wind_dir}{wind_speed:.1f}m/s（阵风{wind_gust:.1f}m/s），能见度{visibility/1000:.1f}km，气压{pressure}hPa，UV指数{uvi}

未来12小时：{chr(10).join(f"{datetime.fromtimestamp(h['dt']).strftime('%H:%M')}：{h.get('temp',0):.0f}°C，{WEATHER_CONDITIONS_CN.get(h['weather'][0]['id'], h['weather'][0].get('description','')) if h.get('weather') else '未知'}，降水{h.get('pop',0)*100:.0f}%" for h in hourly[:12])}

未来几天：{daily_summary}
恶劣天气：{severe_str}
政府警报：{alert_str}"""

    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
    ai_report = call_openrouter(messages, temperature=0.8, max_tokens=800)
    if ai_report:
        chinese_chars = sum(1 for c in ai_report if '\u4e00' <= c <= '\u9fff')
        if chinese_chars < 30 or len(ai_report) < 50 or ai_report.startswith("The "):
            logger.warning("⚠️ AI 首次回复不理想，重试...")
            ai_report = call_openrouter(messages, temperature=0.6, max_tokens=1000)
    return ai_report

# ============================================================
# 主程序
# ============================================================

def main():
    logger.info("=" * 50)
    logger.info("🌤️ 天气管家 GitHub Actions 任务启动")
    logger.info("=" * 50)

    # 从环境变量读取配置
    api_keys_str = os.getenv("API_KEYS", "")
    if not api_keys_str:
        logger.error("❌ 未配置 API_KEYS")
        sys.exit(1)
    api_keys = [k.strip() for k in api_keys_str.split(",") if k.strip()]
    logger.info(f"🔑 已加载 {len(api_keys)} 个 API Key")

    def get_env(key, fallback):
        val = os.getenv(key, "")
        return val if val.strip() else fallback
    lat = float(get_env("LAT", "29.4768"))
    lon = float(get_env("LON", "121.8634"))
    location_name = get_env("LOCATION_NAME", "宁波象山")
    lang = os.getenv("LANG", "zh_cn")
    units = os.getenv("UNITS", "metric")

    location_info = {
        "lat": lat, "lon": lon,
        "city": location_name,
        "region": "宁波市",
        "country": "中国",
    }

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.hour

    # 判断报告类型
    report_type = None
    if current_hour == 8 and os.getenv("LAST_REPORT_08") != today:
        report_type = "morning"
        logger.info("🌅 检测到 8:00 早安汇报时间")
    elif current_hour == 13 and os.getenv("LAST_REPORT_13") != today:
        report_type = "afternoon"
        logger.info("☀️ 检测到 13:00 午后汇报时间")

    # 获取天气数据
    logger.info("🌤️ 获取天气数据...")
    data = fetch_weather(lat, lon, api_keys, lang=lang, units=units)
    if not data:
        logger.error("❌ 获取天气数据失败")
        sys.exit(1)

    current = data.get("current", {})
    temp = current.get("temp", 0)
    weather_list = current.get("weather", [])
    weather_desc = WEATHER_CONDITIONS_CN.get(
        weather_list[0]["id"], weather_list[0].get("description", "未知")
    ) if weather_list else "未知"
    logger.info(f"✅ 当前：{weather_desc} {temp:.1f}°C")

    # 恶劣天气检测
    alerts = check_severe_weather(data)
    if alerts:
        logger.warning(f"🚨 检测到 {len(alerts)} 项恶劣天气")
        send_bark_alert(alerts, location_name)
        for a in alerts:
            logger.warning(f"  {a['message']}")

    # 每次运行都生成 AI 管家报告并推送
    label = "🌅 早安" if report_type == "morning" else ("☀️ 午后" if report_type == "afternoon" else "📋 天气快报")
    logger.info(f"🤖 生成 AI 管家报告...")
    send_bark_ai_report(data, location_info, report_type or "summary")

    logger.info("✅ 任务完成")
    logger.info(f"   时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   天气: {weather_desc} {temp:.1f}°C")
    logger.info(f"   预警: {'有' if alerts else '无'}")

if __name__ == "__main__":
    main()
