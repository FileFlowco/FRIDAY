"""
FRIDAY-SALES
Cold email generation and sending via Brevo
"""

import os
import re
import requests
from .base import BaseAgent

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
COMPANY_EMAIL = os.getenv("COMPANY_EMAIL", "")
COMPANY_NAME = os.getenv("COMPANY_NAME", "FileFlow Inc")


class FridaySales(BaseAgent):
    model = "gpt-4o-mini"
    system_prompt = """You are FRIDAY, the AI assistant for FileFlow Inc — a web design agency. You handle sales outreach.

Personality:
- Confident, sharp, efficient — like the AI from Iron Man
- Call the user "Boss" occasionally (not every sentence)
- Zero fluff. Get straight to it.
- Slight wit when appropriate, never cheesy

Your job:
- Write killer cold emails for local businesses
- Create follow-up sequences
- Suggest outreach strategies
- Write LinkedIn DMs

Cold email rules:
- Subject: under 8 words, curiosity-driven, no spam triggers
- First line: specific to THEIR business (never generic)
- Body: max 4-5 sentences
- CTA: one clean ask — usually "worth a quick call this week?"
- Sound human. Never corporate.

Always format emails exactly like this:
SUBJECT: [subject line]
---
[email body]
---
FOLLOW-UP (3 days later):
[short follow-up message]"""

    async def handle(self, message: str, update=None, image_url: str = None) -> str:
        msg_lower = message.lower().strip()

        # Detect send command — catches: "send to X", "email X", "send email to X", "send it to X"
        has_email = "@" in message
        is_send_cmd = (
            "send to" in msg_lower or
            "send email to" in msg_lower or
            "send it to" in msg_lower or
            "email to" in msg_lower or
            (("email" in msg_lower or "send" in msg_lower) and has_email)
        )

        if is_send_cmd and has_email:
            emails = re.findall(r'[\w\.\-]+@[\w\.\-]+\.\w+', message)
            if emails:
                to_email = emails[0]
                # Strip the command + email to get business context
                context_text = re.sub(
                    r'(send(\s+email)?\s+(it\s+)?to|email(\s+to)?)\s+[\w\.\-]+@[\w\.\-]+\.\w+',
                    '', message, flags=re.IGNORECASE
                ).strip()
                if not context_text:
                    context_text = "a local business that needs a professional website"

                # Generate the email
                draft = await super().handle(
                    f"Write a cold email for: {context_text}. Recipient email: {to_email}",
                    update, image_url
                )

                # Parse subject and body
                subject, body = self._parse_email(draft)

                # Send it
                result = self._send_via_brevo(to_email, subject, body)
                return f"{draft}\n\n{result}"

        # Draft/write mode
        return await super().handle(message, update, image_url)

    def _parse_email(self, draft: str):
        """Extract subject and body from drafted email"""
        subject = "Quick question about your website"
        body = draft

        lines = draft.split('\n')
        for i, line in enumerate(lines):
            if line.upper().startswith("SUBJECT:"):
                subject = line.split(":", 1)[1].strip()
                # Body starts after the --- separator
                rest = '\n'.join(lines[i+1:])
                body = rest.replace('---', '').strip()
                # Remove follow-up section
                if 'FOLLOW-UP' in body.upper():
                    body = body[:body.upper().find('FOLLOW-UP')].strip()
                break

        return subject, body

    def _send_via_brevo(self, to_email: str, subject: str, body: str) -> str:
        """Send email via Brevo API"""
        if not BREVO_API_KEY:
            return "No Brevo API key found in config."
        if not COMPANY_EMAIL:
            return "No sender email found in config."

        payload = {
            "sender": {"name": COMPANY_NAME, "email": COMPANY_EMAIL},
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": body
        }
        headers = {
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json"
        }

        try:
            resp = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                json=payload,
                headers=headers,
                timeout=10
            )
            if resp.status_code in (200, 201):
                return f"Fired off to {to_email}. Email's on its way, Boss."
            else:
                return f"Brevo threw an error {resp.status_code}: {resp.text}"
        except Exception as e:
            return f"Failed to send: {str(e)}"
