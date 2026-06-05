# 🌤️ 天气管家 - GitHub Actions 部署版

基于 OpenWeatherMap One Call API 3.0 + OpenRouter AI + Bark 推送的智能天气管家系统，支持 GitHub Actions 自动化运行。

## ✨ 功能

- 🤖 **AI 智能分析**：OpenRouter 大模型生成个性化管家建议
- 📲 **即时推送**：Bark 推送至 iPhone（恶劣天气 + 定时汇报）
- 🌍 **7 Key 负载均衡**：多个 API Key 轮询调用
- ⏰ **每小时自动运行**：GitHub Actions cron 定时触发
- 🔒 **安全保密**：所有密钥存储在 GitHub Secrets，不上传代码

## 📋 准备工作

### 1. 订阅 OpenWeatherMap One Call API 3.0

1. 注册 OpenWeatherMap：https://home.openweathermap.org/users/sign_up
2. 订阅 "One Call by Call"：https://home.openweathermap.org/subscriptions（免费 1000次/天）
3. 获取 API Keys：https://home.openweathermap.org/api_keys（可创建多个 Key 轮询）

### 2. 获取 OpenRouter API Key

1. 注册 OpenRouter：https://openrouter.ai/
2. 获取 API Key
3. 推荐模型：`nvidia/nemotron-3-ultra-550b-a55b:free`（免费）

### 3. 安装 Bark App（iPhone）

从 App Store 安装 Bark，获取推送地址（如 `https://api.day.app/你的key`）

## 🚀 部署步骤

### 第一步：Fork 本仓库

点击右上角 **Fork**，创建您的副本。

### 第二步：配置 GitHub Secrets

进入您的仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，添加以下密钥：

| Secret 名称 | 说明 | 示例 |
|:--|:--|:--|
| `API_KEYS` | OpenWeatherMap API Keys（多个用逗号分隔） | `key1,key2,key3` |
| `BARK_KEY` | Bark 推送 key | `aQKYodycX7m864Aee52aRQ` |
| `OPENROUTER_API_BASE` | OpenRouter API 地址 | `https://openrouter.ai/api/v1` |
| `OPENROUTER_API_KEY` | OpenRouter API Key | `sk-or-v1-xxx` |
| `OPENROUTER_MODEL` | 模型名称 | `nvidia/nemotron-3-ultra-550b-a55b:free` |

### 第三步：配置仓库变量

进入 **Settings** → **Secrets and variables** → **Actions** → **New repository variable**：

| Variable 名称 | 说明 | 示例 |
|:--|:--|:--|
| `LAT` | 纬度 | `29.4768` |
| `LON` | 经度 | `121.8634` |
| `LOCATION_NAME` | 位置名称 | `宁波象山` |

### 第四步：启用 Actions

进入 **Actions** 标签页，点击 **I understand my workflows, go ahead and enable them**。

### 第五步：测试运行

1. 进入 **Actions** → **Weather Butler - AI Weather Assistant**
2. 点击左侧 **Weather Butler - AI Weather Assistant**
3. 点击 **Run workflow** → **Run workflow**

## ⏰ 定时说明

GitHub Actions 使用 **UTC 时区**。每小时整点自动运行，对应北京时间：

| Actions (UTC) | 北京时间 |
|:--|:--|
| 0 * * * * | 每天 8:00 ~ 7:00 每小时一次 |
| 0 0-7,13,14 * * * | 仅 8:00-15:00 每小时 |

当前 workflow 设置为**每小时运行**，8:00 和 13:00 自动生成管家报告。

## 🔧 自定义修改

### 改为仅 8:00 和 13:00 运行

编辑 `.github/workflows/weather_butler.yml`，将 cron 改为：

```yaml
schedule:
  - cron: '0 0-7,13,14 * * *'  # UTC 0点=北京8点，UTC 5点=北京13点
```

### 修改位置

在仓库 **Settings → Secrets and variables → Actions** 中修改 `LAT`、`LON`、`LOCATION_NAME` 变量。

## 📁 文件结构

```
weather_butler/
├── .github/
│   └── workflows/
│       ├── weather_butler.yml     # GitHub Actions workflow
│       ├── weather_runner.py      # 独立运行脚本（环境变量版）
│       └── requirements.txt        # Python 依赖
├── .gitignore                     # 不上传 .env, .log 等
├── weather_butler.py              # 本地运行版（.env 文件版）
├── weather_monitor.py             # 本地持续监控版
├── .env.example                   # 配置模板
└── README.md
```

## ⚠️ 安全说明

- ❌ 永远不要将 API Key 写入代码
- ❌ 永远不要将 `.env` 文件提交到仓库
- ✅ 所有密钥必须通过 GitHub Secrets 管理
- ✅ `.gitignore` 已配置排除敏感文件
