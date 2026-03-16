#!/bin/bash
#
# Skill Manager Launcher
# Automatically detects the AI CLI client and launches the skill manager dashboard
#

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Detecting AI CLI client...${NC}"

# Auto-detect which CLI is being used
SKILLS_DIR=""
CLI_CLIENT=""

# Check for Claude Code
if [ -d "$HOME/.claude/skills" ]; then
    SKILLS_DIR="$HOME/.claude/skills"
    CLI_CLIENT="Claude Code"
    echo -e "${GREEN}✓ Found Claude Code${NC}"
fi

# Check for Gemini CLI (if not already found)
if [ -z "$SKILLS_DIR" ] && [ -d "$HOME/.gemini/skills" ]; then
    SKILLS_DIR="$HOME/.gemini/skills"
    CLI_CLIENT="Gemini CLI"
    echo -e "${GREEN}✓ Found Gemini CLI${NC}"
fi

# Check for generic AI CLI
if [ -z "$SKILLS_DIR" ] && [ -d "$HOME/.ai/skills" ]; then
    SKILLS_DIR="$HOME/.ai/skills"
    CLI_CLIENT="AI CLI"
    echo -e "${GREEN}✓ Found AI CLI${NC}"
fi

# Check environment variable
if [ -z "$SKILLS_DIR" ] && [ -n "$AI_SKILLS_DIR" ]; then
    SKILLS_DIR="$AI_SKILLS_DIR"
    CLI_CLIENT="Custom CLI"
    echo -e "${GREEN}✓ Found CLI via AI_SKILLS_DIR${NC}"
fi

# If still not found, show error
if [ -z "$SKILLS_DIR" ]; then
    echo -e "${YELLOW}⚠ Could not auto-detect skills directory.${NC}"
    echo ""
    echo "Please set the AI_SKILLS_DIR environment variable:"
    echo "  export AI_SKILLS_DIR=/path/to/your/skills"
    echo ""
    echo "Common locations:"
    echo "  - Claude Code: ~/.claude/skills"
    echo "  - Gemini CLI:  ~/.gemini/skills"
    exit 1
fi

# Verify skills directory exists
if [ ! -d "$SKILLS_DIR" ]; then
    echo -e "${YELLOW}⚠ Skills directory not found: $SKILLS_DIR${NC}"
    exit 1
fi

# Count installed skills
SKILL_COUNT=$(find "$SKILLS_DIR" -maxdepth 1 -type d | wc -l)
SKILL_COUNT=$((SKILL_COUNT - 1)) # Subtract 1 for the parent directory

echo ""
echo -e "${BLUE}📊 Summary:${NC}"
echo "  CLI Client: $CLI_CLIENT"
echo "  Skills Directory: $SKILLS_DIR"
echo "  Installed Skills: $SKILL_COUNT"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Launch the server
echo -e "${BLUE}🚀 Starting Skill Manager...${NC}"
echo ""

python3 "$SCRIPT_DIR/server.py" "$SKILLS_DIR" "$CLI_CLIENT"
