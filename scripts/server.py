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
        self.skills.sort(key=lambda x: x['name'].lower())
        return self.skills

    def _parse_skill_md(self, skill_path: Path, skill_md: Path) -> dict:
        """Parse a SKILL.md file to extract metadata."""
        try:
            content = skill_md.read_text(encoding='utf-8')

            # Extract frontmatter
            frontmatter = {}
            fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if fm_match:
                fm_content = fm_match.group(1)
                # Parse YAML-like frontmatter
                for line in fm_content.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        # Handle multiline values (|)
                        if value == '|':
                            continue
                        frontmatter[key] = value

            # Get description (either from frontmatter or first paragraph)
            description = frontmatter.get('description', '')
            if not description:
                # Try to get first paragraph after frontmatter
                body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL).strip()
                paragraphs = [p.strip() for p in body.split('\n\n') if p.strip()]
                if paragraphs:
                    description = paragraphs[0][:200]

            # Clean up description (remove newlines, extra spaces)
            description = ' '.join(description.split())

            return {
                'id': skill_path.name,
                'name': frontmatter.get('name', skill_path.name),
                'description': description,
                'version': frontmatter.get('version', 'N/A'),
                'path': str(skill_path),
                'cli_client': self.cli_client,
                'has_scripts': (skill_path / 'scripts').exists(),
                'size': self._get_dir_size(skill_path)
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
            content = skill_md.read_text(encoding='utf-8')

            # Get file structure
            files = []
            for root, dirs, filenames in os.walk(skill_path):
                # Skip node_modules and hidden dirs
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
                for filename in filenames:
                    if filename.startswith('.'):
                        continue
                    file_path = Path(root) / filename
                    rel_path = file_path.relative_to(skill_path)
                    files.append({
                        'path': str(rel_path),
                        'size': file_path.stat().st_size
                    })

            return {
                'id': skill_id,
                'content': content,
                'files': files,
                'file_count': len(files)
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
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_html(self, content, status=200):
        """Send HTML response."""
        self.send_response(status)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(content.encode())

    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == '/' or path == '/index.html':
            self._send_html(HTML_TEMPLATE)

        elif path == '/api/skills':
            skills = self.skill_manager.scan_skills()
            self._send_json({'skills': skills, 'cli_client': self.skill_manager.cli_client})

        elif path.startswith('/api/skills/'):
            skill_id = path.split('/')[-1]
            detail = self.skill_manager.get_skill_detail(skill_id)
            if detail:
                self._send_json(detail)
            else:
                self._send_json({'error': 'Skill not found'}, 404)

        else:
            self._send_json({'error': 'Not found'}, 404)

    def do_DELETE(self):
        """Handle DELETE requests."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path.startswith('/api/skills/'):
            skill_id = path.split('/')[-1]
            if self.skill_manager.delete_skill(skill_id):
                self._send_json({'success': True})
            else:
                self._send_json({'error': 'Failed to delete skill'}, 500)
        else:
            self._send_json({'error': 'Not found'}, 404)

    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


# HTML Template for the dashboard
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Skill Manager</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 20px;
            border-radius: 12px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        header h1 {
            font-size: 2rem;
            margin-bottom: 8px;
        }

        header .subtitle {
            opacity: 0.9;
            font-size: 0.95rem;
        }

        .controls {
            display: flex;
            gap: 15px;
            margin-bottom: 25px;
            flex-wrap: wrap;
        }

        .search-box {
            flex: 1;
            min-width: 250px;
            position: relative;
        }

        .search-box input {
            width: 100%;
            padding: 12px 16px 12px 42px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1rem;
            transition: border-color 0.2s;
        }

        .search-box input:focus {
            outline: none;
            border-color: #667eea;
        }

        .search-box::before {
            content: "🔍";
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 1.1rem;
        }

        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .btn-primary {
            background: #667eea;
            color: white;
        }

        .btn-primary:hover {
            background: #5568d3;
        }

        .btn-danger {
            background: #ef4444;
            color: white;
        }

        .btn-danger:hover {
            background: #dc2626;
        }

        .btn-secondary {
            background: #e5e7eb;
            color: #374151;
        }

        .btn-secondary:hover {
            background: #d1d5db;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }

        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }

        .stat-card .number {
            font-size: 2rem;
            font-weight: bold;
            color: #667eea;
        }

        .stat-card .label {
            color: #666;
            font-size: 0.9rem;
        }

        .skills-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }

        .skill-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            transition: transform 0.2s, box-shadow 0.2s;
            cursor: pointer;
        }

        .skill-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.12);
        }

        .skill-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
        }

        .skill-name {
            font-size: 1.2rem;
            font-weight: 600;
            color: #1a1a1a;
            word-break: break-word;
        }

        .skill-version {
            background: #f3f4f6;
            color: #6b7280;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            white-space: nowrap;
        }

        .skill-description {
            color: #4b5563;
            font-size: 0.9rem;
            line-height: 1.5;
            margin-bottom: 15px;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .skill-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.8rem;
            color: #9ca3af;
        }

        .skill-actions {
            display: flex;
            gap: 8px;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #f3f4f6;
        }

        .skill-actions button {
            flex: 1;
            padding: 8px 12px;
            font-size: 0.85rem;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #9ca3af;
        }

        .empty-state-icon {
            font-size: 4rem;
            margin-bottom: 20px;
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
        }

        .modal-overlay.active {
            display: flex;
        }

        .modal {
            background: white;
            border-radius: 12px;
            max-width: 800px;
            width: 100%;
            max-height: 90vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        .modal-header {
            padding: 20px;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .modal-title {
            font-size: 1.3rem;
            font-weight: 600;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: #9ca3af;
        }

        .modal-close:hover {
            color: #374151;
        }

        .modal-body {
            padding: 20px;
            overflow-y: auto;
            flex: 1;
        }

        .modal-footer {
            padding: 20px;
            border-top: 1px solid #e5e7eb;
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }

        .detail-section {
            margin-bottom: 20px;
        }

        .detail-section h3 {
            font-size: 0.85rem;
            text-transform: uppercase;
            color: #9ca3af;
            margin-bottom: 8px;
            letter-spacing: 0.5px;
        }

        .detail-content {
            background: #f9fafb;
            padding: 15px;
            border-radius: 8px;
            font-size: 0.9rem;
        }

        .code-block {
            background: #1f2937;
            color: #e5e7eb;
            padding: 15px;
            border-radius: 8px;
            overflow-x: auto;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.85rem;
            line-height: 1.5;
            max-height: 400px;
            overflow-y: auto;
            white-space: pre-wrap;
        }

        .file-list {
            list-style: none;
        }

        .file-list li {
            padding: 6px 0;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            justify-content: space-between;
        }

        .file-list li:last-child {
            border-bottom: none;
        }

        .file-size {
            color: #9ca3af;
            font-size: 0.8rem;
        }

        .confirm-dialog {
            text-align: center;
            padding: 20px;
        }

        .confirm-dialog p {
            margin-bottom: 20px;
            font-size: 1.1rem;
        }

        .confirm-dialog .skill-name-highlight {
            font-weight: 600;
            color: #ef4444;
        }

        .toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #1f2937;
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transform: translateX(150%);
            transition: transform 0.3s;
            z-index: 2000;
        }

        .toast.show {
            transform: translateX(0);
        }

        .toast.success {
            background: #10b981;
        }

        .toast.error {
            background: #ef4444;
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

        @media (max-width: 640px) {
            .skills-grid {
                grid-template-columns: 1fr;
            }

            header h1 {
                font-size: 1.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎯 Skill Manager <span class="cli-badge" id="cliBadge">Loading...</span></h1>
            <div class="subtitle">Manage your AI CLI skills</div>
        </header>

        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="number" id="totalSkills">-</div>
                <div class="label">Total Skills</div>
            </div>
            <div class="stat-card">
                <div class="number" id="totalSize">-</div>
                <div class="label">Total Size</div>
            </div>
        </div>

        <div class="controls">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="Search skills by name or description...">
            </div>
            <button class="btn btn-primary" onclick="refreshSkills()">
                🔄 Refresh
            </button>
        </div>

        <div class="skills-grid" id="skillsGrid">
            <div class="empty-state">
                <div class="empty-state-icon">📦</div>
                <h3>Loading skills...</h3>
            </div>
        </div>
    </div>

    <!-- Detail Modal -->
    <div class="modal-overlay" id="detailModal">
        <div class="modal">
            <div class="modal-header">
                <div class="modal-title" id="detailTitle">Skill Details</div>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="detailBody">
                <!-- Content injected here -->
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeModal()">Close</button>
                <button class="btn btn-danger" onclick="confirmDelete()">🗑️ Uninstall</button>
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

    <div class="toast" id="toast"></div>

    <script>
        let allSkills = [];
        let currentSkill = null;
        let skillToDelete = null;

        // Load skills on page load
        document.addEventListener('DOMContentLoaded', loadSkills);

        // Search functionality
        document.getElementById('searchInput').addEventListener('input', (e) => {
            filterSkills(e.target.value);
        });

        async function loadSkills() {
            try {
                const response = await fetch('/api/skills');
                const data = await response.json();
                allSkills = data.skills;

                document.getElementById('cliBadge').textContent = data.cli_client || 'Unknown CLI';
                updateStats();
                renderSkills(allSkills);
            } catch (error) {
                showToast('Failed to load skills', 'error');
                console.error(error);
            }
        }

        function updateStats() {
            document.getElementById('totalSkills').textContent = allSkills.length;

            const totalBytes = allSkills.reduce((sum, s) => sum + (s.size || 0), 0);
            document.getElementById('totalSize').textContent = formatSize(totalBytes);
        }

        function formatSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }

        function renderSkills(skills) {
            const grid = document.getElementById('skillsGrid');

            if (skills.length === 0) {
                grid.innerHTML = `
                    <div class="empty-state" style="grid-column: 1/-1;">
                        <div class="empty-state-icon">🔍</div>
                        <h3>No skills found</h3>
                        <p>Try adjusting your search</p>
                    </div>
                `;
                return;
            }

            grid.innerHTML = skills.map(skill => `
                <div class="skill-card" onclick="showDetail('${skill.id}')">
                    <div class="skill-header">
                        <div class="skill-name">${escapeHtml(skill.name)}</div>
                        <span class="skill-version">${escapeHtml(skill.version || 'N/A')}</span>
                    </div>
                    <div class="skill-description">${escapeHtml(skill.description || 'No description')}</div>
                    <div class="skill-meta">
                        <span>${formatSize(skill.size || 0)}</span>
                        <span>${skill.has_scripts ? '📜 Has scripts' : ''}</span>
                    </div>
                    <div class="skill-actions" onclick="event.stopPropagation()">
                        <button class="btn btn-primary" onclick="showDetail('${skill.id}')">
                            👁️ View
                        </button>
                        <button class="btn btn-danger" onclick="promptDelete('${skill.id}', '${escapeHtml(skill.name)}')">
                            🗑️ Uninstall
                        </button>
                    </div>
                </div>
            `).join('');
        }

        function filterSkills(query) {
            const lowerQuery = query.toLowerCase();
            const filtered = allSkills.filter(skill =>
                skill.name.toLowerCase().includes(lowerQuery) ||
                (skill.description && skill.description.toLowerCase().includes(lowerQuery))
            );
            renderSkills(filtered);
        }

        function refreshSkills() {
            const btn = document.querySelector('.btn-primary');
            btn.innerHTML = '<span class="loading"></span> Refreshing...';

            loadSkills().then(() => {
                btn.innerHTML = '🔄 Refresh';
                showToast('Skills refreshed', 'success');
            }).catch(() => {
                btn.innerHTML = '🔄 Refresh';
            });
        }

        async function showDetail(skillId) {
            currentSkill = allSkills.find(s => s.id === skillId);
            if (!currentSkill) return;

            try {
                const response = await fetch(`/api/skills/${skillId}`);
                const detail = await response.json();

                document.getElementById('detailTitle').textContent = currentSkill.name;
                document.getElementById('detailBody').innerHTML = `
                    <div class="detail-section">
                        <h3>Description</h3>
                        <div class="detail-content">${escapeHtml(currentSkill.description || 'No description')}</div>
                    </div>
                    <div class="detail-section">
                        <h3>Version</h3>
                        <div class="detail-content">${escapeHtml(currentSkill.version || 'N/A')}</div>
                    </div>
                    <div class="detail-section">
                        <h3>Location</h3>
                        <div class="detail-content" style="font-family: monospace; font-size: 0.85rem;">${escapeHtml(currentSkill.path)}</div>
                    </div>
                    <div class="detail-section">
                        <h3>Files (${detail.file_count || 0})</h3>
                        <div class="detail-content">
                            <ul class="file-list">
                                ${(detail.files || []).slice(0, 20).map(f => `
                                    <li>
                                        <span>${escapeHtml(f.path)}</span>
                                        <span class="file-size">${formatSize(f.size)}</span>
                                    </li>
                                `).join('')}
                                ${(detail.files || []).length > 20 ? `<li style="color: #9ca3af; text-align: center;">... and ${detail.files.length - 20} more files</li>` : ''}
                            </ul>
                        </div>
                    </div>
                    <div class="detail-section">
                        <h3>SKILL.md Content</h3>
                        <div class="code-block">${escapeHtml(detail.content || 'No content')}</div>
                    </div>
                `;

                document.getElementById('detailModal').classList.add('active');
            } catch (error) {
                showToast('Failed to load skill details', 'error');
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
            }
        });
    </script>
</body>
</html>
'''


def find_available_port(start_port=DEFAULT_PORT, max_attempts=MAX_PORT_ATTEMPTS):
    """Find an available port."""
    import socket

    for port in range(start_port, start_port + max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', port))
            sock.close()
            return port
        except OSError:
            continue

    raise RuntimeError(f"Could not find an available port in range {start_port}-{start_port + max_attempts}")


def open_browser(url, delay=1.0):
    """Open browser after a short delay to ensure server is ready."""
    def _open():
        webbrowser.open(url)
    Timer(delay, _open).start()


def main():
    if len(sys.argv) < 2:
        print("Usage: server.py <skills_dir> [cli_client]")
        sys.exit(1)

    skills_dir = sys.argv[1]
    cli_client = sys.argv[2] if len(sys.argv) > 2 else "unknown"

    # Verify skills directory exists
    if not os.path.exists(skills_dir):
        print(f"Error: Skills directory not found: {skills_dir}")
        sys.exit(1)

    # Create skill manager
    skill_manager = SkillManager(skills_dir, cli_client)

    # Find available port
    port = find_available_port()

    # Set up request handler
    RequestHandler.skill_manager = skill_manager

    # Create server
    server = HTTPServer(('127.0.0.1', port), RequestHandler)

    url = f"http://127.0.0.1:{port}"
    print(f"\n🎯 Skill Manager running at: {url}")
    print(f"   CLI Client: {cli_client}")
    print(f"   Skills Directory: {skills_dir}")
    print("\nPress Ctrl+C to stop the server\n")

    # Open browser
    open_browser(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
