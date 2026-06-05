#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌤️ 天气管家 - 持续监控模式
每 86 秒调用一次 API，检测恶劣天气并预警
"""

import os
import sys
import time
import json
import signal
from datetime import datetime
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from weather_butler import (
    load_env, load_state, save_state, get_location,
    fetch_weather_with_rotation, check_severe_weather,
    generate_butler_report, generate_alert_message,
    send_bark_alert, send_bark_report_summary,
    REPORT_DIR, STATE_FILE, logger
)

# 优雅退出标志
running = True

def signal_handler(sig, frame):
    global running
    logger.info("🛑 收到停止信号，正在优雅退出...")
    running = False

def main():
    global running
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    config = load_env()
    if not config["api_key"] or config["api_key"] == "your_api_key_here":
        logger.error("❌ API Key 未配置！请先配置 .env 文件")
        sys.exit(1)

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
            logger.error("❌ 无法获取位置")
            sys.exit(1)

    logger.info(f"📍 位置：{location_info['city']}，{location_info.get('region', '')}，{location_info.get('country', '')}")
    logger.info(f"📊 坐标：{location_info['lat']:.4f}, {location_info['lon']:.4f}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    lat = location_info["lat"]
    lon = location_info["lon"]

    logger.info("=" * 50)
    logger.info("🌤️ 天气管家持续监控已启动")
    logger.info(f"⏱️ 调用间隔：86秒")
    logger.info(f"🔑 API Key 数量：{len(config.get('api_keys', []))} 个（轮询负载均衡）")
    logger.info(f"📋 定时汇报：每天 08:00 和 13:00")
    logger.info("=" * 50)

    while running:
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")

            # 新的一天重置计数
            if state.get("call_date") != today:
                state["call_count_today"] = 0
                state["call_date"] = today
                state["last_alert_time"] = 0
                state["last_report_time"] = ""
                save_state(state)
                logger.info(f"📅 新的一天开始，调用次数已重置")

            # 检查调用次数
            if state["call_count_today"] >= 1000:
                logger.warning("⚠️ 今日调用次数已达上限（1000次），等待明天...")
                # 等到明天
                while running and datetime.now().strftime("%Y-%m-%d") == today:
                    time.sleep(60)
                continue

            # 调用 API（轮询多 Key）
            logger.info(f"🌤️ 获取天气数据...（{state['call_count_today']+1} 次）")
            data = fetch_weather_with_rotation(
                lat, lon, config,
                lang=config["lang"],
                units=config["units"],
            )

            if not data:
                logger.error("❌ 获取天气数据失败，86秒后重试...")
                for _ in range(86):
                    if not running:
                        break
                    time.sleep(1)
                continue

            state["call_count_today"] += 1
            state["location"] = location_info
            save_state(state)

            # 恶劣天气检测
            alerts = check_severe_weather(data)
            if alerts:
                last_alert = state.get("last_alert_time", 0)
                if time.time() - last_alert > 1800:  # 30分钟冷却
                    alert_msg = generate_alert_message(alerts, location_info)
                    print("\n" + "=" * 50)
                    print(alert_msg)
                    print("=" * 50 + "\n")
                    logger.warning("🚨 检测到恶劣天气！")
                    state["last_alert_time"] = time.time()
                    save_state(state)

                    alert_file = REPORT_DIR / f"alert_{now.strftime('%Y%m%d_%H%M')}.txt"
                    with open(alert_file, "w", encoding="utf-8") as f:
                        f.write(alert_msg)
                    if config.get("bark_key"):
                        send_bark_alert(alerts, location_info)

            # 定时报告
            current_hour = now.hour
            report_type = None

            if current_hour == 8 and state.get("last_report_time") != f"{today}_08":
                report_type = "morning"
                state["last_report_time"] = f"{today}_08"
            elif current_hour == 13 and state.get("last_report_time") != f"{today}_13":
                report_type = "afternoon"
                state["last_report_time"] = f"{today}_13"

            if report_type:
                report = generate_butler_report(data, location_info, report_type)
                print("\n" + report + "\n")
                report_file = REPORT_DIR / f"report_{now.strftime('%Y%m%d')}_{report_type}.txt"
                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(report)
                logger.info(f"📄 报告已保存：{report_file}")
                if config.get("bark_key"):
                    send_bark_report_summary(data, location_info, report_type)
                save_state(state)

            # 简要状态
            current = data.get("current", {})
            temp = current.get("temp", 0)
            wl = current.get("weather", [])
            desc = wl[0].get("description", "") if wl else ""
            logger.info(
                f"🌡️ {desc} {temp:.1f}°C | "
                f"已用 {state['call_count_today']}/1000 | "
                f"下次汇报：{'08:00' if current_hour < 8 else '13:00' if current_hour < 13 else '明天 08:00'}"
            )

            # 等待 86 秒
            for _ in range(86):
                if not running:
                    break
                time.sleep(1)

        except Exception as e:
            logger.error(f"❌ 运行出错: {e}")
            time.sleep(60)

    logger.info("👋 天气管家监控已停止")


if __name__ == "__main__":
    main()
