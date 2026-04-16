"""
FRIDAY-IMAGE
AI image generation via DALL-E 3.
Generates mockups, social media graphics, logos, visuals.
Saves to ~/Documents/FRIDAY/output/images/ — delivers via Telegram photo & web download.
"""

import os
import re
import asyncio
import requests
from datetime import datetime
from .base import BaseAgent

IMAGES_DIR = os.path.expanduser("~/Documents/FRIDAY/output/images")


class FridayImage(BaseAgent):
    provider   = "openai"
    model      = "gpt-4o-mini"
    max_tokens = 512

    system_prompt = """You are FRIDAY, the AI assistant for FileFlow Inc.
You are the creative visual AI — you generate images using DALL-E 3.

Personality: concise, confident, call the user "Boss" occasionally.

Your job:
- Generate social media graphics, mockups, logos, banners, flyers
- Generate website hero images, backgrounds, product visuals
- Generate brand assets: icons, thumbnails, covers
- Generate any creative visual the user asks for

When asked to generate an image, respond ONLY with:
PROMPT: [the optimized DALL-E 3 prompt — detailed, specific, professional quality]
STYLE: [photorealistic / illustration / 3D render / flat design / etc.]
SIZE: [1024x1024 / 1792x1024 / 1024x1792]

Nothing else. No extra commentary."""

    # ── Main handler ──────────────────────────────────────────────────────────

    async def handle(self, message: str, update=None, image_url: str = None, history=None) -> str:
        msg_lower = message.lower().strip()

        # Check if this is an image generation request
        gen_triggers = [
            "generate", "create", "make", "design", "draw", "produce",
            "image", "graphic", "logo", "banner", "mockup", "visual",
            "photo", "picture", "illustration", "thumbnail", "cover",
            "flyer", "poster", "background", "icon", "avatar",
        ]
        is_gen = any(t in msg_lower for t in gen_triggers)

        if not is_gen:
            # Just chat about image capabilities
            return await super().handle(message, update, image_url, history=history)

        # Generate the optimized prompt via LLM
        prompt_response = await super().handle(message, update, image_url, history=history)

        # Parse the structured response
        dalle_prompt, style, size = self._parse_generation_params(prompt_response, message)

        # Call DALL-E 3
        return await self._generate_image(dalle_prompt, style, size, message)

    # ── DALL-E 3 caller ───────────────────────────────────────────────────────

    async def _generate_image(self, prompt: str, style: str, size: str, original: str) -> str:
        try:
            # Enhance prompt for quality
            quality_prompt = (
                f"{prompt}. "
                f"Ultra high quality, professional, sharp details, "
                f"suitable for commercial use."
            )

            response = await asyncio.to_thread(
                self.openai_client.images.generate,
                model="dall-e-3",
                prompt=quality_prompt[:4000],
                size=size,
                quality="hd",
                n=1,
            )

            image_url = response.data[0].url
            revised   = response.data[0].revised_prompt or prompt

            # Download and save the image
            saved_path = await asyncio.to_thread(self._download_image, image_url, original)

            if saved_path:
                fname    = os.path.basename(saved_path)
                reply    = (
                    f"Generated, Boss.\n\n"
                    f"Style: {style}\n"
                    f"Size: {size}\n\n"
                    f"[IMAGE:{saved_path}|{fname}]"
                )
                return reply
            else:
                return f"Generated but couldn't save. Direct URL:\n{image_url}"

        except Exception as e:
            err = str(e)
            if "content_policy" in err.lower() or "safety" in err.lower():
                return (
                    "That image couldn't be generated due to content policy, Boss.\n"
                    "Try rephrasing — avoid anything too specific about real people or brands."
                )
            return f"Image generation failed: {err}"

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _parse_generation_params(self, response: str, fallback: str):
        prompt = fallback
        style  = "photorealistic"
        size   = "1024x1024"

        lines = response.split('\n')
        for line in lines:
            if line.startswith("PROMPT:"):
                prompt = line.split(":", 1)[1].strip()
            elif line.startswith("STYLE:"):
                style = line.split(":", 1)[1].strip()
            elif line.startswith("SIZE:"):
                raw = line.split(":", 1)[1].strip()
                if raw in ("1792x1024", "1024x1792", "1024x1024"):
                    size = raw

        # If LLM didn't follow format, just use the original message as prompt
        if prompt == fallback and len(fallback) > 10:
            prompt = (
                f"Professional, high-quality: {fallback}. "
                f"Clean composition, suitable for business use."
            )

        return prompt, style, size

    def _download_image(self, url: str, original_message: str) -> str | None:
        try:
            os.makedirs(IMAGES_DIR, exist_ok=True)
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            slug = re.sub(r'[^\w]', '_', original_message[:25].lower()).strip('_')
            path = os.path.join(IMAGES_DIR, f"img_{slug}_{ts}.png")

            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                with open(path, 'wb') as f:
                    f.write(resp.content)
                return path
        except Exception:
            pass
        return None
