# 信息差雷达

信息差雷达是一个跨平台桌面软件，用来聚合 GitHub Trending、Hacker News、微博热搜、46+ 中英文 RSS 新闻源和用户自定义站点内容，并为单条热点生成大模型分析报告。核心价值是把「境外已热、境内尚未覆盖」的信息差信号自动化地找出来。

## 当前版本包含（v0.4）

- Vue3 前端界面 + Electron 桌面壳 + FastAPI 本地后端 + SQLite 本地存储
- **并发采集**：50+ 数据源并发抓取，全量刷新约 15 秒完成；每源成功/失败状态可见
- **数据源**：GitHub Trending（10 语言×15、按日增 star 计热度）、Hacker News（Top50）、45 个中英文 RSS + **6 大境内热榜**（微博/知乎/百度/抖音/B站/硬核媒体），单次全量采集 1000+ 条
- **采集健壮性**：失败自动重试、RSSHub 镜像兜底（镜像地址可配置，被墙源自动切换）、浏览器 UA、`content:encoded` 完整摘要
- **采集后全文预抓**：每源热度 Top3 自动后台抓正文入库，AI 分析直接吃全文
- **热度归一化**：所有来源的原始热度（star / points / 榜单位次）按源内百分位映射到 0~100，跨源可比
- **AI 分析报告**：接入通义千问 / DeepSeek / OpenAI / 自定义 OpenAI 兼容接口；支持流式输出（边生成边看）、已抓取全文参与分析、429/5xx 自动重试、报告最大长度可配置
- **信息差洞察**：本地聚合版离线可用，配置 Key 后由大模型撰写；跨源事件聚类 + 境内外分布对比
- **信息分拣**：收藏 / 已读 / 隐藏，一键批量分析前 10 条
- **关键词监控**：设置监控词（每行一个），自动巡航采集中命中时弹系统通知
- **订阅源管理**：自定义 RSS 增删、OPML 导入 / 导出，内置源可勾选开关
- **自定义站点**：链接提取过滤导航噪音，站点记忆可重复抓取
- **全文搜索**：SQLite FTS5，中文按二元分词，支持中英文混合检索
- **数据治理**：按保留天数自动清理旧数据（收藏永不清理）；列表接口瘦字段传输
- **报告导出**：Markdown 下载 / 打印为 PDF
- AI 设置面板（连接测试、API Key 仅保存在本机 `~/.info-gap-radar/config.json`）

## 快速开始（一键开发模式）

```bash
# 1. 后端依赖（Python 3.12）
cd backend
py -3.12 -m venv .venv
.venv/Scripts/pip install -r requirements.txt    # macOS/Linux: .venv/bin/pip

# 2. 前端依赖
cd ..
npm install

# 3. 一键启动：同时拉起后端(8765) + Vite(5173) + Electron 窗口
npm run electron:dev
```

也可以分开跑：后端 `cd backend && .venv/Scripts/python main.py --port 8765`，前端 `npm run dev`（浏览器访问 http://127.0.0.1:5173）。

## AI 模型配置

1. 启动软件后，点击左下角「AI 设置」
2. 选择服务商（通义千问 / DeepSeek / OpenAI / 自定义），会自动填入对应的接口地址和默认模型
3. 填入 API Key，可点击「测试 AI 连接」验证，保存即可
4. 之后点击任意热点的「AI 分析」按钮，报告由真实大模型流式生成；未配置 Key 时回退到本地模板报告

## 测试

```bash
npm run backend:test        # 后端单元测试（pytest）
npm run build:web           # 前端构建校验
```

## 打包

正式输出 Windows `.exe` 和 macOS `.dmg` 时，需要先用 PyInstaller 将 `backend/main.py` 打包为后端二进制，再运行 `electron-builder`：

```bash
cd backend
pip install pyinstaller
python build_backend.py
cd ..
npm run build:web
npm run build:desktop
```

## 下一步

- 聚类升级为语义向量（跨语言同事件合并）
- Product Hunt、Reddit 榜单的专属热度规则
- 移动端 / Web 版只读视图
- 团队版：共享监控词、行业报告
