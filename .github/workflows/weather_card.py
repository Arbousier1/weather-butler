#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成天气卡片图片（含天气图标）"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import requests
import math
import os

def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def create_weather_card(weather_desc, temp, feels_like, humidity, wind_speed, weather_icon, report_type, location_name, icon_code="04d"):
    """生成一张精美的天气卡片 PNG，返回 base64 data URL"""
    width, height = 380, 220

    # 背景色方案
    if "晴" in weather_desc:
        bg = (135, 206, 250)
    elif "雨" in weather_desc:
        bg = (70, 130, 180)
    elif "阴" in weather_desc or "多云" in weather_desc:
        bg = (90, 100, 130)
    elif "雪" in weather_desc:
        bg = (176, 224, 230)
    else:
        bg = (100, 149, 237)

    # 创建背景
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    # 添加装饰性渐变底部
    for y in range(height - 60, height):
        alpha = int(60 * (y - (height - 60)) / 60)
        overlay_color = (
            max(0, bg[0] - alpha * 2),
            max(0, bg[1] - alpha),
            min(255, bg[2] + alpha)
        )
        draw.line([(0, y), (width, y)], fill=overlay_color)

    # 尝试加载字体
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    font_large, font_medium, font_small, font_tiny = None, None, None, None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font_large = ImageFont.truetype(fp, 52)
                font_medium = ImageFont.truetype(fp, 24)
                font_small = ImageFont.truetype(fp, 18)
                font_tiny = ImageFont.truetype(fp, 14)
                break
            except:
                continue
    if font_large is None:
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large
        font_tiny = font_large

    white = (255, 255, 255)
    light = (200, 220, 255)
    accent = (255, 230, 100)

    # ===== 左侧：天气图标区域 =====
    # 下载 OpenWeatherMap 天气图标
    icon_url = f"https://openweathermap.org/img/wn/{icon_code}@2x.png"
    try:
        icon_resp = requests.get(icon_url, timeout=5)
        if icon_resp.status_code == 200:
            from io import BytesIO
            weather_icon_img = Image.open(BytesIO(icon_resp.content)).convert("RGBA")
            # 调整图标大小
            icon_size = 90
            weather_icon_img = weather_icon_img.resize((icon_size, icon_size), Image.LANCZOS)
            # 粘贴到卡片上
            img.paste(weather_icon_img, (25, 60), weather_icon_img)
    except Exception:
        # 图标下载失败，用 emoji 文字代替
        pass

    # ===== 主温度 =====
    temp_str = f"{temp:.0f}°"
    draw.text((125, 35), temp_str, fill=white, font=font_large)

    # ===== 位置 + 时间 =====
    draw.text((20, 8), location_name, fill=light, font=font_tiny)
    draw.text((20, 25), report_type, fill=light, font=font_small)

    # ===== 分隔线 =====
    draw.line([(120, 50), (120, 170)], fill=(255, 255, 255, 60), width=1)

    # ===== 右侧：详细数据 =====
    x_data = 140

    # 体感温度
    draw.text((x_data, 50), f"体感温度  {feels_like:.0f}°C", fill=white, font=font_small)

    # 湿度
    draw.text((x_data, 75), f"💧 湿度     {humidity}%", fill=white, font=font_small)

    # 风力
    draw.text((x_data, 100), f"🌬️ 风速     {wind_speed:.1f} m/s", fill=white, font=font_small)

    # 天气描述
    draw.text((x_data, 125), f"🌥️ {weather_desc}", fill=white, font=font_small)

    # ===== 底部装饰 =====
    draw.line([(15, 160), (width - 15, 160)], fill=(255, 255, 255, 40), width=1)

    # 温度计可视化条
    temp_ratio = max(0, min(1, (temp - 0) / 40))  # 0-40度映射到 0-1
    bar_width = int(300 * temp_ratio)
    draw.rectangle([(x_data, 172), (x_data + 300, 185)], fill=(40, 40, 60))
    draw.rectangle([(x_data, 172), (x_data + bar_width, 185)], fill=(255, 100, 80) if temp > 25 else (80, 160, 255) if temp < 15 else (100, 200, 150))
    draw.text((x_data, 168), "🌡️ 体感温度指示", fill=light, font=font_tiny)
    draw.text((x_data + bar_width + 5, 173), f"{temp:.0f}°", fill=white, font=font_tiny)

    # ===== 底部品牌 =====
    draw.text((width // 2, 200), "🤖 AI Weather Butler", fill=(180, 200, 220), font=font_tiny, anchor="mt")

    return img


def weather_card_to_base64(img, format="PNG"):
    """将 PIL Image 转为 base64 data URL"""
    from io import BytesIO
    buffer = BytesIO()
    img.save(buffer, format=format, quality=85)
    import base64
    b64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/{format.lower()};base64,{b64}"


if __name__ == "__main__":
    # 测试
    card = create_weather_card("阴天", 23, 24, 82, 2.5, "☁️", "📋 天气快报", "宁波象山", "04d")
    data_url = weather_card_to_base64(card)
    print(f"图片 base64 长度: {len(data_url)}")
    card.save("/tmp/test_weather_card.png")
    print("测试图片已保存到 /tmp/test_weather_card.png")
