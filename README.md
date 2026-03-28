<div align="center">

<img src="../logo.png" alt="ZexBot" width="120" height="120" />

# ZexBot

**轻量级 OneBot 11 正向 WebSocket 机器人宿主** · 内置 Web 控制台 · 插件扩展

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![OneBot 11](https://img.shields.io/badge/OneBot-11-5865F2?style=flat-square)](https://github.com/botuniverse/onebot-11)
[![FastAPI](https://img.shields.io/badge/Web-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![VitePress](https://img.shields.io/badge/docs-VitePress-646CFF?style=flat-square&logo=vitepress)](https://vitepress.dev/)

<!-- 发布到 GitHub 后，可将下方两行中的 OWNER/REPO 换成你的「用户名/仓库名」，以显示版本与 Star -->
<!-- [![Release](https://img.shields.io/github/v/release/OWNER/REPO?style=flat-square&logo=github)](https://github.com/OWNER/REPO/releases) -->
<!-- [![Stars](https://img.shields.io/github/stars/OWNER/REPO?style=flat-square&logo=github)](https://github.com/OWNER/REPO) -->

</div>

---

## 简介

ZexBot 使用 Python 编写，通过 **正向 WebSocket** 对接 [LLOneBot](https://github.com/LLOneBot/LLOneBot)、LLBot 等 **OneBot 11** 实现；内置基于 **FastAPI** 的 **Web 控制台**，支持连接状态、群管理、插件配置与内存日志。业务逻辑以 **插件目录** 扩展（`plugin.py` + 可选 `config.json` / `admin` 页）。

|  |  |
|--|--|
| **图形化协议端** | 与 LLBot 等配合时，可在桌面端完成启动与配置（以你所用发行版为准）。 |
| **可视化配置** | Web 控制台编辑主配置与各插件 `config.json`。 |
| **实时监控日志** | 控制台查看运行期日志（内存环形缓冲）。 |
| **Windows 便携 exe** | 支持 `PyInstaller` 单文件打包，无需目标机安装 Python。 |

---

## 快速开始

**环境**：Python **3.10+**（建议 3.11）；已配置 **OneBot 11 正向 WebSocket** 的协议端（示例：`ws://127.0.0.1:3001`）。

```bash
pip install -r zexbot/requirements.txt
python -m zexbot
```

浏览器打开控制台（默认）：**http://127.0.0.1:8080**（端口被占用时会递增，以终端输出为准）。

首次运行会生成 **`zexbot/data/config.json`**，请将 **`ws_url`**、**`token`** 与协议端保持一致。**勿将含真实 Token、群号的配置提交到公开仓库。**

---

## 文档

完整安装步骤（含 **完整安装包**、系统要求、手动安装）见在线文档源码：

| 内容 | 路径 |
|------|------|
| 安装与运行 | [`website/guide/install.md`](website/guide/install.md) |
| 配置说明 | [`website/guide/config.md`](website/guide/config.md) |
| 插件开发 | [`website/guide/plugin-dev.md`](website/guide/plugin-dev.md) |
| Windows 打包 | [`website/guide/windows-build.md`](website/guide/windows-build.md) |

本地构建文档站（[VitePress](https://vitepress.dev/)）：

```bash
cd website
npm install
npm run dev
```

生产构建：`npm run build`，静态资源输出至 **`website/.vitepress/dist`**。

---

## 下载与 GitHub Releases

文档站提供三种下载入口（**LLBot + ZexBot + QQ** / **LLBot + ZexBot** / **仅 ZexBot**）。发布 Release 后，在 **`website/.vitepress/constants.ts`** 中填写资源 **直链**，再部署文档站或同步 README 中的说明即可。

---

## Windows：单文件 exe 与安装包

在**仓库根目录**执行：

```bash
pip install -r packaging/requirements-build.txt
python packaging/build_onefile.py
```

| 产出 | 说明 |
|------|------|
| **`dist/ZexBot.exe`** | 单文件便携版；可复制到未安装 Python 的机器运行；首次运行在 exe **同目录**生成 `data/`、`plugins/` 等。 |
| **`dist/ZexBot-Setup.exe`** | 需安装 [Inno Setup 6](https://jrsoftware.org/isdl.php)；脚本若检测到 `ISCC.exe` 可能自动编译，否则手动执行 `ISCC.exe packaging\ZexBot.iss`。 |

**图标**：将 **`packaging/logo.png`** 替换为你的图标（建议 256×256 PNG）；缺失时构建脚本会生成占位图并生成 `logo.ico`。同步到 Web 静态资源：`python packaging/sync_web_logo.py`。

**Linux / macOS / Docker** 预编译包可自行扩展；其它系统请使用 **Python 源码**运行。

---

## 配置（`zexbot/data/config.json`）

| 字段 | 说明 |
|------|------|
| `ws_url` | OneBot 正向 WebSocket 地址 |
| `token` | 与协议端一致的访问令牌（可为空） |
| `private_message_enabled` | 是否响应私聊 |
| `enabled_group_ids` | 允许响应的群号列表 |
| `web_host` / `web_port` | 控制台监听地址与端口 |
| `plugins_dir` | 插件目录名（相对 `zexbot` 包，默认 `plugins`） |
| `disabled_plugins` | 禁用的插件目录名列表 |

---

## 插件

插件位于 **`zexbot/plugins/<插件目录名>/`**，至少包含 **`plugin.py`**。可选 **`config.json`**、**`admin/index.html`**。

本仓库附带示例：**`group_suite`**（群管等）、**`keyword_reply`**（关键词回复），可按需修改或新增目录。

---

## 开发与发布注意

- 控制台日志为**内存**缓冲；亦可 `POST /api/logs/clear` 清空。
- 本地 `*.log`、`logs/`、`__pycache__/` 等应由 **`.gitignore`** 忽略。
- 开源前请确认仓库内无 **API 密钥、真实 QQ 号、密码** 等敏感信息。

---

## 许可证与作者

请自行在仓库根目录添加 **`LICENSE`**（如 MIT、Apache-2.0 等）。框架与示例由 **Zex** 编写，欢迎按需修改与二次分发。
