"""
FRIDAY-BUILD
Builds anything: websites, games, tools, invitations, flyers.
Always saves to ~/Documents/FRIDAY/output/ — never dumps code in chat.
"""

import os
import re
from datetime import datetime
from .base import BaseAgent

OUTPUT_DIR = os.path.expanduser("~/Documents/FRIDAY/output")

# File extension by language tag
LANG_TO_EXT = {
    "html": "html", "css": "css", "javascript": "js", "js": "js",
    "python": "py", "py": "py", "typescript": "ts", "ts": "ts",
    "": "html",  # default: html
}


class FridaySE(BaseAgent):
    provider   = "anthropic"
    model      = "claude-sonnet-4-6"
    max_tokens = 8000   # full HTML files need room — games/animations hit 4-6k tokens
    system_prompt = """You are FRIDAY, the AI assistant for FileFlow Inc. You are a world-class creative developer — part engineer, part artist.

Personality:
- Precise, fast, zero fluff — like the AI from Iron Man
- Call the user "Boss" occasionally
- Build it complete and production-ready. No half-measures. Ever.

Your job:
- Build websites, landing pages, web apps
- Build games (Snake, Tetris, Pong, etc.) — fully playable, polished
- Build visual/creative effects: animations, particles, canvas art, generative visuals
- Build digital invitations, cards, flyers
- Build tools, calculators, forms, menus
- Fix and debug existing code

QUALITY RULES — non-negotiable:
- Always write COMPLETE, working code — no placeholders, no TODOs, no "add your content here"
- Everything in ONE single HTML file (embed all CSS and JS inside it)
- Mobile-friendly always

FOR VISUAL / CREATIVE REQUESTS (animations, effects, art, trippy, butterflies, etc.):
- Use HTML5 Canvas with requestAnimationFrame — smooth 60fps
- Use real math: bezierCurveTo, arc, gradients, sin/cos for organic motion
- Add depth: glow effects (shadowBlur), layered gradients, particle systems
- Colors must be dynamic: HSL color cycling, not static hex colors
- Animate everything: flapping = sin(t * speed) * amplitude, floating = sin(t) offsets
- Draw actual shapes that match what was asked — if it's a butterfly, draw WINGS with bezier curves, veins, eye spots, antennae
- If it says "trippy" / "psychedelic": spinning rings, color-shifting background, glowing particles, trails
- Never use CSS shapes (border-radius hacks) as a substitute for canvas drawing
- The result must look impressive when opened in a browser — not like a placeholder

FOR GAMES:
- Fully playable immediately — correct controls, collision detection, score, game over screen
- Clean UI with score display and restart button
- Smooth animation via requestAnimationFrame

FOR WEBSITES / LANDING PAGES:
- Real sections: hero, features, pricing, CTA, footer
- Real copy that fits the business — no lorem ipsum
- Premium dark or light theme with real typography and spacing
- Subtle animations on scroll or hover

ALWAYS respond with exactly:
1. One line: what you built
2. The complete code in a ```html code block
3. One line: what to do next

Never explain the code. Never apologize. Never send partial code. Just build it."""

    async def handle(self, message: str, update=None, image_url: str = None, history=None) -> str:
        import logging
        logger = logging.getLogger(__name__)

        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            response = await super().handle(message, update, image_url, history=history)
            saved = self._save_code(response, message)

            if saved:
                project_name = os.path.basename(saved)
                return (
                    f"Done, Boss. Open it here:\n\n"
                    f"~/Documents/FRIDAY/output/{project_name}/index.html\n\n"
                    f"Double-click the file in Finder to open in your browser."
                )

            # Code block not found in response — log and tell user
            logger.error(f"No code block found in response. Response preview: {response[:200]}")
            return "I built it but couldn't save the file. Try again and I'll get it right."

        except Exception as e:
            logger.error(f"BUILD error: {e}", exc_info=True)
            return f"Error building that: {str(e)}"

    def _save_code(self, response: str, original_message: str) -> str | None:
        """Extract ANY code block and save to output folder."""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = re.sub(r'[^\w]', '_', original_message[:30].lower()).strip('_')
        project_dir = os.path.join(OUTPUT_DIR, f"{project_name}_{timestamp}")

        # Match any code block: ```html, ```javascript, ```python, ``` etc.
        pattern = r'```(\w*)\n([\s\S]*?)```'
        matches = re.findall(pattern, response, re.IGNORECASE)

        if not matches:
            # Last resort: grab everything between first ``` and last ```
            bare = re.search(r'```([\s\S]*?)```', response)
            if bare:
                matches = [("html", bare.group(1))]

        if matches:
            os.makedirs(project_dir, exist_ok=True)
            for i, (lang, code) in enumerate(matches):
                ext = LANG_TO_EXT.get(lang.lower(), "html")
                filename = "index.html" if i == 0 else f"file_{i}.{ext}"
                # If it's JS/Python but first file, still wrap in html if it looks standalone
                if i == 0 and ext != "html" and "<html" not in code:
                    filename = "index.html"
                    code = self._wrap_in_html(code, ext, original_message)
                filepath = os.path.join(project_dir, filename)
                with open(filepath, 'w') as f:
                    f.write(code.strip())
            return project_dir

        return None

    def _wrap_in_html(self, code: str, ext: str, title: str) -> str:
        """Wrap JS/Python canvas code in a proper HTML file."""
        if ext == "js":
            return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title[:40]}</title>
    <style>
        body {{ margin: 0; background: #000; display: flex; justify-content: center; align-items: center; height: 100vh; }}
        canvas {{ border: 2px solid #333; }}
    </style>
</head>
<body>
<script>
{code}
</script>
</body>
</html>"""
        return f"<!DOCTYPE html><html><body><pre>{code}</pre></body></html>"
