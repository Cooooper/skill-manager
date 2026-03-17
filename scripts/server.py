#!/usr/bin/env python3
"""
Skill Manager Web Server
A lightweight HTTP server for managing AI CLI skills.
"""

import os
import sys
import json
import shutil
import subprocess
import re
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import webbrowser
from threading import Timer
from datetime import datetime

# Configuration
DEFAULT_PORT = 8765
MAX_PORT_ATTEMPTS = 10

# Supported AI Clients and their skills directories
AI_CLIENTS = {
    "claude": {
        "name": "Claude Code",
        "skills_dir": "~/.claude/skills",
        "config_dir": "~/.claude",
    },
    "qoder": {
        "name": "Qoder",
        "skills_dir": "~/.qoder/skills",
        "config_dir": "~/.qoder",
    },
    "gemini": {
        "name": "Gemini CLI",
        "skills_dir": "~/.gemini/skills",
        "config_dir": "~/.gemini",
    },
    "aone_copilot": {
        "name": "Aone Copilot",
        "skills_dir": "~/.aone_copilot/skills",
        "config_dir": "~/.aone_copilot",
    },
}


def detect_ai_clients():
    """Detect all installed AI clients on the system."""
    home = Path.home()
    detected = []

    for client_id, config in AI_CLIENTS.items():
        config_dir = config["config_dir"]
        skills_dir = config["skills_dir"]

        # Handle paths that may start with ~/ or just be relative
        if config_dir.startswith("~/"):
            config_path = home / config_dir[2:]
        else:
            config_path = home / config_dir

        if skills_dir.startswith("~/"):
            skills_path = home / skills_dir[2:]
        else:
            skills_path = home / skills_dir

        # Check if config directory exists (indicates installation)
        if config_path.exists():
            detected.append(
                {
                    "id": client_id,
                    "name": config["name"],
                    "skills_dir": str(skills_path),
                    "config_dir": str(config_path),
                    "has_skills": skills_path.exists() and skills_path.is_dir(),
                    "skill_count": (
                        len(
                            [
                                d
                                for d in skills_path.iterdir()
                                if d.is_dir() and (d / "SKILL.md").exists()
                            ]
                        )
                        if skills_path.exists()
                        else 0
                    ),
                }
            )

    return detected


class SkillManager:
    def __init__(self, skills_dir: str, cli_client: str):
        self.skills_dir = Path(skills_dir)
        self.cli_client = cli_client
        self.skills = []

    def scan_skills(self, sort_by="updated_at"):
        """Scan the skills directory and parse metadata."""
        self.skills = []

        if not self.skills_dir.exists():
            return self.skills

        for skill_path in self.skills_dir.iterdir():
            if not skill_path.is_dir():
                continue

            skill_md = skill_path / "SKILL.md"
            if not skill_md.exists():
                continue

            skill_info = self._parse_skill_md(skill_path, skill_md)
            if skill_info:
                self.skills.append(skill_info)

        # Sort skills based on sort_by parameter
        if sort_by == "name":
            self.skills.sort(key=lambda x: x["name"].lower())
        elif sort_by == "size":
            self.skills.sort(key=lambda x: x.get("size", 0), reverse=True)
        elif sort_by == "created_at":
            self.skills.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        elif sort_by == "updated_at":
            self.skills.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        else:
            # Default sort by updated_at
            self.skills.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        return self.skills

    def _get_skill_source(self, skill_path: Path) -> dict:
        """Detect skill installation source from git config or other indicators."""
        source_info = {
            "type": "local",
            "url": None,
            "remote": None,
            "author": None,
            "install_date": None,
        }

        # Check if it's a git repository
        git_dir = skill_path / ".git"
        if git_dir.exists():
            try:
                # Read git config to get remote URL
                git_config = git_dir / "config"
                if git_config.exists():
                    config_content = git_config.read_text(encoding="utf-8")

                    # Extract remote URL
                    remote_match = re.search(
                        r'\[remote "origin"\][^\[]*url\s*=\s*(.+)', config_content
                    )
                    if remote_match:
                        remote_url = remote_match.group(1).strip()
                        source_info["remote"] = remote_url

                        # Determine source type from URL
                        remote_url_lower = remote_url.lower()

                        if "github.com" in remote_url_lower:
                            source_info["type"] = "github"
                            # Convert SSH URL to HTTPS for sharing
                            if remote_url.startswith("git@github.com:"):
                                source_info["url"] = remote_url.replace(
                                    "git@github.com:", "https://github.com/"
                                ).replace(".git", "")
                            else:
                                source_info["url"] = remote_url.replace(".git", "")
                        elif "gitlab" in remote_url_lower:
                            # Support both gitlab.com and private GitLab instances
                            source_info["type"] = "gitlab"
                            # Convert SSH URL to HTTPS for sharing
                            if remote_url.startswith("git@"):
                                # Extract domain from git@domain:path format
                                match = re.match(r"git@([^:]+):(.+)", remote_url)
                                if match:
                                    domain, path = match.groups()
                                    source_info["url"] = (
                                        f"https://{domain}/{path}".replace(".git", "")
                                    )
                                else:
                                    source_info["url"] = remote_url.replace(".git", "")
                            else:
                                source_info["url"] = remote_url.replace(".git", "")
                        elif "bitbucket.org" in remote_url_lower:
                            source_info["type"] = "bitbucket"
                            source_info["url"] = remote_url.replace(".git", "")
                        else:
                            source_info["type"] = "git"
                            source_info["url"] = remote_url

                # Try to get author from git log
                try:
                    result = subprocess.run(
                        ["git", "-C", str(skill_path), "log", "--format=%an", "-1"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        source_info["author"] = result.stdout.strip()
                except:
                    pass

                # Try to get install/clone date from git log (oldest commit)
                try:
                    result = subprocess.run(
                        [
                            "git",
                            "-C",
                            str(skill_path),
                            "log",
                            "--format=%ci",
                            "--reverse",
                            "-1",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        source_info["install_date"] = result.stdout.strip().split()[0]
                except:
                    pass

                # Try to get last update date from git log (newest commit)
                try:
                    result = subprocess.run(
                        [
                            "git",
                            "-C",
                            str(skill_path),
                            "log",
                            "--format=%ci",
                            "-1",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        source_info["updated_at"] = result.stdout.strip().split()[0]
                except:
                    pass

            except Exception as e:
                print(f"Error reading git config for {skill_path}: {e}")

        return source_info

    def _parse_skill_md(self, skill_path: Path, skill_md: Path) -> dict:
        """Parse a SKILL.md file to extract metadata."""
        try:
            content = skill_md.read_text(encoding="utf-8")

            # Extract frontmatter
            frontmatter = {}
            fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if fm_match:
                fm_content = fm_match.group(1)
                # Parse YAML-like frontmatter
                for line in fm_content.split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip()
                        # Handle multiline values (|)
                        if value == "|":
                            continue
                        frontmatter[key] = value

            # Get description (either from frontmatter or first paragraph)
            description = frontmatter.get("description", "")
            if not description:
                # Try to get first paragraph after frontmatter
                body = re.sub(
                    r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL
                ).strip()
                paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
                if paragraphs:
                    description = paragraphs[0][:200]

            # Clean up description (remove newlines, extra spaces)
            description = " ".join(description.split())

            # Get source information
            source_info = self._get_skill_source(skill_path)

            # Override author from frontmatter if available
            if "author" in frontmatter:
                source_info["author"] = frontmatter["author"]

            # Get file timestamps as fallback for non-git skills
            stat = skill_path.stat()
            created_at = source_info.get("install_date") or datetime.fromtimestamp(
                stat.st_ctime
            ).strftime("%Y-%m-%d")
            updated_at = source_info.get("updated_at") or datetime.fromtimestamp(
                stat.st_mtime
            ).strftime("%Y-%m-%d")

            return {
                "id": skill_path.name,
                "name": frontmatter.get("name", skill_path.name),
                "description": description,
                "version": frontmatter.get("version", "N/A"),
                "path": str(skill_path),
                "cli_client": self.cli_client,
                "has_scripts": (skill_path / "scripts").exists(),
                "size": self._get_dir_size(skill_path),
                "source": source_info,
                "created_at": created_at,
                "updated_at": updated_at,
            }

        except Exception as e:
            print(f"Error parsing {skill_md}: {e}")
            return None

    def _get_dir_size(self, path: Path) -> int:
        """Get directory size in bytes."""
        total = 0
        try:
            for entry in os.scandir(path):
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += self._get_dir_size(Path(entry.path))
        except:
            pass
        return total

    def get_skill_detail(self, skill_id: str) -> dict:
        """Get detailed information about a specific skill."""
        skill_path = self.skills_dir / skill_id
        skill_md = skill_path / "SKILL.md"

        if not skill_md.exists():
            return None

        try:
            content = skill_md.read_text(encoding="utf-8")

            # Get file structure
            files = []
            for root, dirs, filenames in os.walk(skill_path):
                # Skip node_modules and hidden dirs
                dirs[:] = [
                    d for d in dirs if not d.startswith(".") and d != "node_modules"
                ]
                for filename in filenames:
                    if filename.startswith("."):
                        continue
                    file_path = Path(root) / filename
                    rel_path = file_path.relative_to(skill_path)
                    files.append(
                        {"path": str(rel_path), "size": file_path.stat().st_size}
                    )

            return {
                "id": skill_id,
                "content": content,
                "files": files,
                "file_count": len(files),
            }

        except Exception as e:
            print(f"Error reading skill detail: {e}")
            return None

    def get_skill_file_content(self, skill_id: str, file_path: str) -> dict:
        """Get the content of a specific file within a skill."""
        skill_path = self.skills_dir / skill_id
        target_file = skill_path / file_path

        # Security check: ensure the file is within the skill directory
        try:
            target_file.resolve().relative_to(skill_path.resolve())
        except ValueError:
            return {"success": False, "error": "Invalid file path"}

        if not target_file.exists() or not target_file.is_file():
            return {"success": False, "error": "File not found"}

        # Check file size (limit to 1MB)
        max_size = 1024 * 1024
        if target_file.stat().st_size > max_size:
            return {"success": False, "error": "File too large (>1MB)"}

        try:
            content = target_file.read_text(encoding="utf-8", errors="replace")
            return {"success": True, "content": content, "path": file_path}
        except Exception as e:
            return {"success": False, "error": f"Failed to read file: {e}"}

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill directory."""
        skill_path = self.skills_dir / skill_id

        if not skill_path.exists():
            return False

        try:
            shutil.rmtree(skill_path)
            return True
        except Exception as e:
            print(f"Error deleting skill: {e}")
            return False

    def sync_skill_to_client(self, skill_id: str, target_client_id: str) -> dict:
        """Sync a skill to another AI client."""
        # Find the skill
        skill = None
        for s in self.skills:
            if s["id"] == skill_id:
                skill = s
                break

        if not skill:
            return {"success": False, "error": "Skill not found"}

        # Get target client info
        if target_client_id not in AI_CLIENTS:
            return {"success": False, "error": f"Unknown AI client: {target_client_id}"}

        target_config = AI_CLIENTS[target_client_id]
        home = Path.home()
        target_skills_dir = home / target_config["skills_dir"]

        # Check if target directory exists, create if needed
        if not target_skills_dir.exists():
            try:
                target_skills_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to create target directory: {e}",
                }

        # Source and target paths
        source_path = Path(skill["path"])
        target_skill_path = target_skills_dir / skill["id"]

        # Check if already exists
        if target_skill_path.exists():
            return {
                "success": False,
                "error": f"Skill '{skill['id']}' already exists in {target_config['name']}",
            }

        try:
            # Copy the entire skill directory
            shutil.copytree(source_path, target_skill_path)

            # Copy git history if it's a git repo
            source_git = source_path / ".git"
            if source_git.exists():
                target_git = target_skill_path / ".git"
                if target_git.exists():
                    shutil.rmtree(target_git)
                shutil.copytree(source_git, target_git)

            return {
                "success": True,
                "message": f"Successfully synced '{skill['name']}' to {target_config['name']}",
                "target_path": str(target_skill_path),
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to sync skill: {e}"}

    def update_skill(self, skill_id: str) -> dict:
        """Update a skill by pulling latest code from git remote."""
        # Find the skill
        skill = None
        for s in self.skills:
            if s["id"] == skill_id:
                skill = s
                break

        if not skill:
            return {"success": False, "error": "Skill not found"}

        source_type = skill.get("source", {}).get("type")
        if source_type not in ("github", "gitlab"):
            return {
                "success": False,
                "error": f"Skill source type '{source_type}' does not support update",
            }

        skill_path = Path(skill["path"])
        git_dir = skill_path / ".git"

        if not git_dir.exists():
            return {"success": False, "error": "Not a git repository"}

        try:
            # Check if there are uncommitted changes (ignore untracked files)
            result = subprocess.run(
                ["git", "-C", str(skill_path), "status", "--porcelain", "--untracked-files=no"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.stdout.strip():
                return {
                    "success": False,
                    "error": "Skill has uncommitted changes. Please commit or discard changes before updating.",
                }

            # Get current commit hash for comparison
            result = subprocess.run(
                ["git", "-C", str(skill_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            old_commit = result.stdout.strip() if result.returncode == 0 else None

            # Fetch latest changes from remote
            result = subprocess.run(
                ["git", "-C", str(skill_path), "fetch", "origin"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to fetch from remote: {result.stderr}",
                }

            # Get default branch (usually main or master)
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(skill_path),
                    "rev-parse",
                    "--abbrev-ref",
                    "origin/HEAD",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                # Fallback to main/master
                result = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(skill_path),
                        "rev-parse",
                        "--verify",
                        "origin/main",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    default_branch = "origin/main"
                else:
                    default_branch = "origin/master"
            else:
                default_branch = result.stdout.strip()

            # Pull latest changes
            result = subprocess.run(
                ["git", "-C", str(skill_path), "reset", "--hard", default_branch],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return {"success": False, "error": f"Failed to update: {result.stderr}"}

            # Get new commit hash
            result = subprocess.run(
                ["git", "-C", str(skill_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            new_commit = result.stdout.strip() if result.returncode == 0 else None

            # Check if actually updated
            if old_commit == new_commit:
                return {
                    "success": True,
                    "message": f"'{skill['name']}' is already up to date",
                    "commit": new_commit[:8] if new_commit else None,
                }

            return {
                "success": True,
                "message": f"Successfully updated '{skill['name']}'",
                "old_commit": old_commit[:8] if old_commit else None,
                "new_commit": new_commit[:8] if new_commit else None,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Update operation timed out"}
        except Exception as e:
            return {"success": False, "error": f"Failed to update skill: {e}"}


class RequestHandler(BaseHTTPRequestHandler):
    skill_manager = None

    def log_message(self, format, *args):
        # Suppress default logging
        pass

    def _send_json(self, data, status=200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_html(self, content, status=200):
        """Send HTML response."""
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(content.encode())

    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == "/" or path == "/index.html":
            self._send_html(HTML_TEMPLATE)

        elif path == "/api/skills":
            # Get sort parameter from query string
            query_params = urllib.parse.parse_qs(parsed_path.query)
            sort_by = query_params.get("sort", ["updated_at"])[0]
            skills = self.skill_manager.scan_skills(sort_by=sort_by)
            self._send_json(
                {
                    "skills": skills,
                    "cli_client": self.skill_manager.cli_client,
                    "skills_dir": str(self.skill_manager.skills_dir),
                }
            )

        elif path == "/api/clients":
            # Return all detected AI clients
            clients = detect_ai_clients()
            self._send_json({"clients": clients})

        elif path == "/api/sync/targets":
            # Return potential sync targets (clients that have skills dir)
            clients = detect_ai_clients()
            current_client = None
            # Determine current client based on skills_dir
            for client in clients:
                if client["skills_dir"] == str(self.skill_manager.skills_dir):
                    current_client = client["id"]
                    break
            # Filter out current client
            targets = [c for c in clients if c["id"] != current_client]
            self._send_json({"targets": targets, "current": current_client})

        elif path.startswith("/api/skills/"):
            parts = path.split("/")
            if len(parts) >= 4 and parts[-1] == "file":
                # Handle file content request: /api/skills/{skill_id}/file?path={file_path}
                skill_id = parts[3]
                query_params = urllib.parse.parse_qs(parsed_path.query)
                file_path = query_params.get("path", [""])[0]

                if not file_path:
                    self._send_json({"error": "Missing file path"}, 400)
                    return

                result = self.skill_manager.get_skill_file_content(skill_id, file_path)
                if result.get("success"):
                    self._send_json(result)
                else:
                    self._send_json(result, 404)
            else:
                # Regular skill detail request
                skill_id = parts[-1]
                detail = self.skill_manager.get_skill_detail(skill_id)
                if detail:
                    self._send_json(detail)
                else:
                    self._send_json({"error": "Skill not found"}, 404)

        else:
            self._send_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        """Handle DELETE requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path.startswith("/api/skills/"):
            skill_id = path.split("/")[-1]
            if self.skill_manager.delete_skill(skill_id):
                self._send_json({"success": True})
            else:
                self._send_json({"error": "Failed to delete skill"}, 500)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        """Handle POST requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = (
            self.rfile.read(content_length).decode("utf-8")
            if content_length > 0
            else "{}"
        )

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        if path.startswith("/api/skills/") and path.endswith("/sync"):
            # Handle sync request: /api/skills/{skill_id}/sync
            parts = path.split("/")
            if len(parts) >= 5:
                skill_id = parts[3]
                target_client = data.get("target_client")
                if not target_client:
                    self._send_json({"error": "Missing target_client"}, 400)
                    return

                result = self.skill_manager.sync_skill_to_client(
                    skill_id, target_client
                )
                if result.get("success"):
                    self._send_json(result)
                else:
                    self._send_json(result, 400)
            else:
                self._send_json({"error": "Invalid path"}, 400)
        elif path.startswith("/api/skills/") and path.endswith("/update"):
            # Handle update request: /api/skills/{skill_id}/update
            parts = path.split("/")
            if len(parts) >= 5:
                skill_id = parts[3]
                result = self.skill_manager.update_skill(skill_id)
                if result.get("success"):
                    self._send_json(result)
                else:
                    self._send_json(result, 400)
            else:
                self._send_json({"error": "Invalid path"}, 400)
        elif path == "/api/switch-client":
            # Handle client switch request
            client_id = data.get("client_id")
            if not client_id:
                self._send_json({"error": "Missing client_id"}, 400)
                return

            if client_id not in AI_CLIENTS:
                self._send_json({"error": f"Unknown client: {client_id}"}, 400)
                return

            # Update the skill manager with new skills directory
            home = Path.home()
            new_skills_dir = home / AI_CLIENTS[client_id]["skills_dir"]
            new_cli_client = AI_CLIENTS[client_id]["name"]

            if not new_skills_dir.exists():
                # Create the directory if it doesn't exist
                try:
                    new_skills_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self._send_json(
                        {"error": f"Failed to create skills directory: {e}"}, 500
                    )
                    return

            # Update skill manager
            self.skill_manager.skills_dir = new_skills_dir
            self.skill_manager.cli_client = new_cli_client

            self._send_json(
                {
                    "success": True,
                    "client_id": client_id,
                    "client_name": new_cli_client,
                    "skills_dir": str(new_skills_dir),
                }
            )
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# HTML Template for the dashboard
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Skill Manager - 本地 AI Skills 管理</title>
    <style>
        :root {
            --primary: #1677ff;
            --primary-light: #e6f4ff;
            --primary-hover: #4096ff;
            --success: #52c41a;
            --warning: #faad14;
            --error: #f5222d;
            --text-primary: rgba(0, 0, 0, 0.88);
            --text-secondary: rgba(0, 0, 0, 0.65);
            --text-tertiary: rgba(0, 0, 0, 0.45);
            --bg-body: #f5f7fa;
            --bg-card: #ffffff;
            --border-color: #f0f0f0;
            --shadow-sm: 0 2px 8px rgba(0,0,0,0.06);
            --shadow-md: 0 4px 16px rgba(0,0,0,0.08);
            --shadow-lg: 0 8px 32px rgba(0,0,0,0.12);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            background: var(--bg-body);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
        }

        /* Hero Section */
        .hero {
            background: linear-gradient(135deg, #1677ff 0%, #0958d9 50%, #003eb3 100%);
            color: white;
            padding: 60px 0 80px;
            position: relative;
            overflow: hidden;
            z-index: 10;
        }

        .hero::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.03'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
            pointer-events: none;
        }

        .hero-content {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 60px;
            position: relative;
            z-index: 10;
        }

        .hero-text {
            flex: 1;
        }

        .hero h1 {
            font-size: 48px;
            font-weight: 700;
            margin-bottom: 16px;
            line-height: 1.2;
        }

        .hero h1 span {
            color: #ffd666;
        }

        .hero-subtitle {
            font-size: 18px;
            opacity: 0.9;
            margin-bottom: 32px;
            max-width: 500px;
        }

        .hero-stats {
            display: flex;
            gap: 40px;
        }

        .hero-stat {
            text-align: center;
        }

        .hero-stat-value {
            font-size: 36px;
            font-weight: 700;
            color: #ffd666;
        }

        .hero-stat-label {
            font-size: 14px;
            opacity: 0.8;
            margin-top: 4px;
        }

        .hero-card {
            width: 320px;
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(255,255,255,0.2);
            overflow: visible;
        }

        .hero-card-title {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .hero-card-content {
            font-size: 14px;
            opacity: 0.9;
            line-height: 1.8;
        }

        .hero-card-stats {
            display: flex;
            gap: 24px;
            margin-top: 8px;
        }

        .hero-card-stat {
            text-align: center;
        }

        .hero-card-stat-value {
            font-size: 28px;
            font-weight: 700;
            line-height: 1.2;
        }

        .hero-card-stat-label {
            font-size: 12px;
            opacity: 0.8;
            margin-top: 4px;
        }

        /* Main Container */
        .main-container {
            max-width: 1200px;
            margin: -40px auto 60px;
            padding: 0 24px;
            position: relative;
            z-index: 2;
        }

        /* Search & Filter Section */
        .search-section {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 24px;
            box-shadow: var(--shadow-md);
            margin-bottom: 32px;
        }

        .search-box {
            position: relative;
            margin-bottom: 20px;
        }

        .search-box input {
            width: 100%;
            padding: 14px 20px 14px 48px;
            border: 2px solid var(--border-color);
            border-radius: 10px;
            font-size: 16px;
            transition: all 0.3s;
            background: var(--bg-body);
        }

        .search-box input:focus {
            outline: none;
            border-color: var(--primary);
            background: white;
            box-shadow: 0 0 0 4px var(--primary-light);
        }

        .search-box::before {
            content: "🔍";
            position: absolute;
            left: 16px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 18px;
        }

        /* Filter Tags */
        .filter-section {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }

        .filter-label {
            font-size: 14px;
            color: var(--text-secondary);
            font-weight: 500;
        }

        .filter-tags {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .filter-tag {
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s;
            border: 1px solid var(--border-color);
            background: white;
            color: var(--text-secondary);
        }

        .filter-tag:hover {
            border-color: var(--primary);
            color: var(--primary);
        }

        .filter-tag.active {
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }

        /* Sort Selector */
        .sort-section {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-left: 20px;
        }

        .sort-label {
            font-size: 14px;
            color: var(--text-secondary);
            font-weight: 500;
        }

        .sort-select {
            padding: 6px 12px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            background: white;
            color: var(--text-primary);
            font-size: 14px;
            cursor: pointer;
            outline: none;
            transition: all 0.2s;
        }

        .sort-select:hover {
            border-color: var(--primary);
        }

        .sort-select:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 2px var(--primary-light);
        }

        /* AI Client Switcher */
        .client-switcher {
            position: relative;
            display: inline-block;
            z-index: 2000;
        }

        .client-switcher-btn {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: rgba(255, 255, 255, 0.15);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 8px;
            color: white;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .client-switcher-btn:hover {
            background: rgba(255, 255, 255, 0.25);
        }

        .client-switcher-dropdown {
            position: absolute;
            top: 100%;
            right: 0;
            margin-top: 8px;
            background: white;
            border-radius: 12px;
            box-shadow: var(--shadow-lg);
            min-width: 220px;
            z-index: 9999;
            display: none;
            overflow: hidden;
        }

        .client-switcher-dropdown.active {
            display: block;
        }

        .client-switcher-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
            font-size: 12px;
            color: var(--text-tertiary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .client-option {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px 16px;
            cursor: pointer;
            transition: all 0.2s;
            border-bottom: 1px solid #f5f5f5;
            user-select: none;
            -webkit-user-select: none;
        }

        .client-option:last-child {
            border-bottom: none;
        }

        .client-option:hover {
            background: var(--primary-light);
        }

        .client-option.active {
            background: var(--primary-light);
        }

        .client-option-icon {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            background: #f5f5f5;
        }

        .client-option-info {
            flex: 1;
        }

        .client-option-name {
            font-size: 14px;
            font-weight: 500;
            color: var(--text-primary);
        }

        .client-option-count {
            font-size: 12px;
            color: var(--text-tertiary);
        }

        .client-option-check {
            color: var(--primary);
            font-size: 16px;
            opacity: 0;
        }

        .client-option.active .client-option-check {
            opacity: 1;
        }

        /* Section Title */
        .section-title {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .section-title .icon {
            width: 32px;
            height: 32px;
            background: var(--primary-light);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
        }

        .section-subtitle {
            font-size: 14px;
            color: var(--text-tertiary);
            margin-left: auto;
            font-weight: normal;
        }

        /* Top Skills List */
        .top-skills-section {
            margin-bottom: 48px;
        }

        .top-skills-list {
            background: var(--bg-card);
            border-radius: 12px;
            box-shadow: var(--shadow-sm);
            overflow: hidden;
        }

        .top-skill-item {
            display: flex;
            align-items: center;
            padding: 16px 24px;
            border-bottom: 1px solid var(--border-color);
            transition: background 0.2s;
            cursor: pointer;
        }

        .top-skill-item:last-child {
            border-bottom: none;
        }

        .top-skill-item:hover {
            background: var(--primary-light);
        }

        .top-skill-rank {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 14px;
            margin-right: 16px;
            background: #f5f5f5;
            color: var(--text-secondary);
        }

        .top-skill-rank.top3 {
            background: linear-gradient(135deg, #ffd666, #faad14);
            color: #874d00;
        }

        .top-skill-icon {
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            margin-right: 16px;
            background: var(--primary-light);
        }

        .top-skill-info {
            flex: 1;
            min-width: 0;
        }

        .top-skill-name {
            font-weight: 600;
            font-size: 15px;
            margin-bottom: 4px;
            color: var(--text-primary);
        }

        .top-skill-desc {
            font-size: 13px;
            color: var(--text-tertiary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .top-skill-tags {
            display: flex;
            gap: 8px;
            margin-right: 24px;
        }

        .top-skill-tag {
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            background: #f5f5f5;
            color: var(--text-secondary);
        }

        .top-skill-meta {
            display: flex;
            align-items: center;
            gap: 16px;
            color: var(--text-tertiary);
            font-size: 13px;
        }

        .top-skill-actions {
            display: flex;
            gap: 8px;
            margin-left: 16px;
        }

        /* Skills Grid */
        .skills-grid-section {
            margin-bottom: 48px;
        }

        .skills-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
        }

        .skill-card {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 20px;
            box-shadow: var(--shadow-sm);
            transition: all 0.3s;
            cursor: pointer;
            border: 1px solid transparent;
        }

        .skill-card:hover {
            transform: translateY(-4px);
            box-shadow: var(--shadow-lg);
            border-color: var(--primary-light);
        }

        .skill-card-header {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 12px;
            position: relative;
        }

        .skill-icon {
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            background: var(--primary-light);
            flex-shrink: 0;
        }

        .skill-title-wrap {
            flex: 1;
            min-width: 0;
            padding-right: 50px;
        }

        .skill-name {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 4px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .skill-version {
            position: absolute;
            top: 0;
            right: 0;
            font-size: 11px;
            color: var(--text-tertiary);
            background: #f0f0f0;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 500;
        }

        .skill-size {
            font-size: 12px;
            color: var(--text-tertiary);
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .skill-description {
            font-size: 14px;
            color: var(--text-secondary);
            line-height: 1.6;
            margin-bottom: 16px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            height: 44px;
        }

        .skill-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-top: 12px;
            border-top: 1px solid var(--border-color);
        }

        .skill-source {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            color: var(--text-tertiary);
        }

        .skill-actions {
            display: flex;
            gap: 6px;
        }

        .btn {
            padding: 6px 14px;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-weight: 500;
        }

        .btn-primary {
            background: var(--primary);
            color: white;
        }

        .btn-primary:hover {
            background: var(--primary-hover);
        }

        .btn-secondary {
            background: #f5f5f5;
            color: var(--text-secondary);
        }

        .btn-secondary:hover {
            background: #e8e8e8;
        }

        .btn-danger {
            background: #fff2f0;
            color: var(--error);
        }

        .btn-danger:hover {
            background: #ffccc7;
        }

        .btn-share {
            background: #f6ffed;
            color: var(--success);
        }

        .btn-share:hover {
            background: #d9f7be;
        }

        /* Source Badge */
        .source-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }

        .source-github {
            background: #1f2937;
            color: white;
        }

        .source-gitlab {
            background: #fc6d26;
            color: white;
        }

        .source-bitbucket {
            background: #0052cc;
            color: white;
        }

        .source-git {
            background: #f05032;
            color: white;
        }

        .source-local {
            background: #f5f5f5;
            color: var(--text-secondary);
        }
            display: -webkit-box;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 80px 20px;
            color: var(--text-tertiary);
            background: var(--bg-card);
            border-radius: 12px;
        }

        .empty-state-icon {
            font-size: 64px;
            margin-bottom: 16px;
        }

        .empty-state h3 {
            font-size: 18px;
            color: var(--text-primary);
            margin-bottom: 8px;
        }

        /* Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            padding: 20px;
            backdrop-filter: blur(4px);
        }

        .modal-overlay.active {
            display: flex;
        }

        .modal {
            background: white;
            border-radius: 16px;
            max-width: 960px;
            width: 100%;
            max-height: 90vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            box-shadow: var(--shadow-lg);
        }

        .modal-header {
            padding: 24px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .modal-title {
            font-size: 18px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: var(--text-tertiary);
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 8px;
            transition: all 0.2s;
        }

        .modal-close:hover {
            background: #f5f5f5;
            color: var(--text-primary);
        }

        .modal-body {
            padding: 24px;
            overflow-y: auto;
            flex: 1;
        }

        .modal-footer {
            padding: 20px;
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: flex-end;
            gap: 12px;
        }

        .detail-section {
            margin-bottom: 24px;
        }

        .detail-section h3 {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-tertiary);
            margin-bottom: 12px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        .detail-content {
            background: var(--bg-body);
            padding: 16px;
            border-radius: 10px;
            font-size: 14px;
            color: var(--text-secondary);
        }

        /* Detail Layout - Two Column */
        .detail-layout {
            display: flex;
            gap: 24px;
            height: 100%;
        }

        .detail-sidebar {
            width: 280px;
            flex-shrink: 0;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .detail-main {
            flex: 1;
            overflow-y: auto;
            padding-right: 8px;
        }

        .detail-main::-webkit-scrollbar {
            width: 6px;
        }

        .detail-main::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 3px;
        }

        .detail-main::-webkit-scrollbar-thumb {
            background: #c1c1c1;
            border-radius: 3px;
        }

        .file-tree {
            background: var(--bg-body);
            border-radius: 10px;
            padding: 16px;
            max-height: 400px;
            overflow-y: auto;
        }

        .file-tree-header {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-tertiary);
            margin-bottom: 12px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        .file-tree-list {
            list-style: none;
        }

        .file-tree-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            margin: 0 -12px;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .file-tree-item:hover {
            background: rgba(0, 0, 0, 0.04);
        }

        .file-tree-item.active {
            background: var(--primary-light);
        }

        .file-tree-item.active .file-tree-path {
            color: var(--primary);
            font-weight: 500;
        }

        .file-tree-path {
            color: var(--text-secondary);
            word-break: break-all;
            padding-right: 8px;
        }

        .file-tree-size {
            color: var(--text-tertiary);
            font-size: 12px;
            flex-shrink: 0;
        }

        .skill-meta-card {
            background: var(--bg-body);
            border-radius: 10px;
            padding: 16px;
        }

        .skill-meta-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e5e7eb;
            font-size: 14px;
        }

        .skill-meta-item:last-child {
            border-bottom: none;
        }

        .skill-meta-label {
            color: var(--text-tertiary);
        }

        .skill-meta-value {
            color: var(--text-secondary);
            font-weight: 500;
        }

        @media (max-width: 768px) {
            .detail-layout {
                flex-direction: column;
            }

            .detail-sidebar {
                width: 100%;
            }
        }

        .code-block {
            background: #1f2937;
            color: #e5e7eb;
            padding: 16px;
            border-radius: 10px;
            overflow-x: auto;
            font-family: 'Monaco', 'Menlo', 'SF Mono', monospace;
            font-size: 13px;
            line-height: 1.6;
            max-height: 400px;
            overflow-y: auto;
            white-space: pre-wrap;
        }

        .file-list {
            list-style: none;
        }

        .file-list li {
            padding: 8px 0;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            font-size: 13px;
        }

        .file-list li:last-child {
            border-bottom: none;
        }

        .file-size {
            color: var(--text-tertiary);
            font-size: 12px;
        }

        .confirm-dialog {
            text-align: center;
            padding: 24px;
        }

        .confirm-dialog p {
            margin-bottom: 20px;
            font-size: 15px;
            color: var(--text-secondary);
        }

        .confirm-dialog .skill-name-highlight {
            font-weight: 600;
            color: var(--error);
        }

        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: var(--text-primary);
            color: white;
            padding: 12px 20px;
            border-radius: 10px;
            box-shadow: var(--shadow-lg);
            transform: translateX(150%);
            transition: transform 0.3s;
            z-index: 2000;
            font-size: 14px;
        }

        .toast.show {
            transform: translateX(0);
        }

        .toast.success {
            background: var(--success);
        }

        .toast.error {
            background: var(--error);
        }

        /* Share Modal */
        .share-modal-content {
            text-align: center;
        }

        .share-modal-content > p {
            color: var(--text-secondary);
            margin-bottom: 20px;
            font-size: 14px;
        }

        .install-text-box {
            background: var(--bg-body);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            text-align: left;
        }

        .install-text-box pre {
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 14px;
            line-height: 1.7;
            color: var(--text-primary);
            white-space: pre-wrap;
            word-break: break-word;
        }

        /* Loading */
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid var(--border-color);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Responsive */
        @media (max-width: 768px) {
            .hero-content {
                flex-direction: column;
                gap: 32px;
            }

            .hero h1 {
                font-size: 32px;
            }

            .hero-card {
                width: 100%;
            }

            .skills-grid {
                grid-template-columns: 1fr;
            }

            .top-skill-item {
                flex-wrap: wrap;
            }

            .top-skill-actions {
                width: 100%;
                margin-left: 0;
                margin-top: 12px;
                justify-content: flex-end;
            }
        }

        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #e5e7eb;
            border-top-color: #667eea;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .cli-badge {
            display: inline-block;
            background: rgba(255,255,255,0.2);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            margin-left: 10px;
        }

        .source-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
        }

        .source-github {
            background: #1f2937;
            color: white;
        }

        .source-gitlab {
            background: #fc6d26;
            color: white;
        }

        .source-bitbucket {
            background: #0052cc;
            color: white;
        }

        .source-git {
            background: #f05032;
            color: white;
        }

        .source-local {
            background: #9ca3af;
            color: white;
        }

        .share-btn {
            background: #10b981 !important;
            color: white !important;
        }

        .share-btn:hover {
            background: #059669 !important;
        }

        .share-modal-content {
            text-align: center;
            padding: 20px;
        }

        .source-info {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }

        .author-tag {
            font-size: 0.75rem;
            color: #6b7280;
            background: #f3f4f6;
            padding: 2px 6px;
            border-radius: 4px;
        }

        .btn-sync {
            background: #8b5cf6 !important;
            color: white !important;
        }

        .btn-sync:hover {
            background: #7c3aed !important;
        }

        .btn-update {
            background: #10b981 !important;
            color: white !important;
        }

        .btn-update:hover {
            background: #059669 !important;
        }

        .sync-modal-content {
            max-width: 400px;
        }

        .sync-clients-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
            margin: 20px 0;
        }

        .sync-client-item {
            display: flex;
            align-items: center;
            padding: 12px 16px;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .sync-client-item:hover {
            border-color: var(--primary);
            background: var(--primary-light);
        }

        .sync-client-item.selected {
            border-color: #8b5cf6;
            background: #f5f3ff;
        }

        .sync-client-icon {
            width: 40px;
            height: 40px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            margin-right: 12px;
            background: #f3f4f6;
        }

        .sync-client-info {
            flex: 1;
        }

        .sync-client-name {
            font-weight: 600;
            color: var(--text-primary);
        }

        .sync-client-meta {
            font-size: 0.85rem;
            color: var(--text-tertiary);
        }

    </style>
</head>
<body>
    <!-- Hero Section -->
    <section class="hero">
        <div class="hero-content">
            <div class="hero-text">
                <h1>装上这个 <span>Skill</span><br>解锁 AI 超能力</h1>
                <p class="hero-subtitle">本地 AI Skills 管理平台，轻松查看、管理和分享你的 AI 技能库</p>
            </div>
            <div class="hero-card">
                <div class="hero-card-title">
                    <div class="client-switcher">
                        <button class="client-switcher-btn" onclick="toggleClientSwitcher(event)">
                            <span id="cliBadge">Loading...</span>
                            <span>▼</span>
                        </button>
                        <div class="client-switcher-dropdown" id="clientSwitcherDropdown">
                            <div class="client-switcher-header">选择 AI Client</div>
                            <div id="clientOptions">
                                <!-- Dynamic content -->
                            </div>
                        </div>
                    </div>
                </div>
                <div class="hero-card-stats">
                    <div class="hero-card-stat">
                        <div class="hero-card-stat-value" id="heroTotalSkills">-</div>
                        <div class="hero-card-stat-label">已安装 Skills</div>
                    </div>
                    <div class="hero-card-stat">
                        <div class="hero-card-stat-value" id="heroTotalSize">-</div>
                        <div class="hero-card-stat-label">总占用空间</div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Main Content -->
    <div class="main-container">
        <!-- Search & Filter Section -->
        <div class="search-section">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="搜索 Skills...">
            </div>
            <div class="filter-section">
                <span class="filter-label">来源筛选:</span>
                <div class="filter-tags" id="filterTags">
                    <div class="filter-tag active" data-filter="all">全部</div>
                    <div class="filter-tag" data-filter="github">GitHub</div>
                    <div class="filter-tag" data-filter="gitlab">GitLab</div>
                    <div class="filter-tag" data-filter="git">Git</div>
                    <div class="filter-tag" data-filter="local">本地</div>
                </div>
                <div class="sort-section">
                    <span class="sort-label">排序:</span>
                    <select class="sort-select" id="sortSelect" onchange="changeSort()">
                        <option value="updated_at">更新时间</option>
                        <option value="created_at">安装时间</option>
                        <option value="size">体积大小</option>
                    </select>
                </div>
                <button class="btn btn-primary" onclick="refreshSkills()" style="margin-left: auto;">
                    🔄 刷新列表
                </button>
            </div>
        </div>

        <!-- All Skills Grid -->
        <div class="skills-grid-section" style="margin-top: 0;">
            <h2 class="section-title">
                <span class="icon">🎯</span>
                全部 Skills
                <span class="section-subtitle" id="skillsCount">加载中...</span>
            </h2>
            <div class="skills-grid" id="skillsGrid">
                <div class="empty-state">
                    <div class="empty-state-icon">📦</div>
                    <h3>正在加载 Skills...</h3>
                </div>
            </div>
        </div>
    </div>

    <!-- Detail Modal -->
    <div class="modal-overlay" id="detailModal">
        <div class="modal">
            <div class="modal-header">
                <div class="modal-title" id="detailTitle">Skill 详情</div>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="detailBody">
                <!-- Content injected here -->
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeModal()">关闭</button>
                <button class="btn btn-share" onclick="shareCurrentSkill()">🔗 分享</button>
                <button class="btn btn-sync" onclick="syncCurrentSkill()">🔄 同步</button>
                <button class="btn btn-danger" onclick="confirmDelete()">🗑️ 卸载</button>
            </div>
        </div>
    </div>

    <!-- Confirm Delete Modal -->
    <div class="modal-overlay" id="confirmModal">
        <div class="modal" style="max-width: 400px;">
            <div class="modal-header">
                <div class="modal-title">Confirm Uninstall</div>
                <button class="modal-close" onclick="closeConfirmModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="confirm-dialog">
                    <p>Are you sure you want to uninstall<br><span class="skill-name-highlight" id="deleteSkillName"></span>?</p>
                    <p style="font-size: 0.9rem; color: #9ca3af;">This action cannot be undone.</p>
                </div>
            </div>
            <div class="modal-footer" style="justify-content: center;">
                <button class="btn btn-secondary" onclick="closeConfirmModal()">Cancel</button>
                <button class="btn btn-danger" onclick="executeDelete()">🗑️ Uninstall</button>
            </div>
        </div>
    </div>

    <!-- Share Modal -->
    <div class="modal-overlay" id="shareModal">
        <div class="modal" style="max-width: 560px;">
            <div class="modal-header">
                <div class="modal-title">🚀 分享 Skill</div>
                <button class="modal-close" onclick="closeShareModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="share-modal-content">
                    <p style="color: #6b7280; margin-bottom: 16px;">将 "<strong id="shareSkillName"></strong>" 分享给其他人</p>

                    <div id="shareInstallBox" style="display: none;">
                        <p style="color: #374151; font-size: 0.9rem; margin-bottom: 12px; text-align: left;">
                            复制下方文本，发送给使用 AI CLI 的朋友，他们可以直接粘贴到对话中自动安装：
                        </p>
                        <div class="install-text-box" style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin-bottom: 16px; text-align: left;">
                            <pre id="installCommandText" style="margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 0.95rem; line-height: 1.6; color: #1f2937; white-space: pre-wrap; word-break: break-word;"></pre>
                        </div>
                        <button class="btn btn-primary" onclick="copyInstallText()" style="width: 100%;">
                            📋 复制安装文本
                        </button>
                    </div>

                    <div id="noSourceBox" style="display: none; padding: 20px;">
                        <p style="color: #9ca3af; font-size: 0.95rem;">
                            此 skill 没有可分享的安装来源。
                        </p>
                    </div>
                </div>
            </div>
            <div class="modal-footer" style="justify-content: center;">
                <button class="btn btn-secondary" onclick="closeShareModal()">关闭</button>
            </div>
        </div>
    </div>

    <!-- Sync Modal -->
    <div class="modal-overlay" id="syncModal">
        <div class="modal sync-modal-content">
            <div class="modal-header">
                <div class="modal-title">🔄 同步 Skill</div>
                <button class="modal-close" onclick="closeSyncModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="share-modal-content">
                    <p style="color: #6b7280; margin-bottom: 16px;">将 "<strong id="syncSkillName"></strong>" 同步到其他 AI Client</p>

                    <div id="syncLoadingBox" style="text-align: center; padding: 40px;">
                        <div class="loading" style="width: 40px; height: 40px; margin: 0 auto 16px;"></div>
                        <p style="color: #6b7280;">正在检测已安装的 AI Client...</p>
                    </div>

                    <div id="syncClientsBox" style="display: none;">
                        <p style="color: #374151; font-size: 0.9rem; margin-bottom: 12px; text-align: left;">
                            选择目标 AI Client：
                        </p>
                        <div class="sync-clients-list" id="syncClientsList">
                            <!-- Dynamic content -->
                        </div>
                        <div id="syncErrorBox" style="display: none; color: #ef4444; font-size: 0.9rem; margin-top: 12px; text-align: center;"></div>
                    </div>

                    <div id="noSyncTargetsBox" style="display: none; padding: 20px; text-align: center;">
                        <p style="color: #9ca3af; font-size: 0.95rem;">
                            未检测到其他已安装的 AI Client。<br>
                            支持的客户端：Claude Code、Qoder、Gemini CLI、Aone Copilot
                        </p>
                    </div>

                    <div id="syncSuccessBox" style="display: none; text-align: center; padding: 20px;">
                        <div style="font-size: 48px; margin-bottom: 12px;">✅</div>
                        <p id="syncSuccessMessage" style="color: #059669; font-weight: 600;"></p>
                    </div>
                </div>
            </div>
            <div class="modal-footer" style="justify-content: center;" id="syncFooter">
                <button class="btn btn-secondary" onclick="closeSyncModal()">关闭</button>
                <button class="btn btn-sync" id="syncConfirmBtn" onclick="executeSync()" disabled>🔄 开始同步</button>
            </div>
        </div>
    </div>

    <div class="toast" id="toast"></div>

    <script>
        let allSkills = [];
        let filteredSkills = [];
        let currentSkill = null;
        let skillToDelete = null;
        let currentFilter = 'all';
        let currentSort = 'updated_at';
        let allClients = [];
        let currentClientId = 'claude';
        let selectedFilePath = null;
        let currentDetailFiles = [];

        // Load skills on page load
        document.addEventListener('DOMContentLoaded', () => {
            loadSkills();
            loadAllClients();
        });

        // Search functionality
        document.getElementById('searchInput').addEventListener('input', (e) => {
            filterSkills(e.target.value, currentFilter);
        });

        // Filter tags functionality
        document.querySelectorAll('.filter-tag').forEach(tag => {
            tag.addEventListener('click', () => {
                document.querySelectorAll('.filter-tag').forEach(t => t.classList.remove('active'));
                tag.classList.add('active');
                currentFilter = tag.dataset.filter;
                filterSkills(document.getElementById('searchInput').value, currentFilter);
            });
        });

        async function loadSkills() {
            try {
                const response = await fetch(`/api/skills?sort=${currentSort}`);
                const data = await response.json();
                allSkills = data.skills;
                filteredSkills = [...allSkills];

                document.getElementById('cliBadge').textContent = data.cli_client || 'AI CLI';
                currentClientId = detectCurrentClientId(data.cli_client);
                updateStats();
                renderSkills(filteredSkills);
            } catch (error) {
                showToast('加载失败', 'error');
                console.error(error);
            }
        }

        function detectCurrentClientId(cliClientName) {
            const clientMap = {
                'Claude Code': 'claude',
                'Qoder': 'qoder',
                'Gemini CLI': 'gemini',
                'Aone Copilot': 'aone_copilot'
            };
            return clientMap[cliClientName] || 'claude';
        }

        async function loadAllClients() {
            try {
                const response = await fetch('/api/clients');
                const data = await response.json();
                allClients = data.clients;
                renderClientSwitcher();
            } catch (error) {
                console.error('Failed to load clients:', error);
            }
        }

        function renderClientSwitcher() {
            const container = document.getElementById('clientOptions');
            if (!container) return;

            container.innerHTML = allClients.map(client => `
                <div class="client-option ${client.id === currentClientId ? 'active' : ''}" onclick="switchClient('${client.id}', event)">
                    <div class="client-option-icon">${getClientIcon(client.id)}</div>
                    <div class="client-option-info">
                        <div class="client-option-name">${escapeHtml(client.name)}</div>
                        <div class="client-option-count">${client.skill_count} 个 skills</div>
                    </div>
                    <div class="client-option-check">✓</div>
                </div>
            `).join('');
        }

        function getClientIcon(clientId) {
            const icons = {
                'claude': '🤖',
                'qoder': '🚀',
                'gemini': '♊',
                'aone_copilot': '👥'
            };
            return icons[clientId] || '🤖';
        }

        function toggleClientSwitcher(event) {
            if (event) event.stopPropagation();
            const dropdown = document.getElementById('clientSwitcherDropdown');
            dropdown.classList.toggle('active');
        }

        async function switchClient(clientId, event) {
            if (event) event.stopPropagation();
            const client = allClients.find(c => c.id === clientId);
            if (!client) return;

            // Close dropdown
            document.getElementById('clientSwitcherDropdown').classList.remove('active');

            // If same client, do nothing
            if (clientId === currentClientId) return;

            showToast(`正在切换到 ${client.name}...`, 'success');

            try {
                // Call API to switch client
                const response = await fetch('/api/switch-client', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ client_id: clientId })
                });

                const result = await response.json();

                if (result.success) {
                    // Update current client
                    currentClientId = clientId;

                    // Reload skills with new client
                    await loadSkills();

                    // Update UI
                    renderClientSwitcher();

                    showToast(`已切换到 ${client.name}`, 'success');
                } else {
                    showToast(result.error || '切换失败', 'error');
                }
            } catch (error) {
                showToast('切换失败，请重试', 'error');
                console.error(error);
            }
        }

        function changeSort() {
            const select = document.getElementById('sortSelect');
            currentSort = select.value;
            loadSkills();
        }

        function updateStats() {
            const totalBytes = allSkills.reduce((sum, s) => sum + (s.size || 0), 0);

            // Update hero stats
            document.getElementById('heroTotalSkills').textContent = allSkills.length;
            document.getElementById('heroTotalSize').textContent = formatSize(totalBytes);

            // Update skills count
            document.getElementById('skillsCount').textContent = `共 ${allSkills.length} 个 Skills`;
        }

        function formatSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }

        function getSourceIcon(source) {
            const icons = {
                'github': '🐙',
                'gitlab': '🦊',
                'bitbucket': '🪣',
                'git': '🌿',
                'local': '📁'
            };
            return icons[source?.type] || '📁';
        }

        function getSkillEmoji(name) {
            const emojis = {
                'algorithmic-art': '🎨',
                'brand-guidelines': '🎨',
                'browse': '🔍',
                'canvas-design': '🎨',
                'claude-api': '🤖',
                'docx': '📝',
                'find-skills': '🔍',
                'frontend-design': '🎨',
                'git-commit-diff': '💻',
                'gstack': '🔍',
                'internal-comms': '💬',
                'pdf': '📄',
                'pptx': '📊',
                'qa': '🧪',
                'retro': '📈',
                'review': '👀',
                'ship': '🚀',
                'skill-manager': '🎯',
                'xlsx': '📊'
            };
            return emojis[name] || '📦';
        }

        function renderSkills(skills) {
            const grid = document.getElementById('skillsGrid');

            if (skills.length === 0) {
                grid.innerHTML = `
                    <div class="empty-state" style="grid-column: 1/-1;">
                        <div class="empty-state-icon">🔍</div>
                        <h3>没有找到 Skills</h3>
                        <p>尝试调整搜索条件</p>
                    </div>
                `;
                return;
            }

            grid.innerHTML = skills.map(skill => {
                const sourceType = skill.source?.type || 'local';
                const canUpdate = sourceType === 'github' || sourceType === 'gitlab';
                return `
                <div class="skill-card" onclick="showDetail('${skill.id}')">
                    <div class="skill-card-header">
                        <div class="skill-icon">${getSkillEmoji(skill.id)}</div>
                        <div class="skill-title-wrap">
                            <div class="skill-name">${escapeHtml(skill.name)}</div>
                            <span class="skill-size">📦 ${formatSize(skill.size || 0)}</span>
                        </div>
                        <span class="skill-version">${escapeHtml(skill.version || 'N/A')}</span>
                    </div>
                    <div class="skill-description">${escapeHtml(skill.description || '暂无描述')}</div>
                    <div class="skill-footer">
                        <div class="skill-source">
                            ${getSourceIcon(skill.source)} ${sourceType}
                        </div>
                        <div class="skill-actions" onclick="event.stopPropagation()">
                            ${canUpdate ? `<button class="btn btn-update" onclick="updateSkill('${skill.id}')">更新</button>` : ''}
                            <button class="btn btn-share" onclick="showShareModal('${skill.id}')">分享</button>
                            <button class="btn btn-sync" onclick="showSyncModal('${skill.id}')">同步</button>
                        </div>
                    </div>
                </div>
            `}).join('');
        }

        function filterSkills(query, filterType = 'all') {
            const lowerQuery = query.toLowerCase();
            filteredSkills = allSkills.filter(skill => {
                const matchesSearch = skill.name.toLowerCase().includes(lowerQuery) ||
                    (skill.description && skill.description.toLowerCase().includes(lowerQuery));
                const matchesFilter = filterType === 'all' ||
                    (skill.source?.type === filterType) ||
                    (filterType === 'local' && (!skill.source || skill.source.type === 'local'));
                return matchesSearch && matchesFilter;
            });
            renderSkills(filteredSkills);
        }

        function refreshSkills() {
            const btn = document.querySelector('.search-section .btn-primary');
            btn.innerHTML = '<span class="loading"></span> 刷新中...';

            loadSkills().then(() => {
                btn.innerHTML = '🔄 刷新列表';
                showToast('列表已刷新', 'success');
            }).catch(() => {
                btn.innerHTML = '🔄 刷新列表';
            });
        }

        async function showDetail(skillId) {
            currentSkill = allSkills.find(s => s.id === skillId);
            if (!currentSkill) return;

            try {
                const response = await fetch(`/api/skills/${skillId}`);
                const detail = await response.json();

                document.getElementById('detailTitle').textContent = '📦 ' + currentSkill.name;

                const sourceType = currentSkill.source?.type || 'local';
                const canUpdate = sourceType === 'github' || sourceType === 'gitlab';

                // Store files for later use
                currentDetailFiles = detail.files || [];
                selectedFilePath = 'SKILL.md'; // Default select SKILL.md

                // Get SKILL.md file info
                const skillMdFile = currentDetailFiles.find(f => f.path === 'SKILL.md');

                document.getElementById('detailBody').innerHTML = `
                    <div class="detail-layout">
                        <!-- Left Sidebar: File Tree & Meta -->
                        <div class="detail-sidebar">
                            <div class="file-tree">
                                <div class="file-tree-header">📂 文件 (${detail.file_count || 0})</div>
                                <ul class="file-tree-list" id="fileTreeList">
                                    ${(detail.files || []).map(f => `
                                        <li class="file-tree-item ${f.path === 'SKILL.md' ? 'active' : ''}" onclick="selectFile('${escapeHtml(f.path)}')">
                                            <span class="file-tree-path">${escapeHtml(f.path)}</span>
                                            <span class="file-tree-size">${formatSize(f.size)}</span>
                                        </li>
                                    `).join('')}
                                </ul>
                            </div>
                            <div class="skill-meta-card">
                                <div class="skill-meta-item">
                                    <span class="skill-meta-label">版本</span>
                                    <span class="skill-meta-value">${escapeHtml(currentSkill.version || 'N/A')}</span>
                                </div>
                                <div class="skill-meta-item">
                                    <span class="skill-meta-label">来源</span>
                                    <span class="skill-meta-value">${sourceType}</span>
                                </div>
                                <div class="skill-meta-item">
                                    <span class="skill-meta-label">大小</span>
                                    <span class="skill-meta-value">${formatSize(currentSkill.size || 0)}</span>
                                </div>
                                ${currentSkill.source?.author ? `
                                <div class="skill-meta-item">
                                    <span class="skill-meta-label">作者</span>
                                    <span class="skill-meta-value">${escapeHtml(currentSkill.source.author)}</span>
                                </div>
                                ` : ''}
                            </div>
                        </div>

                        <!-- Right Main: Description & Content -->
                        <div class="detail-main" id="detailMain">
                            <div class="detail-section">
                                <h3>📝 描述</h3>
                                <div class="detail-content">${escapeHtml(currentSkill.description || '暂无描述')}</div>
                            </div>
                            ${currentSkill.source?.url ? `
                            <div class="detail-section">
                                <h3>🔗 来源链接</h3>
                                <div class="detail-content" style="font-family: monospace; font-size: 13px;">
                                    <a href="${escapeHtml(currentSkill.source.url)}" target="_blank" style="color: var(--primary);">${escapeHtml(currentSkill.source.url)}</a>
                                </div>
                            </div>
                            ` : ''}
                            <div class="detail-section">
                                <h3>📍 本地路径</h3>
                                <div class="detail-content" style="font-family: monospace; font-size: 13px;">${escapeHtml(currentSkill.path)}</div>
                            </div>
                            <div class="detail-section" id="fileContentSection">
                                <h3 id="fileContentTitle">📄 SKILL.md</h3>
                                <div class="code-block" id="fileContent">${escapeHtml(detail.content || 'No content')}</div>
                            </div>
                        </div>
                    </div>
                `;

                document.getElementById('detailModal').classList.add('active');
            } catch (error) {
                showToast('加载详情失败', 'error');
            }
        }

        async function selectFile(filePath) {
            if (!currentSkill) return;

            selectedFilePath = filePath;

            // Update UI to show active file
            document.querySelectorAll('.file-tree-item').forEach(item => {
                item.classList.remove('active');
                if (item.querySelector('.file-tree-path')?.textContent === filePath) {
                    item.classList.add('active');
                }
            });

            // Update file content title
            document.getElementById('fileContentTitle').textContent = `📄 ${filePath}`;

            // Load file content
            const fileContentDiv = document.getElementById('fileContent');
            fileContentDiv.textContent = '加载中...';

            try {
                const response = await fetch(`/api/skills/${currentSkill.id}/file?path=${encodeURIComponent(filePath)}`);
                const data = await response.json();

                if (data.success) {
                    fileContentDiv.textContent = data.content || '(空文件)';
                } else {
                    fileContentDiv.textContent = `加载失败: ${data.error || '未知错误'}`;
                }
            } catch (error) {
                fileContentDiv.textContent = '加载文件内容失败';
                console.error(error);
            }
        }

        function closeModal() {
            document.getElementById('detailModal').classList.remove('active');
            currentSkill = null;
        }

        function promptDelete(skillId, skillName) {
            skillToDelete = skillId;
            document.getElementById('deleteSkillName').textContent = skillName;
            document.getElementById('confirmModal').classList.add('active');
        }

        function closeConfirmModal() {
            document.getElementById('confirmModal').classList.remove('active');
            skillToDelete = null;
        }

        function confirmDelete() {
            if (currentSkill) {
                promptDelete(currentSkill.id, currentSkill.name);
            }
        }

        async function executeDelete() {
            if (!skillToDelete) return;

            try {
                const response = await fetch(`/api/skills/${skillToDelete}`, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    showToast('Skill uninstalled successfully', 'success');
                    closeConfirmModal();
                    closeModal();
                    await loadSkills();
                } else {
                    throw new Error('Delete failed');
                }
            } catch (error) {
                showToast('Failed to uninstall skill', 'error');
            }
        }

        function showToast(message, type = 'info') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = `toast ${type} show`;

            setTimeout(() => {
                toast.classList.remove('show');
            }, 3000);
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function renderSourceBadge(source) {
            if (!source) return '';

            const icons = {
                'github': '🐙',
                'gitlab': '🦊',
                'bitbucket': '🪣',
                'git': '🌿',
                'local': '📁'
            };

            const icon = icons[source.type] || '📁';
            const badgeClass = `source-${source.type}`;

            let html = `<span class="source-badge ${badgeClass}">${icon} ${source.type}</span>`;

            if (source.author) {
                html += `<span class="author-tag">by ${escapeHtml(source.author)}</span>`;
            }

            return html;
        }

        function renderSourceDetail(source) {
            if (!source) return '<p>No source information available</p>';

            const icons = {
                'github': '🐙',
                'gitlab': '🦊',
                'bitbucket': '🪣',
                'git': '🌿',
                'local': '📁'
            };

            let html = `<div class="source-info">`;
            html += `<span class="source-badge source-${source.type}">${icons[source.type] || '📁'} ${source.type}</span>`;

            if (source.author) {
                html += `<span class="author-tag">👤 ${escapeHtml(source.author)}</span>`;
            }

            if (source.install_date) {
                html += `<span class="author-tag">📅 ${source.install_date}</span>`;
            }

            html += `</div>`;

            if (source.url) {
                html += `<div style="margin-top: 10px;">`;
                html += `<a href="${escapeHtml(source.url)}" target="_blank" style="color: #667eea; text-decoration: none; word-break: break-all;">`;
                html += `🔗 ${escapeHtml(source.url)}</a>`;
                html += `</div>`;
            } else if (source.remote) {
                html += `<div style="margin-top: 10px; font-family: monospace; font-size: 0.85rem; color: #6b7280;">`;
                html += `📎 ${escapeHtml(source.remote)}`;
                html += `</div>`;
            }

            return html;
        }

        // Share functionality
        let skillToShare = null;
        let installTextToCopy = '';

        function generateInstallText(skill) {
            const hasGitSource = skill.source && (skill.source.url || skill.source.remote);
            const isLocal = !hasGitSource || skill.source.type === 'local';

            if (isLocal) {
                // 本地 skill，提示使用 find-skills
                return `我想安装 "${skill.name}" 这个 skill，请帮我使用 find-skills 查找并安装。`;
            } else {
                // 有 git 来源，提供 clone 安装方式
                const repoUrl = skill.source.url || skill.source.remote;
                const skillDesc = skill.description || '一个实用的 AI CLI skill';

                return `请帮我安装 "${skill.name}" 这个 skill。

操作步骤：
1. 从仓库 clone 到本地 skills 目录：
   git clone ${repoUrl} ~/.claude/skills/${skill.id}

2. 或者如果你已经安装了 find-skills，可以直接让我帮你查找并安装。

Skill 简介：${skillDesc}`;
            }
        }

        function showShareModal(skillId) {
            skillToShare = allSkills.find(s => s.id === skillId);
            if (!skillToShare) return;

            document.getElementById('shareSkillName').textContent = skillToShare.name;

            const hasSource = skillToShare.source && (skillToShare.source.url || skillToShare.source.remote);
            const isLocal = !hasSource || skillToShare.source.type === 'local';

            if (hasSource || isLocal) {
                // 生成安装提示文本
                installTextToCopy = generateInstallText(skillToShare);
                document.getElementById('installCommandText').textContent = installTextToCopy;
                document.getElementById('shareInstallBox').style.display = 'block';
                document.getElementById('noSourceBox').style.display = 'none';
            } else {
                document.getElementById('shareInstallBox').style.display = 'none';
                document.getElementById('noSourceBox').style.display = 'block';
            }

            document.getElementById('shareModal').classList.add('active');
        }

        function closeShareModal() {
            document.getElementById('shareModal').classList.remove('active');
            skillToShare = null;
            installTextToCopy = '';
        }

        function shareCurrentSkill() {
            if (currentSkill) {
                showShareModal(currentSkill.id);
            }
        }

        function copyInstallText() {
            if (!installTextToCopy) return;

            navigator.clipboard.writeText(installTextToCopy).then(() => {
                showToast('安装文本已复制到剪贴板！', 'success');
            }).catch(() => {
                // 降级方案
                const textarea = document.createElement('textarea');
                textarea.value = installTextToCopy;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                try {
                    document.execCommand('copy');
                    showToast('安装文本已复制到剪贴板！', 'success');
                } catch (err) {
                    showToast('复制失败，请手动复制', 'error');
                }
                document.body.removeChild(textarea);
            });
        }

        // Sync functionality
        let skillToSync = null;
        let selectedSyncTarget = null;
        let availableSyncTargets = [];

        const clientIcons = {
            'claude': '🤖',
            'qoder': '🚀',
            'gemini': '♊',
            'aone_copilot': '👥'
        };

        async function showSyncModal(skillId) {
            skillToSync = allSkills.find(s => s.id === skillId);
            if (!skillToSync) return;

            document.getElementById('syncSkillName').textContent = skillToSync.name;
            document.getElementById('syncModal').classList.add('active');

            // Reset state
            selectedSyncTarget = null;
            availableSyncTargets = [];
            document.getElementById('syncConfirmBtn').disabled = true;
            document.getElementById('syncErrorBox').style.display = 'none';
            document.getElementById('syncErrorBox').textContent = '';

            // Show loading
            document.getElementById('syncLoadingBox').style.display = 'block';
            document.getElementById('syncClientsBox').style.display = 'none';
            document.getElementById('noSyncTargetsBox').style.display = 'none';
            document.getElementById('syncSuccessBox').style.display = 'none';
            document.getElementById('syncFooter').style.display = 'flex';

            try {
                const response = await fetch('/api/sync/targets');
                const data = await response.json();

                availableSyncTargets = data.targets || [];

                document.getElementById('syncLoadingBox').style.display = 'none';

                if (availableSyncTargets.length === 0) {
                    document.getElementById('noSyncTargetsBox').style.display = 'block';
                    document.getElementById('syncFooter').style.display = 'none';
                } else {
                    renderSyncTargets(availableSyncTargets);
                    document.getElementById('syncClientsBox').style.display = 'block';
                }
            } catch (error) {
                document.getElementById('syncLoadingBox').style.display = 'none';
                document.getElementById('noSyncTargetsBox').style.display = 'block';
                document.getElementById('noSyncTargetsBox').innerHTML = '<p style="color: #ef4444;">加载失败，请重试</p>';
            }
        }

        function renderSyncTargets(targets) {
            const container = document.getElementById('syncClientsList');
            container.innerHTML = targets.map(target => `
                <div class="sync-client-item" data-client-id="${target.id}" onclick="selectSyncTarget('${target.id}')">
                    <div class="sync-client-icon">${clientIcons[target.id] || '🤖'}</div>
                    <div class="sync-client-info">
                        <div class="sync-client-name">${escapeHtml(target.name)}</div>
                        <div class="sync-client-meta">${target.skill_count} 个 skills</div>
                    </div>
                </div>
            `).join('');
        }

        function selectSyncTarget(clientId) {
            selectedSyncTarget = clientId;

            // Update UI
            document.querySelectorAll('.sync-client-item').forEach(item => {
                if (item.dataset.clientId === clientId) {
                    item.classList.add('selected');
                } else {
                    item.classList.remove('selected');
                }
            });

            document.getElementById('syncConfirmBtn').disabled = false;
            document.getElementById('syncErrorBox').style.display = 'none';
        }

        async function executeSync() {
            if (!skillToSync || !selectedSyncTarget) return;

            const btn = document.getElementById('syncConfirmBtn');
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span> 同步中...';

            try {
                const response = await fetch(`/api/skills/${skillToSync.id}/sync`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ target_client: selectedSyncTarget })
                });

                const result = await response.json();

                if (result.success) {
                    document.getElementById('syncClientsBox').style.display = 'none';
                    document.getElementById('syncSuccessBox').style.display = 'block';
                    document.getElementById('syncSuccessMessage').textContent = result.message;
                    document.getElementById('syncFooter').innerHTML = `
                        <button class="btn btn-secondary" onclick="closeSyncModal()">关闭</button>
                    `;
                    showToast(result.message, 'success');
                } else {
                    btn.disabled = false;
                    btn.innerHTML = '🔄 开始同步';
                    document.getElementById('syncErrorBox').textContent = result.error || '同步失败';
                    document.getElementById('syncErrorBox').style.display = 'block';
                }
            } catch (error) {
                btn.disabled = false;
                btn.innerHTML = '🔄 开始同步';
                document.getElementById('syncErrorBox').textContent = '同步失败，请重试';
                document.getElementById('syncErrorBox').style.display = 'block';
            }
        }

        function closeSyncModal() {
            document.getElementById('syncModal').classList.remove('active');
            skillToSync = null;
            selectedSyncTarget = null;
            availableSyncTargets = [];

            // Reset button state
            const btn = document.getElementById('syncConfirmBtn');
            btn.disabled = true;
            btn.innerHTML = '🔄 开始同步';
        }

        function syncCurrentSkill() {
            if (currentSkill) {
                showSyncModal(currentSkill.id);
            }
        }

        async function updateSkill(skillId) {
            const skill = allSkills.find(s => s.id === skillId);
            if (!skill) return;

            const sourceType = skill.source?.type;
            if (sourceType !== 'github' && sourceType !== 'gitlab') {
                showToast('只有 GitHub/GitLab 来源的 skill 支持更新', 'error');
                return;
            }

            if (!confirm(`确定要更新 "${skill.name}" 吗？\n将从 ${sourceType} 拉取最新代码。`)) {
                return;
            }

            try {
                showToast(`正在更新 ${skill.name}...`, 'success');

                const response = await fetch(`/api/skills/${skillId}/update`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                const result = await response.json();

                if (result.success) {
                    showToast(result.message, 'success');
                    // Refresh the list
                    refreshSkills();
                } else {
                    showToast(result.error || '更新失败', 'error');
                }
            } catch (error) {
                showToast('更新失败，请重试', 'error');
                console.error(error);
            }
        }

        // Close modals on overlay click
        document.querySelectorAll('.modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    overlay.classList.remove('active');
                }
            });
        });

        // Close client switcher when clicking outside
        document.addEventListener('click', (e) => {
            const switcher = document.querySelector('.client-switcher');
            const dropdown = document.getElementById('clientSwitcherDropdown');
            if (switcher && dropdown && !switcher.contains(e.target)) {
                dropdown.classList.remove('active');
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeModal();
                closeConfirmModal();
                closeShareModal();
                closeSyncModal();
                // Close client switcher
                const dropdown = document.getElementById('clientSwitcherDropdown');
                if (dropdown) dropdown.classList.remove('active');
            }
        });
    </script>
</body>
</html>
"""


def find_available_port(start_port=DEFAULT_PORT, max_attempts=MAX_PORT_ATTEMPTS):
    """Find an available port."""
    import socket

    for port in range(start_port, start_port + max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", port))
            sock.close()
            return port
        except OSError:
            continue

    raise RuntimeError(
        f"Could not find an available port in range {start_port}-{start_port + max_attempts}"
    )


def open_browser(url, delay=1.0):
    """Open browser after a short delay to ensure server is ready."""

    def _open():
        webbrowser.open(url)

    Timer(delay, _open).start()


def format_size_cli(size_bytes):
    """Format size for CLI output."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


def print_skill_detail(skill):
    """Print detailed information for a skill."""
    print("\n" + "=" * 60)
    print(f"📦 {skill.get('name', skill['id'])}")
    print("=" * 60)

    desc = skill.get("description", "暂无描述")
    if desc:
        print(f"\n📝 描述:\n   {desc}")

    version = skill.get("version", "N/A")
    print(f"\n📌 版本: {version}")

    print(f"📁 路径: {skill.get('path', 'N/A')}")
    print(f"📊 大小: {format_size_cli(skill.get('size', 0))}")

    if skill.get("has_scripts"):
        print("📜 包含 scripts: 是")

    # Source info
    source = skill.get("source", {})
    if source and source.get("type") != "local":
        print(f"\n🔗 来源: {source.get('type', 'unknown').upper()}")
        url = source.get("url") or source.get("remote")
        if url:
            print(f"   URL: {url}")
        if source.get("author"):
            print(f"   作者: {source['author']}")
        if source.get("install_date"):
            print(f"   安装时间: {source['install_date']}")
    else:
        print(f"\n🔗 来源: Local (本地安装)")

    # Files list
    files = skill.get("files", [])
    if files:
        print(f"\n📂 文件列表 ({len(files)} 个):")
        for f in files[:10]:  # Show first 10 files
            print(
                f"   • {f.get('name', 'unknown')} ({format_size_cli(f.get('size', 0))})"
            )
        if len(files) > 10:
            print(f"   ... 还有 {len(files) - 10} 个文件")

    print("=" * 60)


def generate_share_text(skill):
    """Generate installation prompt for sharing."""
    has_git_source = skill.get("source") and (
        skill.get("source", {}).get("url") or skill.get("source", {}).get("remote")
    )
    is_local = not has_git_source or skill.get("source", {}).get("type") == "local"

    if is_local:
        return f"我想安装 \"{skill.get('name', skill['id'])}\" 这个 skill，请帮我使用 find-skills 查找并安装。"
    else:
        repo_url = skill.get("source", {}).get("url") or skill.get("source", {}).get(
            "remote"
        )
        skill_desc = skill.get("description", "一个实用的 AI CLI skill")
        skill_id = skill.get("id", "skill-name")

        return f"""请帮我安装 "{skill.get('name', skill_id)}" 这个 skill。

操作步骤：
1. 从仓库 clone 到本地 skills 目录：
   git clone {repo_url} ~/.claude/skills/{skill_id}

或者使用 find-skills：
我想安装 "{skill.get('name', skill_id)}" 这个 skill，请帮我使用 find-skills 查找并安装。"""


def cli_interactive_menu(skills, cli_client, skills_dir):
    """Interactive CLI menu for skill management."""
    if not skills:
        print("\n📦 No skills found.")
        return

    while True:
        print(f"\n🎯 {cli_client} - Installed Skills ({len(skills)} total)\n")
        print("-" * 70)
        print(f"{'#':<4} {'Name':<22} {'Version':<10} {'Source':<10} {'Size':<8}")
        print("-" * 70)

        for idx, skill in enumerate(skills, 1):
            name = skill.get("name", skill["id"])[:20]
            version = (skill.get("version") or "N/A")[:8]
            source_type = (skill.get("source", {}).get("type") or "local")[:8]
            size = format_size_cli(skill.get("size", 0))
            print(f"{idx:<4} {name:<22} {version:<10} {source_type:<10} {size:<8}")

        print("-" * 70)
        print(
            "\n操作: [数字] 查看详情 | [s数字] 分享 | [y数字] 同步 | [d数字] 卸载 | [a] AI Clients | [q] 退出"
        )
        print(
            "示例: 1 (查看#1详情) | s1 (分享#1) | y1 (同步#1) | d1 (卸载#1) | a (查看AI Clients)"
        )

        try:
            choice = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n\nbye!")
            break

        if choice == "q" or choice == "quit":
            print("\nbye!")
            break

        # Parse command
        if choice.startswith("s"):  # Share
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(skills):
                    skill = skills[idx]
                    print(f"\n📤 分享 \"{skill.get('name', skill['id'])}\":")
                    print("-" * 60)
                    print(generate_share_text(skill))
                    print("-" * 60)
                    print("\n已复制到剪贴板 (或手动复制上述文本)")
                else:
                    print("❌ 无效的序号")
            except ValueError:
                print("❌ 无效输入")

        elif choice.startswith("d"):  # Delete/Uninstall
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(skills):
                    skill = skills[idx]
                    print(f"\n⚠️  确认卸载 \"{skill.get('name', skill['id'])}\"?")
                    confirm = input("输入 'yes' 确认卸载: ").strip().lower()
                    if confirm == "yes":
                        skill_path = Path(skills_dir) / skill["id"]
                        if skill_path.exists():
                            shutil.rmtree(skill_path)
                            print(f"✅ \"{skill.get('name', skill['id'])}\" 已卸载")
                            # Refresh skills list
                            skills = [s for s in skills if s["id"] != skill["id"]]
                        else:
                            print("❌ 目录不存在")
                    else:
                        print("已取消")
                else:
                    print("❌ 无效的序号")
            except ValueError:
                print("❌ 无效输入")

        elif choice.isdigit():  # View detail
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(skills):
                    print_skill_detail(skills[idx])
                else:
                    print("❌ 无效的序号")
            except ValueError:
                print("❌ 无效输入")

        elif choice == "a":  # Show AI Clients
            print("\n🤖 已安装的 AI Clients:")
            print("-" * 60)
            clients = detect_ai_clients()
            current_client_name = None

            # Find current client name
            for client in clients:
                if client["skills_dir"] == str(skills_dir):
                    current_client_name = client["name"]
                    break

            for client in clients:
                is_current = client["skills_dir"] == str(skills_dir)
                marker = " 👈 当前" if is_current else ""
                print(f"  {client['id']}: {client['name']}")
                print(f"     路径: {client['skills_dir']}")
                print(f"     Skills: {client['skill_count']} 个{marker}")
                print()

            if len(clients) <= 1:
                print("💡 只检测到一个 AI Client，无法使用同步功能")
                print("   支持的客户端: Claude Code、Qoder、Gemini CLI、Aone Copilot")
            else:
                print(f"💡 使用 'y数字' 命令将 skill 同步到其他 AI Client")

        elif choice.startswith("y"):  # Sync (y = sync)
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(skills):
                    skill = skills[idx]
                    skill_id = skill["id"]

                    # Detect available sync targets
                    clients = detect_ai_clients()
                    targets = [c for c in clients if c["skills_dir"] != str(skills_dir)]

                    if not targets:
                        print("❌ 未检测到其他已安装的 AI Client")
                        print(
                            "   支持的客户端: Claude Code、Qoder、Gemini CLI、Aone Copilot"
                        )
                        continue

                    print(f"\n🔄 同步 \"{skill.get('name', skill_id)}\" 到:")
                    print("-" * 60)
                    for i, target in enumerate(targets, 1):
                        print(
                            f"  {i}. {target['name']} ({target['skill_count']} skills)"
                        )
                        print(f"     路径: {target['skills_dir']}")
                    print()

                    try:
                        target_idx = int(input("选择目标 (输入序号): ").strip()) - 1
                        if 0 <= target_idx < len(targets):
                            target_client = targets[target_idx]
                            print(f"\n正在同步到 {target_client['name']}...")

                            result = skill_manager.sync_skill_to_client(
                                skill_id, target_client["id"]
                            )
                            if result["success"]:
                                print(f"✅ {result['message']}")
                                print(f"   目标路径: {result['target_path']}")
                            else:
                                print(f"❌ 同步失败: {result['error']}")
                        else:
                            print("❌ 无效选择")
                    except ValueError:
                        print("❌ 无效输入")
                else:
                    print("❌ 无效的序号")
            except ValueError:
                print("❌ 无效输入")

        else:
            print("❌ 无效命令")


def print_skills_table(skills, cli_client):
    """Legacy: Print skills in a simple table for CLI mode."""
    if not skills:
        print("\n📦 No skills found.")
        return

    print(f"\n🎯 {cli_client} - Installed Skills ({len(skills)} total)\n")
    print("-" * 100)
    print(f"{'Name':<20} {'Version':<10} {'Source':<12} {'Size':<8} {'Description'}")
    print("-" * 100)

    for skill in skills:
        name = skill.get("name", skill["id"])[:18]
        version = (skill.get("version") or "N/A")[:8]
        source_type = (skill.get("source", {}).get("type") or "local")[:10]
        size = format_size_cli(skill.get("size", 0))
        desc = (skill.get("description") or "No description")[:40]

        print(f"{name:<20} {version:<10} {source_type:<12} {size:<8} {desc}")

    print("-" * 100)

    # Print source details section
    git_skills = [
        s for s in skills if s.get("source", {}).get("type") not in (None, "local")
    ]
    if git_skills:
        print("\n📋 Git Repository Sources:\n")
        for skill in git_skills:
            source = skill.get("source", {})
            url = source.get("url") or source.get("remote") or "N/A"
            author = source.get("author") or "Unknown"
            print(f"  • {skill.get('name', skill['id'])}")
            print(f"    URL: {url}")
            print(f"    Author: {author}")
            if source.get("install_date"):
                print(f"    Installed: {source['install_date']}")
            print()


def main():
    # Check for CLI mode flags
    cli_mode = False
    simple_mode = False
    args = sys.argv[1:]

    if "--cli" in args or "--list" in args or "-l" in args:
        cli_mode = True
        # Remove the flag from args
        args = [a for a in args if a not in ("--cli", "--list", "-l")]

    if "--simple" in args or "-s" in args:
        simple_mode = True
        args = [a for a in args if a not in ("--simple", "-s")]

    if len(args) < 1:
        print(
            "Usage: server.py <skills_dir> [cli_client] [--cli|--list|-l] [--simple|-s]"
        )
        print("\nOptions:")
        print("  --cli, --list, -l    Display skills in terminal (no web server)")
        print("  --simple, -s         Simple list mode (no interaction)")
        sys.exit(1)

    skills_dir = args[0]
    cli_client = args[1] if len(args) > 1 else "unknown"

    # Verify skills directory exists
    if not os.path.exists(skills_dir):
        print(f"Error: Skills directory not found: {skills_dir}")
        sys.exit(1)

    # Create skill manager
    skill_manager = SkillManager(skills_dir, cli_client)
    skills = skill_manager.scan_skills()

    if cli_mode:
        if simple_mode:
            # Simple CLI mode: print table and exit
            print_skills_table(skills, cli_client)
        else:
            # Interactive CLI mode
            cli_interactive_menu(skills, cli_client, skills_dir)
        sys.exit(0)

    # Web mode: start HTTP server
    port = find_available_port()

    # Set up request handler
    RequestHandler.skill_manager = skill_manager

    # Create server
    server = HTTPServer(("127.0.0.1", port), RequestHandler)

    url = f"http://127.0.0.1:{port}"

    # Open browser
    open_browser(url)

    # Minimal output in web mode
    print(f"\n🎯 Skill Manager: {url}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
