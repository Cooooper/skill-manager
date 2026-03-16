---
name: skill-manager
description: |
  Manage locally installed skills for AI CLI clients (Claude Code, Gemini CLI, etc.).
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
elif [ -d "$HOME/.ai/skills" ]; then
    SKILLS_DIR="$HOME/.ai/skills"
    CLI_CLIENT="AI CLI"
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

### Step 2: Start the Web Server

```bash
# Run the skill manager server
python3 "$HOME/.claude/skills/skill-manager/scripts/server.py" "$SKILLS_DIR" "$CLI_CLIENT"
```

The server will:
1. Find an available port (starting from 8765)
2. Start the web dashboard
3. Automatically open your default browser
4. Display all installed skills with metadata

### Step 3: User Interaction

The web dashboard provides:

| Feature | Description |
|---------|-------------|
| **Search** | Filter skills by name or description |
| **View Details** | Click any skill to see full SKILL.md content and file structure |
| **Uninstall** | Delete skills with confirmation dialog |
| **Refresh** | Rescan the skills directory for changes |
| **Statistics** | See total skill count and storage usage |

## Dashboard Features

### Skill Cards
Each skill is displayed as a card showing:
- Skill name and version
- Description (truncated)
- Directory size
- Whether it has scripts

### Detail View
Click "View" to see:
- Full description
- Version number
- File location
- Complete file list with sizes
- Full SKILL.md content (syntax highlighted)

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

| CLI Client | Skills Directory |
|------------|------------------|
| Claude Code | `~/.claude/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| Custom | Configurable |

The skill auto-detects the CLI based on which directory exists.

## Technical Details

### Server Implementation
- **Language**: Python 3
- **HTTP Server**: Built-in `http.server`
- **Port Range**: 8765-8774 (auto-discovery)
- **Frontend**: Vanilla HTML/CSS/JS (no external dependencies)

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve dashboard HTML |
| `/api/skills` | GET | List all skills with metadata |
| `/api/skills/:id` | GET | Get detailed skill info |
| `/api/skills/:id` | DELETE | Uninstall a skill |

### Skill Metadata Parsing

The server parses each skill's `SKILL.md` to extract:
- `name` - from YAML frontmatter
- `description` - from frontmatter or first paragraph
- `version` - from frontmatter (optional)
- `size` - total directory size
- `has_scripts` - whether `scripts/` directory exists

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
