---
name: skill-manager
description: Manage locally installed skills for AI CLI clients (Claude Code, Gemini CLI, etc.).
  Start a web dashboard to view, search, inspect details, and uninstall skills.
  Use when user types "/show-skills" or asks to manage/view/list their installed skills.
  Works across different AI CLI clients by auto-detecting the skills directory.
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
# Display skills directly in terminal without starting web server
python3 "$HOME/.claude/skills/skill-manager/scripts/server.py" "$SKILLS_DIR" "$CLI_CLIENT" --cli

# Or use shorthand
python3 "$HOME/.claude/skills/skill-manager/scripts/server.py" "$SKILLS_DIR" "$CLI_CLIENT" -l
```

CLI mode outputs a formatted table with:

- Skill name, version, source type, size, and description
- Git repository details (URL, author, install date) for git-based skills
- No browser required - perfect for SSH sessions or quick lookups

### Step 3: User Interaction

#### Web Dashboard Features

The web dashboard provides:

| Feature          | Description                                                     |
| ---------------- | --------------------------------------------------------------- |
| **Search**       | Filter skills by name or description                            |
| **View Details** | Click any skill to see full SKILL.md content and file structure |
| **Source Info**  | See where each skill was installed from (GitHub, GitLab, etc.)  |
| **Share**        | Generate install prompts for sharing with AI CLI users          |
| **Uninstall**    | Delete skills with confirmation dialog                          |
| **Refresh**      | Rescan the skills directory for changes                         |
| **Statistics**   | See total skill count and storage usage                         |

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

| CLI Client  | Skills Directory    |
| ----------- | ------------------- |
| Claude Code | `~/.claude/skills/` |
| Gemini CLI  | `~/.gemini/skills/` |
| Custom      | Configurable        |

The skill auto-detects the CLI based on which directory exists.

## Technical Details

### Server Implementation

- **Language**: Python 3
- **HTTP Server**: Built-in `http.server`
- **Port Range**: 8765-8774 (auto-discovery)
- **Frontend**: Vanilla HTML/CSS/JS (no external dependencies)

### API Endpoints

| Endpoint          | Method | Description                   |
| ----------------- | ------ | ----------------------------- |
| `/`               | GET    | Serve dashboard HTML          |
| `/api/skills`     | GET    | List all skills with metadata |
| `/api/skills/:id` | GET    | Get detailed skill info       |
| `/api/skills/:id` | DELETE | Uninstall a skill             |

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
