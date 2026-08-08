# 信息差雷达

信息差雷达是一个跨平台桌面软件 MVP，用来聚合 GitHub Trending、Hacker News、RSS 新闻源和用户自定义网站内容，并为单条热点生成分析报告。

## 当前版本包含

- Vue3 前端界面
- Electron 桌面壳
- FastAPI 本地后端
- SQLite 本地存储
- GitHub Trending / Hacker News / RSS 采集模块
- 自定义网站链接提取
- 本地规则版 AI 分析报告生成器

## 本地运行

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --port 8765
```

前端：

```bash
npm install
npm run dev
```

桌面开发模式：

```bash
npm run electron:dev
```

## 打包方向

正式输出 Windows `.exe` 和 macOS `.dmg` 时，需要先用 PyInstaller 将 `backend/main.py` 打包为后端二进制，再运行 `electron-builder`。

```bash
cd backend
pip install pyinstaller
python build_backend.py
cd ..
npm run build:web
npm run build:desktop
```

## 下一步

- 接入真实大模型 API
- 增加 Product Hunt、Reddit、arXiv、AI 工具榜单等高价值来源
- 加入关键词监控与本地提醒
- 为重点站点添加专属解析规则
- 增加报告导出 PDF
