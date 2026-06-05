#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成天气卡片图片"""
from PIL import Image, ImageDraw, ImageFont
import math

# 天气图标像素艺术（简化版，用emoji风格表示）
def create_weather_card(weather_desc, temp, feels_like, humidity, wind_speed, weather_icon, report_type, location_name):
    """生成一张天气卡片图片"""
    width, height = 380, 220

    # 背景色：根据天气类型
    if "晴" in weather_desc or "☀️" in weather_icon:
        bg_r, bg_g, bg_b = 135, 206, 250  # 浅蓝天
    elif "雨" in weather_desc:
        bg_r, bg_g, bg_b = 70, 130, 180   # SteelBlue
    elif "阴" in weather_desc or "多云" in weather_desc or "☁️" in weather_icon:
        bg_r, bg_g, bg_b = 105, 105, 120  # 深灰蓝
    elif "雪" in weather_desc:
        bg_r, bg_g, bg_b = 176, 224, 230  # 浅蓝
    else:
        bg_r, bg_g, bg_b = 100, 149, 237  # CornflowerBlue

    img = Image.new("RGB", (width, height), (bg_r, bg_g, bg_b))
    draw = ImageDraw.Draw(img)

    # 圆角矩形背景（简单用矩形+渐变感）
    # 添加半透明覆盖增加层次
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # 绘制渐变底部
    for y in range(height // 2, height):
        alpha = int(60 * (y - height // 2) / (height // 2))
        overlay_draw.rectangle([(0, y), (width, y + 1)], fill=(0, 0, 0, alpha))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # 重新获取 draw
    draw = ImageDraw.Draw(img)

    # 尝试加载字体
    try:
        # 尝试系统字体
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_tiny = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        # 使用默认字体
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_tiny = ImageFont.load_default()

    # 绘制分隔线
    draw.line([(20, 100), (width - 20, 100)], fill=(255, 255, 255, 80), width=1)

    # 绘制内容
    white = (255, 255, 255)
    light_blue = (200, 230, 255)

    # 顶部：位置和时间
    draw.text((width // 2, 15), location_name, fill=light_blue, font=font_small, anchor="mt")
    draw.text((width // 2, 35), report_type, fill=white, font=font_medium, anchor="mt")

    # 中部：天气图标（大emoji占位）
    draw.text((30, 60), weather_icon, fill=white, font=font_large)

    # 温度（主温度）
    draw.text((130, 50), f"{temp:.0f}°", fill=white, font=font_large)
    draw.text((200, 55), "C", fill=light_blue, font=font_medium)

    # 体感温度
    draw.text((130, 100), f"体感 {feels_like:.0f}°C", fill=light_blue, font=font_tiny)

    # 天气描述
    draw.text((240, 55), weather_desc, fill=white, font=font_medium)

    # 底部：湿度和风力
    draw.text((25, 140), f"💧 湿度 {humidity}%", fill=white, font=font_small)
    draw.text((25, 165), f"🌬️ 风速 {wind_speed:.1f} m/s", fill=white, font=font_small)

    # 右侧：更多信息（降水概率等）
    draw.text((25, 195), f"🌤️ 天气管家 · AI智能分析", fill=light_blue, font=font_tiny)

    return img
