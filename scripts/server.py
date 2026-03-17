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

# Configuration
DEFAULT_PORT = 8765
MAX_PORT_ATTEMPTS = 10


class SkillManager:
    def __init__(self, skills_dir: str, cli_client: str):
        self.skills_dir = Path(skills_dir)
        self.cli_client = cli_client
        self.skills = []

    def scan_skills(self):
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

        # Sort by name
        self.skills.sort(key=lambda x: x["name"].lower())
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
                                match = re.match(r'git@([^:]+):(.+)', remote_url)
                                if match:
                                    domain, path = match.groups()
                                    source_info["url"] = f"https://{domain}/{path}".replace(".git", "")
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
            skills = self.skill_manager.scan_skills()
            self._send_json(
                {"skills": skills, "cli_client": self.skill_manager.cli_client}
            )

        elif path.startswith("/api/skills/"):
            skill_id = path.split("/")[-1]
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

    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, DELETE, OPTIONS")
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
            z-index: 1;
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
            font-size: 12px;
            color: var(--text-tertiary);
            background: #f5f5f5;
            padding: 2px 8px;
            border-radius: 4px;
            display: inline-block;
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
            max-width: 720px;
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

    </style>
</head>
<body>
    <!-- Hero Section -->
    <section class="hero">
        <div class="hero-content">
            <div class="hero-text">
                <h1>装上这个 <span>Skill</span><br>解锁 AI 超能力</h1>
                <p class="hero-subtitle">本地 AI Skills 管理平台，轻松查看、管理和分享你的 AI 技能库</p>
                <div class="hero-stats">
                    <div class="hero-stat">
                        <div class="hero-stat-value" id="heroTotalSkills">-</div>
                        <div class="hero-stat-label">已安装 Skills</div>
                    </div>
                    <div class="hero-stat">
                        <div class="hero-stat-value" id="heroTotalSize">-</div>
                        <div class="hero-stat-label">总占用空间</div>
                    </div>
                </div>
            </div>
            <div class="hero-card">
                <div class="hero-card-title">🤖 <span id="cliBadge">Loading...</span></div>
                <div class="hero-card-content">
                    自动检测本地 AI CLI 环境<br>
                    支持 Claude Code、Gemini CLI 等<br>
                    一键管理所有 Skills
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

    <div class="toast" id="toast"></div>

    <script>
        let allSkills = [];
        let filteredSkills = [];
        let currentSkill = null;
        let skillToDelete = null;
        let currentFilter = 'all';

        // Load skills on page load
        document.addEventListener('DOMContentLoaded', loadSkills);

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
                const response = await fetch('/api/skills');
                const data = await response.json();
                allSkills = data.skills;
                filteredSkills = [...allSkills];

                document.getElementById('cliBadge').textContent = data.cli_client || 'AI CLI';
                updateStats();
                renderSkills(filteredSkills);
            } catch (error) {
                showToast('加载失败', 'error');
                console.error(error);
            }
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

            grid.innerHTML = skills.map(skill => `
                <div class="skill-card" onclick="showDetail('${skill.id}')">
                    <div class="skill-card-header">
                        <div class="skill-icon">${getSkillEmoji(skill.id)}</div>
                        <div class="skill-title-wrap">
                            <div class="skill-name">${escapeHtml(skill.name)}</div>
                            <span class="skill-version">${escapeHtml(skill.version || 'N/A')}</span>
                        </div>
                    </div>
                    <div class="skill-description">${escapeHtml(skill.description || '暂无描述')}</div>
                    <div class="skill-footer">
                        <div class="skill-source">
                            ${getSourceIcon(skill.source)} ${skill.source?.type || 'local'}
                        </div>
                        <div class="skill-actions" onclick="event.stopPropagation()">
                            <button class="btn btn-secondary" onclick="showDetail('${skill.id}')">详情</button>
                            <button class="btn btn-share" onclick="showShareModal('${skill.id}')">分享</button>
                            <button class="btn btn-danger" onclick="promptDelete('${skill.id}', '${escapeHtml(skill.name)}')">卸载</button>
                        </div>
                    </div>
                </div>
            `).join('');
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
                document.getElementById('detailBody').innerHTML = `
                    <div class="detail-section">
                        <h3>描述</h3>
                        <div class="detail-content">${escapeHtml(currentSkill.description || '暂无描述')}</div>
                    </div>
                    <div class="detail-section">
                        <h3>版本</h3>
                        <div class="detail-content">${escapeHtml(currentSkill.version || 'N/A')}</div>
                    </div>
                    <div class="detail-section">
                        <h3>来源</h3>
                        <div class="detail-content">
                            ${renderSourceDetail(currentSkill.source)}
                        </div>
                    </div>
                    <div class="detail-section">
                        <h3>位置</h3>
                        <div class="detail-content" style="font-family: monospace; font-size: 13px;">${escapeHtml(currentSkill.path)}</div>
                    </div>
                    <div class="detail-section">
                        <h3>文件 (${detail.file_count || 0})</h3>
                        <div class="detail-content">
                            <ul class="file-list">
                                ${(detail.files || []).slice(0, 20).map(f => `
                                    <li>
                                        <span>${escapeHtml(f.path)}</span>
                                        <span class="file-size">${formatSize(f.size)}</span>
                                    </li>
                                `).join('')}
                                ${(detail.files || []).length > 20 ? `<li style="color: #9ca3af; text-align: center;">... 还有 ${detail.files.length - 20} 个文件</li>` : ''}
                            </ul>
                        </div>
                    </div>
                    <div class="detail-section">
                        <h3>SKILL.md 内容</h3>
                        <div class="code-block">${escapeHtml(detail.content || 'No content')}</div>
                    </div>
                `;

                document.getElementById('detailModal').classList.add('active');
            } catch (error) {
                showToast('加载详情失败', 'error');
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

        // Close modals on overlay click
        document.querySelectorAll('.modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    overlay.classList.remove('active');
                }
            });
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeModal();
                closeConfirmModal();
                closeShareModal();
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

    desc = skill.get('description', '暂无描述')
    if desc:
        print(f"\n📝 描述:\n   {desc}")

    version = skill.get('version', 'N/A')
    print(f"\n📌 版本: {version}")

    print(f"📁 路径: {skill.get('path', 'N/A')}")
    print(f"📊 大小: {format_size_cli(skill.get('size', 0))}")

    if skill.get('has_scripts'):
        print("📜 包含 scripts: 是")

    # Source info
    source = skill.get('source', {})
    if source and source.get('type') != 'local':
        print(f"\n🔗 来源: {source.get('type', 'unknown').upper()}")
        url = source.get('url') or source.get('remote')
        if url:
            print(f"   URL: {url}")
        if source.get('author'):
            print(f"   作者: {source['author']}")
        if source.get('install_date'):
            print(f"   安装时间: {source['install_date']}")
    else:
        print(f"\n🔗 来源: Local (本地安装)")

    # Files list
    files = skill.get('files', [])
    if files:
        print(f"\n📂 文件列表 ({len(files)} 个):")
        for f in files[:10]:  # Show first 10 files
            print(f"   • {f.get('name', 'unknown')} ({format_size_cli(f.get('size', 0))})")
        if len(files) > 10:
            print(f"   ... 还有 {len(files) - 10} 个文件")

    print("=" * 60)


def generate_share_text(skill):
    """Generate installation prompt for sharing."""
    has_git_source = skill.get('source') and (skill.get('source', {}).get('url') or skill.get('source', {}).get('remote'))
    is_local = not has_git_source or skill.get('source', {}).get('type') == 'local'

    if is_local:
        return f"我想安装 \"{skill.get('name', skill['id'])}\" 这个 skill，请帮我使用 find-skills 查找并安装。"
    else:
        repo_url = skill.get('source', {}).get('url') or skill.get('source', {}).get('remote')
        skill_desc = skill.get('description', '一个实用的 AI CLI skill')
        skill_id = skill.get('id', 'skill-name')

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
            name = skill.get('name', skill['id'])[:20]
            version = (skill.get('version') or 'N/A')[:8]
            source_type = (skill.get('source', {}).get('type') or 'local')[:8]
            size = format_size_cli(skill.get('size', 0))
            print(f"{idx:<4} {name:<22} {version:<10} {source_type:<10} {size:<8}")

        print("-" * 70)
        print("\n操作: [数字] 查看详情 | [s数字] 分享 | [d数字] 卸载 | [q] 退出")
        print("示例: 1 (查看#1详情) | s1 (分享#1) | d1 (卸载#1)")

        try:
            choice = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n\nbye!")
            break

        if choice == 'q' or choice == 'quit':
            print("\nbye!")
            break

        # Parse command
        if choice.startswith('s'):  # Share
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

        elif choice.startswith('d'):  # Delete/Uninstall
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(skills):
                    skill = skills[idx]
                    print(f"\n⚠️  确认卸载 \"{skill.get('name', skill['id'])}\"?")
                    confirm = input("输入 'yes' 确认卸载: ").strip().lower()
                    if confirm == 'yes':
                        skill_path = Path(skills_dir) / skill['id']
                        if skill_path.exists():
                            shutil.rmtree(skill_path)
                            print(f"✅ \"{skill.get('name', skill['id'])}\" 已卸载")
                            # Refresh skills list
                            skills = [s for s in skills if s['id'] != skill['id']]
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
        name = skill.get('name', skill['id'])[:18]
        version = (skill.get('version') or 'N/A')[:8]
        source_type = (skill.get('source', {}).get('type') or 'local')[:10]
        size = format_size_cli(skill.get('size', 0))
        desc = (skill.get('description') or 'No description')[:40]

        print(f"{name:<20} {version:<10} {source_type:<12} {size:<8} {desc}")

    print("-" * 100)

    # Print source details section
    git_skills = [s for s in skills if s.get('source', {}).get('type') not in (None, 'local')]
    if git_skills:
        print("\n📋 Git Repository Sources:\n")
        for skill in git_skills:
            source = skill.get('source', {})
            url = source.get('url') or source.get('remote') or 'N/A'
            author = source.get('author') or 'Unknown'
            print(f"  • {skill.get('name', skill['id'])}")
            print(f"    URL: {url}")
            print(f"    Author: {author}")
            if source.get('install_date'):
                print(f"    Installed: {source['install_date']}")
            print()


def main():
    # Check for CLI mode flags
    cli_mode = False
    simple_mode = False
    args = sys.argv[1:]

    if '--cli' in args or '--list' in args or '-l' in args:
        cli_mode = True
        # Remove the flag from args
        args = [a for a in args if a not in ('--cli', '--list', '-l')]

    if '--simple' in args or '-s' in args:
        simple_mode = True
        args = [a for a in args if a not in ('--simple', '-s')]

    if len(args) < 1:
        print("Usage: server.py <skills_dir> [cli_client] [--cli|--list|-l] [--simple|-s]")
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
