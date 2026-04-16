"""
FRIDAY-PM (Project Manager)
Tracks projects, deadlines, client status
"""

import os
import json
from datetime import datetime
from .base import BaseAgent

LEADS_DIR = os.path.expanduser("~/Documents/FRIDAY/leads")
PROJECTS_FILE = os.path.expanduser("~/Documents/FRIDAY/logs/projects.json")


class FridayPM(BaseAgent):
    provider   = "openai"
    model      = "gpt-4o"
    max_tokens = 4096
    system_prompt = """You are FRIDAY, the AI assistant for FileFlow Inc. You keep projects on track.

Personality:
- Precise, organized, proactive — like the AI from Iron Man
- Call the user "Boss" occasionally
- Lead with what matters most: what's overdue, what's at risk
- Be direct about problems, don't soften bad news

Your job:
- Track active projects and their status
- Set and monitor deadlines
- Summarize what's pending and what's overdue
- Create project plans for new clients
- Flag anything at risk before it becomes a problem

Project plan format:
PROJECT: [Client Name]
Start: [date]
Deadline: [date]
Budget: [amount]

MILESTONES:
Day 1-2: Discovery and wireframe
Day 3-5: Design and build
Day 6: Client review
Day 7: Revisions and launch

STATUS: [Not started / In progress / In review / Complete]
NOTES: [anything important]

When asked for a status update, lead with: what's overdue, what's due soon, what's on track.
End every response with what needs attention next."""

    async def handle(self, message: str, update=None, image_url: str = None, history=None) -> str:
        # Load existing projects if any
        projects_context = self._load_projects()
        if projects_context:
            message = f"Current projects data:\n{projects_context}\n\nUser request: {message}"

        response = await super().handle(message, update, image_url, history=history)

        # Save any new project info mentioned
        self._save_project_update(response)

        return response

    def _load_projects(self) -> str:
        if os.path.exists(PROJECTS_FILE):
            with open(PROJECTS_FILE, 'r') as f:
                data = json.load(f)
                return json.dumps(data, indent=2)
        return ""

    def _save_project_update(self, response: str):
        os.makedirs(os.path.dirname(PROJECTS_FILE), exist_ok=True)
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "update": response[:200]
        }
        logs = []
        if os.path.exists(PROJECTS_FILE):
            with open(PROJECTS_FILE, 'r') as f:
                try:
                    logs = json.load(f)
                except Exception:
                    logs = []
        logs.append(log_entry)
        with open(PROJECTS_FILE, 'w') as f:
            json.dump(logs[-50:], f, indent=2)
