#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌤️ 天气管家 (Weather Butler)
基于 OpenWeatherMap One Call API 3.0 的智能天气管家系统
- 每 86 秒调用一次 API，监控天气变化
- 每天 8:00 和 13:00 生成管家式天气汇报
- 检测恶劣天气并立即预警
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# 配置
# ============================================================
BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"
LOG_FILE = BASE_DIR / "weather_butler.log"
REPORT_DIR = BASE_DIR / "reports"
STATE_FILE = BASE_DIR / "state.json"

# 默认配置
DEFAULT_CONFIG = {
    "api_keys": [],  # 多 Key 轮询
    "api_key": "",   # 兼容单 Key
    "lang": "zh_cn",
    "units": "metric",
    "lat": None,
    "lon": None,
    "location_name": "",
    "bark_key": "",  # Bark 推送
    "openrouter_api_base": "",
    "openrouter_api_key": "",
    "openrouter_model": "",
}

# Key 轮询索引
_key_index = 0

# ============================================================
# 日志设置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("WeatherButler")

# ============================================================
# 天气状况代码映射（中文）
# ============================================================
WEATHER_CONDITIONS_CN = {
    # 雷暴
    200: "雷阵雨（小）", 201: "雷阵雨（中）", 202: "雷阵雨（大）",
    210: "雷阵雨（小）", 211: "雷阵雨（中）", 212: "雷阵雨（大）",
    221: "雷阵雨伴冰雹", 230: "雷阵雨伴小雨", 231: "雷阵雨伴中雨",
    232: "雷阵雨伴大雨",
    # 毛毛雨
    300: "毛毛雨（小）", 301: "毛毛雨（中）", 302: "毛毛雨（大）",
    310: "毛毛雨（小）", 311: "毛毛雨（中）", 312: "毛毛雨（大）",
    313: "阵雨毛毛雨", 314: "冻毛毛雨（大）", 321: "阵雨毛毛雨",
    # 雨
    500: "小雨", 501: "中雨", 502: "大雨", 503: "暴雨", 504: "大暴雨",
    511: "冻雨", 520: "阵雨（小）", 521: "阵雨（中）", 522: "阵雨（大）",
    531: "零星阵雨",
    # 雪
    600: "小雪", 601: "中雪", 602: "大雪", 611: "雨夹雪",
    612: "阵雨夹雪", 613: "阵雪（小）", 615: "阵雪（中）",
    616: "阵雪（大）", 620: "阵雪（小）", 621: "阵雪（中）",
    622: "阵雪（大）",
    # 雾/霾
    701: "薄雾", 711: "烟雾", 721: "霾", 731: "沙尘（小）",
    741: "雾", 751: "沙尘", 761: "沙尘暴", 762: "火山灰",
    771: "大风", 781: "龙卷风",
    # 晴/云
    800: "晴", 801: "少云", 802: "多云", 803: "阴", 804: "阴天",
}

# 恶劣天气代码集合
SEVERE_WEATHER_IDS = {
    # 雷暴系列
    200, 201, 202, 210, 211, 212, 221, 230, 231, 232,
    # 大雨/暴雨
    502, 503, 504, 511, 522,
    # 大雪
    602, 616, 622,
    # 极端天气
    761, 762, 771, 781,
}

# 风向中文
WIND_DIRECTIONS = [
    "北风", "东北风", "东风", "东南风",
    "南风", "西南风", "西风", "西北风",
]

# UV 指数等级
UV_LEVELS = [
    (0, 2, "低", "无需特别防护"),
    (3, 5, "中等", "建议涂抹防晒霜"),
    (6, 7, "高", "减少户外暴晒，涂抹SPF30+防晒霜"),
    (8, 10, "很高", "避免10-16点户外活动，必须防护"),
    (11, 50, "极高", "尽量不外出，严格防护"),
]

# ============================================================
# 工具函数
# ============================================================

def load_env():
    """从 .env 文件加载配置"""
    config = DEFAULT_CONFIG.copy()
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip().upper()
                    value = value.strip()
                    if key == "API_KEYS":
                        # 多 Key，逗号分隔
                        keys = [k.strip() for k in value.split(",") if k.strip()]
                        config["api_keys"] = keys
                        if keys:
                            config["api_key"] = keys[0]  # 兼容
                    elif key == "API_KEY":
                        if value and value.lower() not in ("none", "null"):
                            config["api_key"] = value
                            if not config["api_keys"]:
                                config["api_keys"] = [value]
                    elif key == "LAT":
                        try:
                            config["lat"] = float(value)
                        except ValueError:
                            pass
                    elif key == "LON":
                        try:
                            config["lon"] = float(value)
                        except ValueError:
                            pass
                    elif key == "LOCATION_NAME":
                        config["location_name"] = value
                    elif key == "LANG":
                        config["lang"] = value
                    elif key == "UNITS":
                        config["units"] = value
                    elif key == "BARK_KEY":
                        if value and value.lower() not in ("none", "null", ""):
                            config["bark_key"] = value
                    elif key == "OPENROUTER_API_BASE":
                        if value and value.lower() not in ("none", "null", ""):
                            config["openrouter_api_base"] = value
                    elif key == "OPENROUTER_API_KEY":
                        if value and value.lower() not in ("none", "null", ""):
                            config["openrouter_api_key"] = value
                    elif key == "OPENROUTER_MODEL":
                        if value and value.lower() not in ("none", "null", ""):
                            config["openrouter_model"] = value
    return config


def get_next_key(config):
    """轮询获取下一个 API Key"""
    global _key_index
    keys = config.get("api_keys", [])
    if not keys:
        return config.get("api_key", "")
    key = keys[_key_index % len(keys)]
    _key_index += 1
    return key


def load_state():
    """加载状态文件"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "last_alert_time": 0,
        "last_report_date": "",
        "last_report_time": "",
        "call_count_today": 0,
        "call_date": "",
        "location": {},
    }


def save_state(state):
    """保存状态文件"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_location():
    """自动获取当前位置（通过 IP 定位）"""
    try:
        resp = requests.get(
            "http://ip-api.com/json/?lang=zh-CN",
            timeout=10,
        )
        data = resp.json()
        if data.get("status") == "success":
            return {
                "lat": data["lat"],
                "lon": data["lon"],
                "city": data.get("city", "未知城市"),
                "region": data.get("regionName", ""),
                "country": data.get("country", ""),
            }
    except Exception as e:
        logger.error(f"IP 定位失败: {e}")
    return None


def wind_direction(deg):
    """将风向角度转为中文"""
    idx = round(deg / 45) % 8
    return WIND_DIRECTIONS[idx]


def uv_info(uvi):
    """获取 UV 等级信息"""
    for low, high, level, advice in UV_LEVELS:
        if low <= uvi <= high:
            return level, advice
    return "极高", "尽量不外出，严格防护"


def temp_feeling(temp):
    """体感描述"""
    if temp <= -10:
        return "极寒", "⚠️ 请穿厚羽绒服、戴帽子手套围巾，注意防冻"
    elif temp <= 0:
        return "严寒", "🧣 请穿羽绒服、戴帽子手套，注意保暖"
    elif temp <= 10:
        return "寒冷", "🧥 建议穿厚外套或毛衣，注意保暖"
    elif temp <= 18:
        return "微凉", "🧥 建议穿薄外套或长袖"
    elif temp <= 25:
        return "舒适", "👕 温度适宜，穿着舒适"
    elif temp <= 30:
        return "温暖", "👕 穿短袖即可，注意防晒"
    elif temp <= 35:
        return "炎热", "🥵 注意防暑降温，多喝水"
    else:
        return "酷热", "🔥 高温预警！尽量待在室内，注意防暑"


def humidity_feeling(humidity):
    """湿度体感描述"""
    if humidity < 30:
        return "干燥", "💧 空气干燥，注意补水保湿"
    elif humidity < 60:
        return "舒适", "✅ 湿度适宜"
    elif humidity < 80:
        return "潮湿", "💨 空气潮湿，注意除湿"
    else:
        return "闷湿", "😰 非常潮湿，体感不适"


def visibility_desc(vis):
    """能见度描述"""
    if vis >= 10000:
        return "极佳", "✅ 能见度很好"
    elif vis >= 5000:
        return "良好", "✅ 能见度正常"
    elif vis >= 2000:
        return "一般", "⚠️ 能见度有所下降，出行注意"
    elif vis >= 1000:
        return "较差", "⚠️ 能见度较差，驾车减速慢行"
    else:
        return "极差", "🚨 能见度极差，建议减少外出"


def get_wind_level(speed):
    """风力等级"""
    if speed < 1:
        return "无风", 0
    elif speed < 6:
        return "微风", 1
    elif speed < 12:
        return "轻风", 2
    elif speed < 20:
        return "和风", 3
    elif speed < 29:
        return "劲风", 4
    elif speed < 39:
        return "强风", 5
    elif speed < 50:
        return "疾风", 6
    elif speed < 62:
        return "大风", 7
    elif speed < 75:
        return "烈风", 8
    elif speed < 89:
        return "狂风", 9
    elif speed < 103:
        return "暴风", 10
    elif speed < 117:
        return "狂暴风", 11
    else:
        return "飓风", 12


# ============================================================
# API 调用
# ============================================================

def fetch_weather(lat, lon, api_key, lang="zh_cn", units="metric", exclude=None):
    """调用 One Call API 3.0 获取天气数据"""
    url = "https://api.openweathermap.org/data/3.0/onecall"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "lang": lang,
        "units": units,
    }
    if exclude:
        params["exclude"] = exclude

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        status = resp.status_code
        if status == 401:
            logger.error(f"API Key 无效: {api_key[:8]}... 请检查配置")
        elif status == 429:
            logger.warning(f"API Key {api_key[:8]}... 调用次数已达上限")
        elif status == 402:
            logger.error(f"API Key {api_key[:8]}... 需要订阅 One Call API 3.0")
        else:
            logger.error(f"API 请求失败 (HTTP {status}): {e}")
    except requests.exceptions.RequestException as e:
        logger.error(f"网络错误: {e}")
    return None


def fetch_weather_with_rotation(lat, lon, config, lang=None, units=None, exclude=None):
    """使用多 Key 轮询调用 API，自动切换失败的 Key"""
    keys = config.get("api_keys", [])
    lang = lang or config.get("lang", "zh_cn")
    units = units or config.get("units", "metric")

    if not keys:
        logger.error("❌ 未配置 API Key")
        return None

    # 尝试所有 Key
    for i in range(len(keys)):
        key = get_next_key(config)
        logger.info(f"🔑 使用 Key: {key[:8]}... ({i+1}/{len(keys)})")
        data = fetch_weather(lat, lon, key, lang=lang, units=units, exclude=exclude)
        if data:
            return data
        logger.warning(f"⚠️ Key {key[:8]}... 失败，尝试下一个...")

    logger.error("❌ 所有 API Key 均调用失败")
    return None


# ============================================================
# Bark 推送（iPhone 即时通知）
# ============================================================

def send_bark(title, body, group="天气管家", sound="alarm.caf", url=None):
    """通过 Bark 发送推送通知到 iPhone"""
    config = load_env()
    bark_key = config.get("bark_key", "")
    if not bark_key:
        logger.debug("Bark 未配置，跳过推送")
        return False

    import urllib.parse
    try:
        # 基础 URL
        api_url = f"https://api.day.app/{bark_key}/{urllib.parse.quote(title)}/{urllib.parse.quote(body)}"
        extra = f"?group={urllib.parse.quote(group)}&sound={sound}"
        if url:
            extra += f"&url={urllib.parse.quote(url)}"
        api_url += extra

        resp = requests.get(api_url, timeout=8)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 200:
            logger.info(f"📲 Bark 推送成功: {title}")
            return True
        else:
            logger.warning(f"⚠️ Bark 推送返回异常: {result}")
            return False
    except Exception as e:
        logger.error(f"❌ Bark 推送失败: {e}")
        return False


def send_bark_alert(alerts, location_info):
    """推送恶劣天气预警"""
    now = datetime.now().strftime("%H:%M")
    city = location_info.get("city", "未知位置")
    title = f"🚨 {city} 恶劣天气预警"
    body_parts = []
    for a in alerts:
        body_parts.append(a["message"])
        if a.get("detail"):
            body_parts.append(f"→ {a['detail']}")
    body = "\n".join(body_parts)
    if len(body) > 500:
        body = body[:497] + "..."
    return send_bark(title, body, group="天气预警", sound="alarm.caf")


def send_bark_report_summary(data, location_info, report_type):
    """推送定时天气报告摘要"""
    now = datetime.now()
    city = location_info.get("city", "未知位置")
    current = data.get("current", {})
    temp = current.get("temp", 0)
    feels_like = current.get("feels_like", 0)

    weather_list = current.get("weather", [])
    weather_desc = WEATHER_CONDITIONS_CN.get(
        weather_list[0]["id"], weather_list[0].get("description", "未知")
    ) if weather_list else "未知"

    # 检测是否有预警
    alerts = check_severe_weather(data)
    if alerts:
        # 有预警就用预警推送
        return send_bark_alert(alerts, location_info)

    # 无预警则推送温和的摘要
    label = "🌅 早安" if report_type == "morning" else "☀️ 午后"
    title = f"{label} | {city} {weather_desc} {temp:.0f}°C"
    body = f"体感 {feels_like:.0f}°C"

    # 添加降水信息
    hourly = data.get("hourly", [])
    if hourly:
        max_pop = max(h.get("pop", 0) for h in hourly[:6])
        if max_pop >= 0.5:
            body += f" | 🌧️ 降水概率 {max_pop*100:.0f}%"
        elif max_pop >= 0.2:
            body += f" | 🌦️ 小雨概率 {max_pop*100:.0f}%"

    # 添加风力信息
    wind_speed = current.get("wind_speed", 0)
    if wind_speed >= 5:
        body += f" | 🌬️ 风速 {wind_speed:.0f}m/s"

    # 近几天趋势
    daily = data.get("daily", [])
    if len(daily) >= 2:
        d1 = daily[1]
        d1_w = WEATHER_CONDITIONS_CN.get(
            d1["weather"][0]["id"], d1["weather"][0].get("description", "")
        ) if d1.get("weather") else ""
        body += f"\n明日：{d1_w} {d1['temp']['min']:.0f}~{d1['temp']['max']:.0f}°C"

    return send_bark(title, body, group=f"天气汇总/{report_type}", sound="glass.caf")


# ============================================================
# OpenRouter AI 智能分析
# ============================================================

def call_openrouter(config, messages, temperature=0.7, max_tokens=800):
    """调用 OpenRouter API（兼容 OpenAI 格式）"""
    api_base = config.get("openrouter_api_base", "").rstrip("/")
    api_key = config.get("openrouter_api_key", "")
    model = config.get("openrouter_model", "")

    if not api_base or not api_key or not model:
        logger.debug("OpenRouter 未完整配置，跳过 AI 分析")
        return None

    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://weather-butler.local",
        "X-Title": "Weather Butler",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"].strip()
    except requests.exceptions.HTTPError as e:
        resp_text = resp.text if 'resp' in dir() else ""
        logger.error(f"❌ OpenRouter API 错误 ({resp.status_code if 'resp' in dir() else '?'}): {resp_text[:200]}")
    except Exception as e:
        logger.error(f"❌ OpenRouter 请求失败: {e}")
    return None


def generate_ai_butler_report(data, location_info, report_type):
    """用 AI 生成管家式天气分析"""
    config = load_env()
    if not config.get("openrouter_api_key"):
        return None

    city = location_info.get("city", "未知")
    region = location_info.get("region", "")
    location_str = f"{city}" + (f"，{region}" if region else "")

    current = data.get("current", {})
    daily = data.get("daily", [])
    hourly = data.get("hourly", [])
    alerts = data.get("alerts", [])

    # 提取关键数据
    temp = current.get("temp", 0)
    feels_like = current.get("feels_like", 0)
    humidity = current.get("humidity", 0)
    wind_speed = current.get("wind_speed", 0)
    wind_deg = current.get("wind_deg", 0)
    wind_gust = current.get("wind_gust", 0)
    visibility = current.get("visibility", 10000)
    pressure = current.get("pressure", 0)
    uvi = current.get("uvi", 0)
    clouds = current.get("clouds", 0)
    weather_list = current.get("weather", [])
    weather_desc = WEATHER_CONDITIONS_CN.get(
        weather_list[0]["id"], weather_list[0].get("description", "未知")
    ) if weather_list else "未知"
    wind_dir = wind_direction(wind_deg)

    # 未来几天摘要
    daily_summary = ""
    for i, d in enumerate(daily[:4]):
        d_time = datetime.fromtimestamp(d["dt"])
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d_time.weekday()]
        d_w = WEATHER_CONDITIONS_CN.get(
            d["weather"][0]["id"], d["weather"][0].get("description", "")
        ) if d.get("weather") else "未知"
        pop = d.get("pop", 0)
        pop_str = f"，降水概率 {pop*100:.0f}%" if pop >= 0.2 else ""
        daily_summary += f"- {weekday}：{d['temp']['min']:.0f}~{d['temp']['max']:.0f}°C，{d_w}{pop_str}\n"

    # 恶劣天气列表
    severe = check_severe_weather(data)
    severe_str = ""
    for a in severe:
        severe_str += f"- {a['message']} → {a.get('detail','')}\n"

    # 政府警报
    alert_str = ""
    for a in alerts:
        alert_str += f"- {a.get('event','警报')}：{a.get('description','')[:100]}...\n"

    label = "🌅 早安" if report_type == "morning" else "☀️ 午后"
    time_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    # 更强的中文强制 prompt
    system_prompt = """你是一位专业的天气管家，服务于宁波象山的居民。你说话风格亲切、专业、有条理，像一位贴心的管家。

【强制要求】
- 必须全程用中文回答，不要出现任何英文单词或字母
- 回复长度控制在 200-350 字之间
- 用自然段落形式，不要用列表格式
- 内容包含：开场问候、当前天气、穿衣建议、出行提醒、今日活动、未来展望、结束祝福

【天气管家口吻示例】
"主人早安，今天象山..."
"穿衣方面建议..."
"出行请注意..."
"今日适合做..."
"今日不宜做..."
"未来几天..."
"祝您有美好的一天！"

【禁止】
- 出现任何英文单词（weather, temperature, humidity 等）
- 回复开头是 "The" 或英文
- 使用 markdown 列表格式"""

    user_prompt = f"""请用中文为宁波象山的用户生成天气汇报。如果模型不遵循中文指令，强制用中文回答。

地点：{location_str}
时间：{time_str}

当前天气数据：
- 天气状况：{weather_desc}
- 气温：{temp:.1f}°C（体感 {feels_like:.1f}°C）
- 湿度：{humidity}%
- 风力：{wind_dir} {wind_speed:.1f}m/s（阵风 {wind_gust:.1f}m/s）
- 能见度：{visibility/1000:.1f}km
- 气压：{pressure} hPa
- UV指数：{uvi}

未来12小时：
{chr(10).join(f"{datetime.fromtimestamp(h['dt']).strftime('%H:%M')}：{h.get('temp',0):.0f}°C，{WEATHER_CONDITIONS_CN.get(h['weather'][0]['id'], h['weather'][0].get('description','')) if h.get('weather') else '未知'}，降水{h.get('pop',0)*100:.0f}%" for h in hourly[:12])}

未来几天：{daily_summary}

恶劣天气：{severe_str if severe_str else '无'}
政府警报：{alert_str if alert_str else '无'}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 第一次调用
    ai_report = call_openrouter(config, messages, temperature=0.8, max_tokens=800)
    
    # 如果太短或英文，重试
    if ai_report:
        chinese_chars = sum(1 for c in ai_report if '\u4e00' <= c <= '\u9fff')
        if chinese_chars < 30 or len(ai_report) < 50 or ai_report.startswith("The "):
            logger.warning(f"⚠️ AI 首次回复不理想（{len(ai_report)}字，中文{chinese_chars}字），重试...")
            ai_report = call_openrouter(config, messages, temperature=0.6, max_tokens=1000)
    
    return ai_report


def chunk_text(text, max_chars=380):
    """将长文本智能分段，每段保留完整语义"""
    if not text:
        return []
    paragraphs = text.split("\n")
    parts = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > max_chars:
            if current.strip():
                parts.append(current.strip())
                current = ""
            sentences = []
            for sep in ["。", "！", "？", "；"]:
                if sep in para:
                    for s in para.split(sep):
                        s = s.strip() + sep
                        if s.strip() and s != sep:
                            sentences.append(s)
                    break
            if not sentences:
                sentences = [para]
            for s in sentences:
                if len(s) > max_chars:
                    for s2 in s.split("，"):
                        s2 = s2.strip() + "，"
                        if len(current) + len(s2) > max_chars:
                            if current.strip():
                                parts.append(current.strip())
                            current = s2
                        else:
                            current += s2
                elif len(current) + len(s) > max_chars:
                    if current.strip():
                        parts.append(current.strip())
                    current = s
                else:
                    current += s
        elif len(current) + len(para) > max_chars:
            if current.strip():
                parts.append(current.strip())
            current = para + "\n"
        else:
            current += para + "\n"
    if current.strip():
        parts.append(current.strip())
    return [p for p in parts if p] if parts else [text[:max_chars]]


def send_bark_ai_report(data, location_info, report_type):
    """推送 AI 生成的管家报告"""
    city = location_info.get("city", "未知")
    label = "🌅 早安" if report_type == "morning" else "☀️ 午后"

    ai_report = generate_ai_butler_report(data, location_info, report_type)
    current = data.get("current", {})
    temp = current.get("temp", 0)
    weather_list = current.get("weather", [])
    weather_desc = WEATHER_CONDITIONS_CN.get(
        weather_list[0]["id"], weather_list[0].get("description", "未知")
    ) if weather_list else "未知"

    # 检查 AI 报告是否有效
    if not ai_report or len(ai_report) < 30:
        logger.warning("⚠️ AI 报告无效，降级到模板报告")
        return send_bark_report_summary(data, location_info, report_type)

    # 检查是否含足够中文
    chinese_chars = sum(1 for c in ai_report if '\u4e00' <= c <= '\u9fff')
    if chinese_chars < 20:
        logger.warning(f"⚠️ AI 报告中文不足 ({chinese_chars}字)，降级到模板报告")
        return send_bark_report_summary(data, location_info, report_type)

    # 合并成一条完整通知
    # 标题: "🌅 早安 | 象山 阴天 23°C"
    # 内容: 去掉 AI 报告开头可能的称呼，直接用自然段
    body = ai_report.strip()
    # 如果太长则截断
    if len(body) > 450:
        body = body[:447] + "..."

    title = f"{label} | {city} {weather_desc} {temp:.0f}°C"
    logger.info(f"📝 AI 报告已生成 ({len(ai_report)}字)，推送1条通知")

    send_bark(
        title,
        body,
        group=f"天气汇总/{report_type}",
        sound="glass.caf",
    )
    return True


# ============================================================
# 恶劣天气检测
# ============================================================

def check_severe_weather(data):
    """检测恶劣天气，返回预警信息列表"""
    alerts = []
    now = time.time()

    # 1. 检查当前天气
    current = data.get("current", {})
    weather_list = current.get("weather", [])
    for w in weather_list:
        wid = w.get("id", 0)
        if wid in SEVERE_WEATHER_IDS:
            alerts.append({
                "type": "current_severe",
                "level": "danger",
                "message": f"⚠️ 当前天气恶劣：{WEATHER_CONDITIONS_CN.get(wid, w.get('description', '未知'))}",
                "detail": w.get("description", ""),
            })

    # 2. 检查风速
    wind_speed = current.get("wind_speed", 0)
    wind_gust = current.get("wind_gust", 0)
    if wind_gust >= 20 or wind_speed >= 15:
        level_name, level_num = get_wind_level(max(wind_speed, wind_gust))
        alerts.append({
            "type": "high_wind",
            "level": "warning" if level_num < 8 else "danger",
            "message": f"🌬️ {level_name}预警：风速 {wind_speed:.1f}m/s，阵风 {wind_gust:.1f}m/s",
            "detail": "注意固定户外物品，减少外出" if level_num >= 6 else "外出注意安全",
        })

    # 3. 检查能见度
    visibility = current.get("visibility", 10000)
    if visibility < 2000:
        desc, _ = visibility_desc(visibility)
        alerts.append({
            "type": "low_visibility",
            "level": "warning",
            "message": f"👁️ 能见度{desc}：{visibility}m",
            "detail": "驾车请减速慢行，开雾灯" if visibility < 1000 else "出行注意安全",
        })

    # 4. 检查极端温度
    temp = current.get("temp", 20)
    if temp <= -15:
        alerts.append({
            "type": "extreme_cold",
            "level": "danger",
            "message": f"🥶 极端低温：{temp:.1f}°C",
            "detail": "严寒天气，尽量减少外出，注意防冻",
        })
    elif temp >= 40:
        alerts.append({
            "type": "extreme_heat",
            "level": "danger",
            "message": f"🔥 极端高温：{temp:.1f}°C",
            "detail": "高温预警！避免户外活动，注意防暑降温",
        })

    # 5. 检查分钟级降水
    minutely = data.get("minutely", [])
    heavy_rain_count = 0
    for m in minutely[:30]:  # 检查未来30分钟
        if m.get("precipitation", 0) > 2.0:
            heavy_rain_count += 1
    if heavy_rain_count >= 5:
        alerts.append({
            "type": "incoming_heavy_rain",
            "level": "warning",
            "message": f"🌧️ 未来30分钟内有强降水（{heavy_rain_count}分钟降水量>2mm）",
            "detail": "请尽快携带雨具或寻找避雨处",
        })

    # 6. 检查政府天气警报
    gov_alerts = data.get("alerts", [])
    for a in gov_alerts:
        event = a.get("event", "天气警报")
        desc = a.get("description", "")
        # 截取前200字
        if len(desc) > 200:
            desc = desc[:200] + "..."
        alerts.append({
            "type": "government_alert",
            "level": "danger",
            "message": f"🚨 政府天气警报：{event}",
            "detail": desc,
        })

    return alerts


# ============================================================
# 管家式报告生成
# ============================================================

def generate_butler_report(data, location_info, report_type="morning"):
    """生成管家式天气报告"""
    current = data.get("current", {})
    daily = data.get("daily", [])
    hourly = data.get("hourly", [])
    minutely = data.get("minutely", [])

    now = datetime.now()
    time_label = "🌅 早安汇报" if report_type == "morning" else "☀️ 午后汇报"
    greeting = "早上好！" if report_type == "morning" else "下午好！"

    city = location_info.get("city", "您的位置")
    region = location_info.get("region", "")
    country = location_info.get("country", "")
    location_str = f"{city}" + (f"，{region}" if region else "") + (f"，{country}" if country else "")

    lines = []
    lines.append(f"{'='*50}")
    lines.append(f"  🏠 天气管家 · {time_label}")
    lines.append(f"  📍 {location_str}")
    lines.append(f"  🕐 {now.strftime('%Y年%m月%d日 %H:%M')}")
    lines.append(f"{'='*50}")
    lines.append("")
    lines.append(f"{greeting} 我是您的天气管家，为您整理了最新的天气情况：")
    lines.append("")

    # ---- 当前天气 ----
    temp = current.get("temp", 0)
    feels_like = current.get("feels_like", 0)
    humidity = current.get("humidity", 0)
    pressure = current.get("pressure", 0)
    visibility = current.get("visibility", 10000)
    wind_speed = current.get("wind_speed", 0)
    wind_gust = current.get("wind_gust", 0)
    wind_deg = current.get("wind_deg", 0)
    uvi = current.get("uvi", 0)
    clouds = current.get("clouds", 0)
    dew_point = current.get("dew_point", 0)
    weather_list = current.get("weather", [])

    weather_desc = WEATHER_CONDITIONS_CN.get(
        weather_list[0]["id"], weather_list[0].get("description", "未知")
    ) if weather_list else "未知"

    temp_feel, temp_advice = temp_feeling(temp)
    humid_feel, humid_advice = humidity_feeling(humidity)
    vis_desc, vis_advice = visibility_desc(visibility)
    wind_name, wind_num = get_wind_level(wind_speed)
    wind_dir = wind_direction(wind_deg)
    uv_level, uv_advice = uv_info(uvi)

    lines.append("📋 【当前天气概况】")
    lines.append(f"   天气状况：{weather_desc}")
    lines.append(f"   温度：{temp:.1f}°C（体感 {feels_like:.1f}°C）— {temp_feel}")
    lines.append(f"   湿度：{humidity}% — {humid_feel}")
    lines.append(f"   风况：{wind_dir} {wind_name} {wind_speed:.1f}m/s" +
                 (f"，阵风 {wind_gust:.1f}m/s" if wind_gust else ""))
    lines.append(f"   能见度：{visibility/1000:.1f}km — {vis_desc}")
    lines.append(f"   云量：{clouds}%")
    lines.append(f"   UV 指数：{uvi}（{uv_level}）")
    lines.append(f"   气压：{pressure} hPa")
    lines.append("")

    # ---- 管家建议 ----
    lines.append("💡 【管家建议】")
    lines.append(f"   🌡️ 穿衣：{temp_advice}")
    lines.append(f"   💧 湿度：{humid_advice}")
    # 检查未来几小时降水概率
    rain_needed = any(h.get("pop", 0) >= 0.3 for h in hourly[:6])
    rain_in_min = any(m.get("precipitation", 0) > 0 for m in minutely[:15])
    lines.append("   🌂 雨具：" + ("🌧️ 未来几小时有降水可能，建议携带雨具" if rain_needed else
                  "🌧️ 近期可能有零星降水，建议备好雨具" if rain_in_min else
                  "✅ 短期内无降水，无需雨具"))
    lines.append(f"   ☀️ 防晒：{uv_advice}")
    lines.append(f"   👁️ 出行：{vis_advice}")
    lines.append("")

    # ---- 活动建议 ----
    lines.append("🎯 【今日活动建议】")
    lines.append("")

    # 判断适合/不适合的活动
    suitable = []
    unsuitable = []

    # 温度相关
    if 15 <= temp <= 28:
        suitable.append("🏃 户外跑步/骑行")
        suitable.append("🚶 散步/逛公园")
    elif temp < 5 or temp > 35:
        unsuitable.append("🏃 户外运动（温度极端）")
    elif 5 <= temp < 15:
        suitable.append("🚶 散步（注意保暖）")
        unsuitable.append("🏃 剧烈户外运动")
    elif 28 < temp <= 35:
        suitable.append("🏊 游泳/水上活动")
        unsuitable.append("🏃 剧烈户外运动（注意防暑）")

    # 降水相关
    has_rain_today = False
    for h in hourly[:12]:
        if h.get("pop", 0) >= 0.5:
            has_rain_today = True
            break
    if has_rain_today:
        unsuitable.append("📸 户外摄影")
        unsuitable.append("🌿 野餐/露营")
        suitable.append("☕ 室内咖啡馆/书店")
        suitable.append("🎬 看电影/逛商场")
    else:
        suitable.append("📸 户外摄影（光线好）")
        if 18 <= temp <= 30:
            suitable.append("🌿 公园野餐")

    # 风力相关
    if wind_speed >= 8:
        unsuitable.append("🪁 放风筝（风太大）")
        unsuitable.append("🚴 骑行（风大不安全）")
    elif wind_speed >= 3:
        suitable.append("🪁 放风筝（风力刚好）")

    # UV 相关
    if uvi >= 8:
        unsuitable.append("🏖️ 长时间户外暴晒")
    elif uvi >= 3 and not has_rain_today:
        suitable.append("🏖️ 户外休闲（注意防晒）")

    # 能见度相关
    if visibility < 2000:
        unsuitable.append("🚗 长途自驾（能见度差）")
    else:
        suitable.append("🚗 自驾出行")

    # 空气质量（如果有）
    if humidity >= 80 and temp > 25:
        unsuitable.append("🏋️ 户外锻炼（闷热潮湿）")
        suitable.append("🏋️ 室内健身")

    if suitable:
        lines.append("   ✅ 适合做的事：")
        for s in suitable:
            lines.append(f"      {s}")
    lines.append("")
    if unsuitable:
        lines.append("   ❌ 不建议做的事：")
        for u in unsuitable:
            lines.append(f"      {u}")
    lines.append("")

    # ---- 今日逐时预报 ----
    lines.append("⏰ 【逐时预报（未来12小时）】")
    for h in hourly[:12]:
        h_time = datetime.fromtimestamp(h["dt"])
        h_temp = h.get("temp", 0)
        h_weather = WEATHER_CONDITIONS_CN.get(
            h["weather"][0]["id"], h["weather"][0].get("description", "")
        ) if h.get("weather") else "未知"
        h_pop = h.get("pop", 0)
        h_wind = h.get("wind_speed", 0)
        pop_str = f"🌧️{h_pop*100:.0f}%" if h_pop >= 0.2 else ""
        wind_str = f"🌬️{h_wind:.0f}m/s" if h_wind >= 5 else ""
        lines.append(
            f"   {h_time.strftime('%H:%M')} | {h_temp:.0f}°C | {h_weather}"
            f" {pop_str} {wind_str}"
        )
    lines.append("")

    # ---- 未来几天趋势 ----
    if daily:
        lines.append("📅 【未来几天趋势】")
        for d in daily[:4]:
            d_time = datetime.fromtimestamp(d["dt"])
            d_temp_min = d["temp"]["min"]
            d_temp_max = d["temp"]["max"]
            d_weather = WEATHER_CONDITIONS_CN.get(
                d["weather"][0]["id"], d["weather"][0].get("description", "")
            ) if d.get("weather") else "未知"
            d_pop = d.get("pop", 0)
            weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d_time.weekday()]
            pop_str = f" | 降水概率 {d_pop*100:.0f}%" if d_pop >= 0.2 else ""
            lines.append(
                f"   {weekday}({d_time.strftime('%m/%d')}) "
                f"{d_temp_min:.0f}°~{d_temp_max:.0f}°C {d_weather}{pop_str}"
            )
        lines.append("")

    # ---- 恶劣天气提醒 ----
    severe = check_severe_weather(data)
    if severe:
        lines.append("🚨 【恶劣天气预警】")
        for a in severe:
            lines.append(f"   {a['message']}")
            if a.get("detail"):
                lines.append(f"   └─ {a['detail']}")
        lines.append("")

    lines.append(f"{'='*50}")
    lines.append("  🤖 您的天气管家，祝您有美好的一天！")
    lines.append(f"{'='*50}")

    return "\n".join(lines)


def generate_alert_message(alerts, location_info):
    """生成恶劣天气预警消息"""
    city = location_info.get("city", "您的位置")
    now = datetime.now().strftime("%H:%M")
    lines = []
    lines.append(f"🚨🚨🚨 恶劣天气预警 🚨🚨🚨")
    lines.append(f"📍 {city} | ⏰ {now}")
    lines.append("")
    for a in alerts:
        lines.append(f"  {a['message']}")
        if a.get("detail"):
            lines.append(f"  └─ {a['detail']}")
        lines.append("")
    lines.append("⚠️ 请注意安全，做好防护准备！")
    return "\n".join(lines)


# ============================================================
# 主程序
# ============================================================

def main():
    """主程序入口"""
    config = load_env()

    if not config["api_keys"] or (len(config["api_keys"]) == 1 and config["api_keys"][0] == "your_api_key_here"):
        logger.error("❌ 请先配置 API Key！")
        logger.error("   1. 访问 https://home.openweathermap.org/users/sign_up 注册账号")
        logger.error("   2. 在 https://home.openweathermap.org/api_keys 获取 API Key")
        logger.error("   3. 在 .env 文件中填入 API_KEYS=key1,key2,...")
        logger.error("   4. 在 https://home.openweathermap.org/subscriptions 订阅 One Call API 3.0（免费1000次/天）")
        print("\n" + "="*60)
        print("❌ API Key 未配置！请按以下步骤操作：")
        print("="*60)
        print("1. 打开 https://home.openweathermap.org/users/sign_up 注册")
        print("2. 验证邮箱后，前往 https://home.openweathermap.org/api_keys 获取 Key")
        print("3. 前往 https://home.openweathermap.org/subscriptions")
        print("   订阅 One Call API 3.0（免费额度 1000次/天）")
        print("4. 在 .env 中填入 API_KEYS=key1,key2,...")
        print("="*60)
        sys.exit(1)

    logger.info(f"🔑 已加载 {len(config['api_keys'])} 个 API Key，将轮询调用")

    # 获取位置
    logger.info("🌍 正在获取当前位置...")
    if config["lat"] and config["lon"]:
        location_info = {
            "lat": config["lat"],
            "lon": config["lon"],
            "city": config.get("location_name", "手动设置位置"),
            "region": "",
            "country": "",
        }
    else:
        location_info = get_location()
        if not location_info:
            logger.error("❌ 无法获取位置，请手动在 .env 中设置 lat 和 lon")
            sys.exit(1)
        logger.info(f"📍 定位成功：{location_info['city']}，{location_info['region']}，{location_info['country']}")

    lat = location_info["lat"]
    lon = location_info["lon"]

    # 确保报告目录存在
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 加载状态
    state = load_state()

    # 检查是否新的一天，重置计数
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("call_date") != today:
        state["call_count_today"] = 0
        state["call_date"] = today
        state["last_alert_time"] = 0
        save_state(state)

    # 检查是否需要生成报告
    now = datetime.now()
    current_hour = now.hour
    current_time_str = now.strftime("%H:%M")
    report_type = None

    if current_hour == 8 and state.get("last_report_time") != f"{today}_08":
        report_type = "morning"
        state["last_report_time"] = f"{today}_08"
    elif current_hour == 13 and state.get("last_report_time") != f"{today}_13":
        report_type = "afternoon"
        state["last_report_time"] = f"{today}_13"

    # 调用 API（轮询多 Key）
    logger.info(f"🌤️ 正在获取天气数据...（今日第 {state['call_count_today']+1} 次，共 {len(config['api_keys'])} 个 Key）")
    data = fetch_weather_with_rotation(
        lat, lon, config,
        lang=config["lang"],
        units=config["units"],
    )

    if not data:
        logger.error("❌ 获取天气数据失败")
        sys.exit(1)

    # 更新调用计数
    state["call_count_today"] += 1
    state["location"] = location_info
    save_state(state)

    logger.info(f"✅ 天气数据获取成功（{state['call_count_today']}/1000）")

    # 恶劣天气检测
    alerts = check_severe_weather(data)
    if alerts:
        # 避免频繁报警（至少间隔30分钟）
        last_alert = state.get("last_alert_time", 0)
        if time.time() - last_alert > 1800:
            alert_msg = generate_alert_message(alerts, location_info)
            print("\n" + alert_msg)
            logger.warning("🚨 检测到恶劣天气！")
            state["last_alert_time"] = time.time()
            save_state(state)

            # 保存预警
            alert_file = REPORT_DIR / f"alert_{now.strftime('%Y%m%d_%H%M')}.txt"
            with open(alert_file, "w", encoding="utf-8") as f:
                f.write(alert_msg)
            logger.info(f"📄 预警已保存：{alert_file}")

            # Bark 推送
            if config.get("bark_key"):
                send_bark_alert(alerts, location_info)

    # 生成定时报告
    if report_type:
        report = generate_butler_report(data, location_info, report_type)
        print("\n" + report)

        # 保存报告
        report_file = REPORT_DIR / f"report_{now.strftime('%Y%m%d')}_{report_type}.txt"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"📄 报告已保存：{report_file}")
        state["last_report_date"] = today
        save_state(state)

        # AI 生成管家报告并推送
        if config.get("bark_key"):
            ai_report = generate_ai_butler_report(data, location_info, report_type)
            # 保存 AI 报告到文件
            ai_report_file = REPORT_DIR / f"ai_report_{now.strftime('%Y%m%d')}_{report_type}.txt"
            with open(ai_report_file, "w", encoding="utf-8") as f:
                f.write(f"{'='*50}\n")
                f.write(f"  🏠 AI 天气管家 · {report_type}\n")
                f.write(f"  📍 {location_info.get('city','')} | {now.strftime('%Y年%m月%d日 %H:%M')}\n")
                f.write(f"{'='*50}\n\n")
                if ai_report:
                    f.write(ai_report)
                else:
                    # AI 不可用时降级
                    fallback = generate_butler_report(data, location_info, report_type)
                    f.write(fallback)
                f.write(f"\n{'='*50}\n")
            logger.info(f"🤖 AI 报告已保存：{ai_report_file}")
            # 推送到 iPhone
            send_bark_ai_report(data, location_info, report_type)
            # 打印到终端
            print(f"\n{'='*50}")
            print(f"  🤖 AI 天气管家 · {report_type}")
            print(f"  📍 {location_info.get('city','')} | {now.strftime('%Y年%m月%d日 %H:%M')}")
            print(f"{'='*50}\n")
            if ai_report:
                print(ai_report)
            else:
                print(generate_butler_report(data, location_info, report_type))
        else:
            # 无 Bark 时只打印报告
            print(generate_butler_report(data, location_info, report_type))

    # 如果既不是报告时间也没有预警，输出简要信息
    if not report_type and not alerts:
        current = data.get("current", {})
        temp = current.get("temp", 0)
        weather_list = current.get("weather", [])
        weather_desc = WEATHER_CONDITIONS_CN.get(
            weather_list[0]["id"], weather_list[0].get("description", "未知")
        ) if weather_list else "未知"
        logger.info(f"🌡️ 当前：{weather_desc} {temp:.1f}°C | 调用 {state['call_count_today']}/1000")


if __name__ == "__main__":
    main()
