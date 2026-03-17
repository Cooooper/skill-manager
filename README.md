# Skill Manager

<p align="center">
  <b>🤖 AI CLI Skills 管理仪表板</b><br>
  <b>AI CLI Skills Management Dashboard</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg" alt="Platform">
</p>

<p align="center">
  <a href="#中文文档">中文</a> | <a href="#english-documentation">English</a>
</p>

---

<h2 id="中文文档">📖 中文文档</h2>

### 简介

**Skill Manager** 是一个用于管理本地安装的 AI CLI 客户端技能（skills）的 Web 仪表板工具。它支持多个 AI 客户端，包括 Claude Code、Qoder、Gemini CLI 和 Aone Copilot。

通过直观的 Web 界面或终端交互模式，您可以轻松查看、搜索、同步、更新和卸载技能。

### ✨ 功能特点

| 功能 | 描述 |
|------|------|
| 🔍 **搜索与筛选** | 按名称或描述快速查找技能 |
| 📊 **排序功能** | 支持按更新时间、安装时间、大小或名称排序 |
| 📁 **文件浏览器** | 查看技能的完整文件结构和内容 |
| 🔄 **跨 CLI 同步** | 在不同 AI 客户端之间同步技能 |
| ⬆️ **技能更新** | 从 GitHub/GitLab 拉取最新代码 |
| 📤 **分享功能** | 生成安装提示文本，方便分享给其他用户 |
| 🗑️ **卸载管理** | 安全删除不需要的技能 |
| 📈 **统计信息** | 查看技能总数和存储使用情况 |

### 🚀 安装方法

#### 方式一：通过 Git 克隆安装

```bash
# 进入您的 skills 目录
cd ~/.claude/skills

# 克隆 skill-manager
git clone https://github.com/your-repo/skill-manager.git

# 或者使用 SSH
git clone git@github.com:your-repo/skill-manager.git
```

#### 方式二：手动安装

1. 下载项目压缩包
2. 解压到 `~/.claude/skills/skill-manager/` 目录
3. 确保 `scripts/server.py` 文件可执行

### 🎯 使用方法

#### Web 仪表板模式（默认）

```bash
# 运行 skill manager
python3 ~/.claude/skills/skill-manager/scripts/server.py "$HOME/.claude/skills" "Claude Code"
```

服务器将：
1. 自动查找可用端口（从 8765 开始）
2. 启动 Web 仪表板
3. 自动打开默认浏览器
4. 显示所有已安装的技能及其元数据

#### CLI 终端模式

```bash
# 交互式 CLI 模式
python3 ~/.claude/skills/skill-manager/scripts/server.py "$SKILLS_DIR" "$CLI_CLIENT" --cli

# 或简写形式
python3 ~/.claude/skills/skill-manager/scripts/server.py "$SKILLS_DIR" "$CLI_CLIENT" -l

# 简单列表模式（无交互，适合脚本）
python3 ~/.claude/skills/skill-manager/scripts/server.py "$SKILLS_DIR" "$CLI_CLIENT" -l -s
```

**交互式 CLI 模式命令：**

| 命令 | 功能 |
|------|------|
| `数字` | 查看指定技能的详情 |
| `s数字` | 生成分享文本（如 `s1` 分享第1个技能）|
| `y数字` | 同步技能到其他 AI 客户端 |
| `d数字` | 卸载指定技能 |
| `a` | 查看所有已检测到的 AI 客户端 |
| `q` | 退出程序 |

### 🌐 Web 仪表板功能

#### 技能卡片

每个技能以卡片形式展示：
- 技能名称和版本
- 描述（截断显示）
- **来源标识**（GitHub、GitLab、Bitbucket 或本地）
- **作者信息**（来自 git 历史）
- 目录大小
- 是否包含脚本目录

#### 详情视图

点击任意技能卡片查看详细信息，采用双栏布局：

**左侧边栏：**
- 📂 **文件浏览器**：完整的文件列表和大小
  - 点击文件查看内容
  - 代码文件语法高亮
  - 文件大小限制：1MB
- **技能元数据**：版本、来源、大小、作者

**右侧主区域：**
- 📝 完整描述
- 🔗 源代码链接（如来自 GitHub/GitLab）
- 📍 本地文件路径
- 📄 文件内容查看器

#### 排序选项

点击"排序"下拉菜单：

| 排序方式 | 描述 |
|----------|------|
| **更新时间** | 最后修改时间（默认）|
| **安装时间** | 安装/创建时间 |
| **体积大小** | 目录大小（从大到小）|
| **名称** | 按字母顺序 |

#### AI 客户端切换

点击顶部英雄卡片中的客户端名称（如 "🤖 Claude Code ▼"）：
- 查看所有检测到的 AI CLI 客户端
- 切换不同客户端的技能目录
- 查看每个客户端的技能数量

### 🔄 跨 CLI 同步

在不同 AI CLI 客户端之间同步技能：

**Web 仪表板：**
1. 点击技能卡片上的"同步"按钮
2. 从列表中选择目标 AI 客户端
3. 点击"开始同步"

**CLI 模式：**
```
# 查看所有检测到的 AI 客户端
> a

# 同步第1个技能
> y1

# 然后选择目标客户端
```

**同步行为：**
- 复制整个技能目录，包括脚本
- 如可用，保留 git 历史
- 如目标已存在该技能，则跳过
- 如需要，创建目标 skills 目录

### ⬆️ 技能更新

对于从 GitHub 或 GitLab 安装的技能，可以更新到最新版本：

**Web 仪表板：**
- 点击 GitHub/GitLab 来源技能卡片上的"更新"按钮

**要求：**
- 技能必须来自 GitHub 或 GitLab
- 没有未提交的本地更改
- 必须是具有远程访问权限的有效 git 仓库

**更新行为：**
- 从远程获取最新更改
- 执行硬重置以匹配远程分支
- 返回包含旧/新提交哈希的成功消息
- 如已是最新则显示"已是最新"

### 📤 分享功能

1. 点击技能卡片或详情视图中的"分享"
2. 系统根据技能类型生成安装提示：
   - **本地技能**："我想安装 '{skill-name}' 这个 skill，请帮我使用 find-skills 查找并安装。"
   - **Git 仓库**：提供 clone 命令和 find-skills 替代方案
3. 复制生成的文本并发送给其他 AI CLI 用户
4. 接收者将文本粘贴到他们的 AI 客户端即可自动安装

### 🛠️ 技术细节

#### 服务器实现

- **语言**：Python 3
- **HTTP 服务器**：内置 `http.server`
- **端口范围**：8765-8774（自动发现）
- **前端**：原生 HTML/CSS/JS（无外部依赖）

#### API 接口

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 仪表板 HTML 页面 |
| `/api/skills?sort={field}` | GET | 列出所有技能及元数据 |
| `/api/skills/:id` | GET | 获取技能详细信息 |
| `/api/skills/:id/file?path={path}` | GET | 获取特定文件内容 |
| `/api/skills/:id` | DELETE | 卸载技能 |
| `/api/skills/:id/sync` | POST | 同步技能到其他客户端 |
| `/api/skills/:id/update` | POST | 从 git 远程更新技能 |
| `/api/clients` | GET | 列出所有检测到的 AI 客户端 |
| `/api/sync/targets` | GET | 获取可用同步目标 |

**排序选项：** `updated_at`（默认）、`created_at`、`size`、`name`

### 🔧 故障排除

#### 服务器无法启动

- 检查 Python 3 是否安装：`python3 --version`
- 检查 skills 目录是否存在且可读
- 如 8765-8774 端口都被占用，尝试其他端口

#### 技能未显示

- 验证 skills 目录路径是否正确
- 确保技能子目录中存在 SKILL.md 文件
- 检查文件权限

#### 浏览器未自动打开

- 服务器会打印 URL - 手动打开它
- 默认 URL：`http://127.0.0.1:8765`

### 🔒 安全说明

- 服务器仅绑定到 `127.0.0.1`（本地主机）
- 无需身份验证（仅限本地访问）
- 删除操作需要确认
- 文件路径在操作前经过验证

---

<h2 id="english-documentation">📖 English Documentation</h2>

### Introduction

**Skill Manager** is a web-based dashboard tool for managing locally installed AI CLI client skills. It supports multiple AI clients, including Claude Code, Qoder, Gemini CLI, and Aone Copilot.

Through an intuitive web interface or terminal interactive mode, you can easily view, search, sync, update, and uninstall skills.

### ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Search & Filter** | Quickly find skills by name or description |
| 📊 **Sorting** | Sort by update time, install time, size, or name |
| 📁 **File Browser** | View complete file structure and content of skills |
| 🔄 **Cross-CLI Sync** | Sync skills between different AI clients |
| ⬆️ **Skill Update** | Pull latest code from GitHub/GitLab |
| 📤 **Share** | Generate installation prompts for easy sharing |
| 🗑️ **Uninstall** | Safely remove unwanted skills |
| 📈 **Statistics** | View total skill count and storage usage |

### 🚀 Installation

#### Method 1: Install via Git Clone

```bash
# Navigate to your skills directory
cd ~/.claude/skills

# Clone skill-manager
git clone https://github.com/your-repo/skill-manager.git

# Or use SSH
git clone git@github.com:your-repo/skill-manager.git
```

#### Method 2: Manual Installation

1. Download the project archive
2. Extract to `~/.claude/skills/skill-manager/` directory
3. Ensure `scripts/server.py` file is executable

### 🎯 Usage

#### Web Dashboard Mode (Default)

```bash
# Run skill manager
python3 ~/.claude/skills/skill-manager/scripts/server.py "$HOME/.claude/skills" "Claude Code"
```

The server will:
1. Automatically find an available port (starting from 8765)
2. Start the web dashboard
3. Automatically open your default browser
4. Display all installed skills with metadata

#### CLI Terminal Mode

```bash
# Interactive CLI mode
python3 ~/.claude/skills/skill-manager/scripts/server.py "$SKILLS_DIR" "$CLI_CLIENT" --cli

# Or shorthand
python3 ~/.claude/skills/skill-manager/scripts/server.py "$SKILLS_DIR" "$CLI_CLIENT" -l

# Simple list mode (no interaction, good for scripts)
python3 ~/.claude/skills/skill-manager/scripts/server.py "$SKILLS_DIR" "$CLI_CLIENT" -l -s
```

**Interactive CLI Mode Commands:**

| Command | Function |
|---------|----------|
| `number` | View details of specified skill |
| `s<number>` | Generate share text (e.g., `s1` to share skill #1) |
| `y<number>` | Sync skill to other AI client |
| `d<number>` | Uninstall specified skill |
| `a` | View all detected AI clients |
| `q` | Quit program |

### 🌐 Web Dashboard Features

#### Skill Cards

Each skill is displayed as a card showing:
- Skill name and version
- Description (truncated)
- **Source badge** (GitHub, GitLab, Bitbucket, or local)
- **Author info** (from git history)
- Directory size
- Whether it has scripts directory

#### Detail View

Click any skill card to see detailed information with a two-column layout:

**Left Sidebar:**
- 📂 **File Browser**: Complete file list with sizes
  - Click files to view content
  - Syntax highlighting for code files
  - File size limit: 1MB
- **Skill Metadata**: Version, source, size, author

**Right Main Area:**
- 📝 Full description
- 🔗 Source link (if from GitHub/GitLab)
- 📍 Local file path
- 📄 File content viewer

#### Sorting Options

Click the "Sort" dropdown:

| Sort Option | Description |
|-------------|-------------|
| **Updated At** | Last modified time (default) |
| **Created At** | Installation/creation time |
| **Size** | Directory size (largest first) |
| **Name** | Alphabetical order |

#### AI Client Switching

Click the client name in the hero card (e.g., "🤖 Claude Code ▼"):
- View all detected AI CLI clients
- Switch between different clients' skill directories
- See skill count for each client

### 🔄 Cross-CLI Sync

Sync skills between different AI CLI clients:

**Web Dashboard:**
1. Click the "Sync" button on any skill card
2. Select target AI client from the list
3. Click "Start Sync"

**CLI Mode:**
```
# View all detected AI clients
> a

# Sync skill #1
> y1

# Then select target client
```

**Sync Behavior:**
- Copies entire skill directory including scripts
- Preserves git history if available
- Skips if skill already exists in target
- Creates target skills directory if needed

### ⬆️ Skill Update

For skills installed from GitHub or GitLab, you can update to the latest version:

**Web Dashboard:**
- Click the "Update" button on GitHub/GitLab sourced skills

**Requirements:**
- Skill must be installed from GitHub or GitLab
- No uncommitted local changes
- Must be a valid git repository with remote access

**Update Behavior:**
- Fetches latest changes from remote
- Performs hard reset to match remote branch
- Returns success message with old/new commit hashes
- Shows "already up to date" if no changes needed

### 📤 Share Feature

1. Click "Share" on a skill card or in detail view
2. System generates installation prompt based on skill type:
   - **Local skills**: "I want to install the '{skill-name}' skill, please help me find and install it using find-skills."
   - **Git repositories**: Provides clone command and find-skills alternative
3. Copy generated text and send to other AI CLI users
4. Recipients paste the text into their AI client to auto-install

### 🛠️ Technical Details

#### Server Implementation

- **Language**: Python 3
- **HTTP Server**: Built-in `http.server`
- **Port Range**: 8765-8774 (auto-discovery)
- **Frontend**: Vanilla HTML/CSS/JS (no external dependencies)

#### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard HTML page |
| `/api/skills?sort={field}` | GET | List all skills with metadata |
| `/api/skills/:id` | GET | Get detailed skill info |
| `/api/skills/:id/file?path={path}` | GET | Get content of specific file |
| `/api/skills/:id` | DELETE | Uninstall a skill |
| `/api/skills/:id/sync` | POST | Sync skill to another client |
| `/api/skills/:id/update` | POST | Update skill from git remote |
| `/api/clients` | GET | List all detected AI clients |
| `/api/sync/targets` | GET | Get available sync targets |

**Sort Options:** `updated_at` (default), `created_at`, `size`, `name`

### 🔧 Troubleshooting

#### Server Won't Start

- Check if Python 3 is installed: `python3 --version`
- Check if the skills directory exists and is readable
- Try a different port if 8765-8774 are all occupied

#### Skills Not Showing

- Verify the skills directory path is correct
- Ensure SKILL.md files exist in skill subdirectories
- Check file permissions

#### Browser Doesn't Open

- The server prints the URL - manually open it
- Default URL: `http://127.0.0.1:8765`

### 🔒 Security Notes

- Server only binds to `127.0.0.1` (localhost)
- No authentication required (local access only)
- Delete operations require confirmation
- File paths are validated before operations

---

## 📋 Supported AI Clients / 支持的 AI 客户端

| Client | Config Directory | Skills Directory |
|--------|-----------------|------------------|
| **Claude Code** | `~/.claude/` | `~/.claude/skills/` |
| **Qoder** | `~/.qoder/` | `~/.qoder/skills/` |
| **Gemini CLI** | `~/.gemini/` | `~/.gemini/skills/` |
| **Aone Copilot** | `~/.aone_copilot/` | `~/.aone_copilot/skills/` |

---

## 📄 License / 许可证

MIT License - see [LICENSE](LICENSE) file for details.

---

<p align="center">
  Made with ❤️ for AI CLI users
</p>
