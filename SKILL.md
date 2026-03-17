---
name: skill-manager
description: Manage locally installed skills for AI CLI clients.
  Start a web dashboard to view, search, inspect details, sync between clients, and uninstall skills.
  Use when user types "/show-skills" or asks to manage/view/list their installed skills.
  Works across different AI CLI clients (Claude Code, Qoder, Gemini CLI, Aone Copilot) by auto-detecting installed tools.
  Supports syncing skills between different AI CLI clients.
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
---

# Skill Manager

A web-based dashboard for managing locally installed AI CLI skills.

## When to Use

Trigger this skill when:

- User types `/show-skills` or `/skill-manager`
- User asks to "manage skills", "view skills", "list skills", "show my skills"
- User wants to "uninstall", "delete", or "remove" a skill
- User wants to see what skills are installed

## Usage

### Step 1: Detect CLI Client and Skills Directory

```bash
# Auto-detect which CLI is being used
SKILLS_DIR=""
CLI_CLIENT=""

if [ -d "$HOME/.claude/skills" ]; then
    SKILLS_DIR="$HOME/.claude/skills"
    CLI_CLIENT="Claude Code"
elif [ -d "$HOME/.gemini/skills" ]; then
    SKILLS_DIR="$HOME/.gemini/skills"
    CLI_CLIENT="Gemini CLI"
elif [ -d "$HOME/.aone_copilot/skills" ]; then
    SKILLS_DIR="$HOME/.aone_copilot/skills"
    CLI_CLIENT="Aone Copilot"
elif [ -d "$HOME/.config/opencode/skills" ]; then
    SKILLS_DIR="$HOME/.config/opencode/skills"
    CLI_CLIENT="OpenCode"
fi

# Fallback: check environment variable
if [ -z "$SKILLS_DIR" ] && [ -n "$AI_SKILLS_DIR" ]; then
    SKILLS_DIR="$AI_SKILLS_DIR"
    CLI_CLIENT="Custom CLI"
fi

# If still not found, ask user
if [ -z "$SKILLS_DIR" ]; then
    echo "Could not auto-detect skills directory."
    # Ask user for the path
fi
```

### Step 2: Choose Display Mode

#### Option A: Web Dashboard (Default)

```bash
# Run the skill manager server
python3 "$HOME/.claude/skills/skill-manager/scripts/server.py" "$SKILLS_DIR" "$CLI_CLIENT"
```

The server will:

1. Find an available port (starting from 8765)
2. Start the web dashboard
3. Automatically open your default browser
4. Display all installed skills with metadata

#### Option B: CLI Mode (Terminal)

```bash
# Interactive CLI mode with menu
python3 "$HOME/.claude/skills/skill-manager/scripts/server.py" "$SKILLS_DIR" "$CLI_CLIENT" --cli

# Or use shorthand
python3 "$HOME/.claude/skills/skill-manager/scripts/server.py" "$SKILLS_DIR" "$CLI_CLIENT" -l

# Simple list mode (no interaction)
python3 "$HOME/.claude/skills/skill-manager/scripts/server.py" "$SKILLS_DIR" "$CLI_CLIENT" -l -s
```

**Interactive CLI Mode** (默认):
- 展示带编号的技能列表
- 支持交互操作：
  - 输入数字查看 skill 详情（描述、版本、来源、文件列表等）
  - 输入 `s数字` 生成分享文本（如 `s1` 分享第1个 skill）
  - 输入 `y数字` 同步 skill 到其他 AI Client（如 `y1` 同步第1个 skill）
  - 输入 `d数字` 卸载 skill（如 `d1` 卸载第1个 skill）
  - 输入 `a` 查看所有已安装的 AI Clients
  - 输入 `q` 退出

**Simple Mode** (`-s` 或 `--simple`):
- 仅输出格式化的技能表格
- 无交互，适合脚本或快速查看

CLI 模式无需浏览器，适合 SSH 会话或快速操作。

### Step 3: User Interaction

#### AI Client Detection

The skill manager automatically detects all installed AI CLI clients on your system:

| AI Client     | Config Directory     | Skills Directory        |
| ------------- | -------------------- | ----------------------- |
| **Claude Code** | `~/.claude/`        | `~/.claude/skills/`     |
| **Qoder**       | `~/.qoder/`         | `~/.qoder/skills/`      |
| **Gemini CLI**  | `~/.gemini/`        | `~/.gemini/skills/`     |
| **Aone Copilot**| `~/.aone_copilot/`  | `~/.aone_copilot/skills/`|

**API Endpoints:**
- `GET /api/clients` - List all detected AI clients
- `GET /api/sync/targets` - Get available sync targets (excludes current client)

#### Skill Sync Feature

Sync skills between different AI CLI clients:

**Web Dashboard:**
1. Click "同步" (Sync) button on any skill card
2. Select target AI client from the list
3. Click "开始同步" to sync the skill

**CLI Mode:**
```
# View all detected AI clients
> a

# Sync skill #1 to another client
> y1

# Then select target from the list
```

**Sync Behavior:**
- Copies entire skill directory including scripts
- Preserves git history if available
- Fails gracefully if skill already exists in target
- Creates target skills directory if needed

#### Web Dashboard Features

The web dashboard provides:

| Feature            | Description                                                     |
| ------------------ | --------------------------------------------------------------- |
| **Search**         | Filter skills by name or description                            |
| **View Details**   | Click any skill card to see full SKILL.md content and file structure |
| **Source Info**    | See where each skill was installed from (GitHub, GitLab, etc.)  |
| **Update**         | Pull latest code from GitHub/GitLab for git-based skills        |
| **Share**          | Generate install prompts for sharing with AI CLI users          |
| **Sync**           | Sync skills between different AI CLI clients                    |
| **Uninstall**      | Delete skills with confirmation dialog                          |
| **Refresh**        | Rescan the skills directory for changes                         |
| **Statistics**     | See total skill count and storage usage                         |
| **AI Clients**     | Detect and manage multiple installed AI CLI tools               |

## Dashboard Features

### Skill Cards

Each skill is displayed as a card showing:

- Skill name and version
- Description (truncated)
- **Source badge** (GitHub, GitLab, Bitbucket, or local)
- **Author name** (from git history)
- Directory size
- Whether it has scripts

### Detail View

Click "View" to see:

- Full description
- Version number
- **Source information** (type, author, install date, repository URL)
- File location
- Complete file list with sizes
- Full SKILL.md content (syntax highlighted)
- **Share button** to share the skill with others

### Source Detection

The skill manager automatically detects installation sources:

| Source Type   | Detection Method                       |
| ------------- | -------------------------------------- |
| **GitHub**    | github.com in remote URL               |
| **GitLab**    | gitlab.com or private GitLab instances |
| **Bitbucket** | bitbucket.org in remote URL            |
| **Git**       | Other git repositories                 |
| **Local**     | No git repository found                |

Source information includes:

- Repository URL (converted to HTTPS for sharing)
- Author (from git commit history)
- Install date (from oldest commit)

### Share Flow

1. Click "Share" on a skill card or in the detail view
2. The system generates an installation prompt based on skill type:
   - **Local skills**: "我想安装 '{skill-name}' 这个 skill，请帮我使用 find-skills 查找并安装。"
   - **Git repositories**: Provides clone command and find-skills alternative
3. Copy the generated text and send to other AI CLI users
4. Recipients paste the text into their AI client to auto-install

### Uninstall Flow

1. Click "Uninstall" on a skill card or in the detail view
2. Confirm the deletion in the dialog
3. Skill is permanently removed
4. List automatically refreshes

## Port Configuration

Default port: **8765**

If port 8765 is occupied, the server will automatically try 8766, 8767, etc.

To specify a custom port, modify the server script or set environment variable:

```bash
export SKILL_MANAGER_PORT=8080
```

## Cross-CLI Compatibility

This skill manager works with any AI CLI that stores skills in a directory structure:

| CLI Client     | Config Directory      | Skills Directory           |
| -------------- | --------------------- | -------------------------- |
| Claude Code    | `~/.claude/`          | `~/.claude/skills/`        |
| Qoder          | `~/.qoder/`           | `~/.qoder/skills/`         |
| Gemini CLI     | `~/.gemini/`          | `~/.gemini/skills/`        |
| Aone Copilot   | `~/.aone_copilot/`    | `~/.aone_copilot/skills/`  |
| Custom         | Configurable          | Configurable               |

The skill manager auto-detects all installed AI CLI clients and displays the current one in the dashboard.

### Skill Sync Between Clients

You can sync skills between different AI CLI clients:

1. **From Web Dashboard:** Click the "同步" button on any skill card
2. **From CLI Mode:** Use command `y{number}` (e.g., `y1` to sync skill #1)

Requirements for sync:
- Both source and target AI CLI must be installed
- Target skills directory will be created if it doesn't exist
- Skips if skill already exists in target to prevent overwrites

### Skill Update (Git Pull)

For skills installed from GitHub or GitLab, you can update them to the latest version:

1. **From Web Dashboard:** Click the "更新" button on GitHub/GitLab sourced skills
2. **Requirements:**
   - Skill must be installed from GitHub or GitLab
   - No uncommitted local changes
   - Must be a valid git repository with remote access

**Update Behavior:**
- Fetches latest changes from remote
- Performs hard reset to match remote branch
- Returns success message with old/new commit hashes
- Shows "already up to date" if no changes needed

## Technical Details

### Server Implementation

- **Language**: Python 3
- **HTTP Server**: Built-in `http.server`
- **Port Range**: 8765-8774 (auto-discovery)
- **Frontend**: Vanilla HTML/CSS/JS (no external dependencies)

### API Endpoints

| Endpoint                    | Method | Description                   |
| --------------------------- | ------ | ----------------------------- |
| `/`                         | GET    | Serve dashboard HTML          |
| `/api/skills`               | GET    | List all skills with metadata |
| `/api/skills/:id`           | GET    | Get detailed skill info       |
| `/api/skills/:id`           | DELETE | Uninstall a skill             |
| `/api/skills/:id/sync`      | POST   | Sync skill to another client  |
| `/api/skills/:id/update`    | POST   | Update skill from git remote  |
| `/api/clients`              | GET    | List all detected AI clients  |
| `/api/sync/targets`         | GET    | Get available sync targets    |

### Skill Metadata Parsing

The server parses each skill's `SKILL.md` and git history to extract:

- `name` - from YAML frontmatter
- `description` - from frontmatter or first paragraph
- `version` - from frontmatter (optional)
- `size` - total directory size
- `has_scripts` - whether `scripts/` directory exists
- `source` - installation source information:
  - `type` - github, gitlab, bitbucket, git, or local
  - `url` - HTTPS URL for sharing
  - `remote` - original remote URL
  - `author` - from git commit history
  - `install_date` - from oldest commit

## Troubleshooting

### Server won't start

- Check if Python 3 is installed: `python3 --version`
- Check if the skills directory exists and is readable
- Try a different port if 8765-8774 are all occupied

### Skills not showing

- Verify the skills directory path is correct
- Ensure SKILL.md files exist in skill subdirectories
- Check file permissions

### Browser doesn't open

- The server prints the URL - manually open it
- Default URL: `http://127.0.0.1:8765`

## Security Notes

- Server only binds to `127.0.0.1` (localhost)
- No authentication required (local access only)
- Delete operations require confirmation
- File paths are validated before operations
