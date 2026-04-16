"""
FRIDAY-LEAD
Real lead generation powered by Leadforge + Google Places API
"""

import os
import sys
import json
from datetime import datetime
from .base import BaseAgent

# Point to leadforge
LEADFORGE_PATH = os.path.expanduser("~/Documents/leadforge/app")
LEADS_DIR = os.path.expanduser("~/Documents/FRIDAY/leads")

# Add leadforge to path
if LEADFORGE_PATH not in sys.path:
    sys.path.insert(0, LEADFORGE_PATH)

# Set Google Places API key for leadforge
os.environ["GOOGLE_PLACES_API_KEY"] = os.getenv("GOOGLE_PLACES_API_KEY", "")


class FridayLead(BaseAgent):
    model = "gpt-4o-mini"
    system_prompt = """You are FRIDAY, the AI assistant for FileFlow Inc. You find leads.

Personality:
- Sharp, efficient, hunter mentality — like the AI from Iron Man
- Call the user "Boss" occasionally
- Lead with the best prospects first
- Be specific about why each business is a good target

When given a niche and city, find real local businesses that need web design.
Focus on: no website, outdated site, weak online presence.

After finding leads, format them clearly and suggest the best outreach for each one."""

    async def handle(self, message: str, update=None, image_url: str = None) -> str:
        # Try to extract niche and location from message
        niche, location, count = self._parse_request(message)

        if niche and location:
            return await self._find_real_leads(niche, location, count, message)
        else:
            return await super().handle(
                f"The user said: '{message}'. Ask them to specify a niche and city, "
                f"e.g. 'restaurants in Miami' or 'barbers in New York'. "
                f"Also suggest 3 good niches to target for web design clients.",
                update, image_url
            )

    def _parse_request(self, message: str):
        """Extract niche, location, count from message"""
        import re
        msg = message.lower()

        # Try to find "X in Y" pattern
        match = re.search(r'(.+?)\s+in\s+(.+?)(?:\s+(\d+))?$', msg)
        if match:
            niche = match.group(1).strip()
            location = match.group(2).strip()
            count = int(match.group(3)) if match.group(3) else 10
            return niche, location, min(count, 20)

        return None, None, 10

    async def _find_real_leads(self, niche: str, location: str, count: int, original: str) -> str:
        try:
            from leadforge.providers import places
            from leadforge.core.enrich import enrich

            await self._send_status(f"Searching for {niche} in {location}...")

            # Search Google Places
            results = places.search(niche, location, count)

            if not results:
                return f"No results found for '{niche} in {location}'. Try a broader search like 'restaurants in Miami'."

            await self._send_status(f"Found {len(results)} businesses. Analyzing websites...")

            # Enrich with details
            leads = enrich(results, places, count)

            if not leads:
                return f"Found businesses but none matched the criteria (no website or weak site). Try a different niche."

            # Save to file
            os.makedirs(LEADS_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(LEADS_DIR, f"leads_{niche}_{location}_{timestamp}.json")
            with open(filename, 'w') as f:
                json.dump(leads, f, indent=2)

            # Format response
            response = f"LEADS: {niche.title()} in {location.title()}\n"
            response += f"Found {len(leads)} prospects\n"
            response += f"Saved to: FRIDAY/leads/\n\n"
            response += "=" * 30 + "\n\n"

            for i, lead in enumerate(leads[:10], 1):
                name = lead.get("Business Name", "Unknown")
                phone = lead.get("Phone", "No phone")
                email = lead.get("Email", "No email found")
                website = lead.get("Website", "NO WEBSITE")
                insight = lead.get("Website Insight", "")
                contact = lead.get("Best Contact", "Email")

                response += f"{i}. {name}\n"
                if website and website != "NO WEBSITE":
                    response += f"   Website: {website}\n"
                else:
                    response += f"   ⚠️ NO WEBSITE — hot lead\n"
                if phone != "No phone":
                    response += f"   Phone: {phone}\n"
                if email != "No email found":
                    response += f"   Email: {email}\n"
                if insight:
                    response += f"   Why: {insight}\n"
                response += f"   Best: {contact}\n\n"

            response += f"\nTo send cold emails to these leads, tap Sales and say:\n"
            response += f"'send to [email] for a [niche] business'"

            return response

        except ImportError as e:
            return await self._fallback(niche, location, count, str(e))
        except Exception as e:
            return await self._fallback(niche, location, count, str(e))

    async def _send_status(self, msg: str):
        """Log status updates"""
        print(f"[FRIDAY-LEAD] {msg}")

    async def _fallback(self, niche: str, location: str, count: int, error: str) -> str:
        """Fallback to GPT if leadforge fails"""
        prompt = (
            f"Generate a realistic lead list of {count} {niche} businesses in {location} "
            f"that likely need web design services. For each include: business name, "
            f"why they need a website, best contact method, and a personalized opening line "
            f"for a cold email. Format clearly and be specific."
        )
        result = await super().handle(prompt)
        return f"(Using AI generation — Google Places unavailable: {error})\n\n{result}"
