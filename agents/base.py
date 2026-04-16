"""
FRIDAY Base Agent
Supports both OpenAI and Anthropic (Claude) providers.
If primary provider fails, automatically falls back to the other.
"""

import asyncio
import logging
logger = logging.getLogger(__name__)


class BaseAgent:
    system_prompt = "You are a helpful AI assistant."
    model         = "claude-haiku-4-5-20251001"
    provider      = "anthropic"   # "anthropic" or "openai"
    fallback_model = "gpt-4o-mini"
    max_tokens    = 4096          # default — override per agent

    def __init__(self, openai_client, anthropic_client):
        self.openai_client    = openai_client
        self.anthropic_client = anthropic_client

    async def handle(self, message: str, update=None, image_url: str = None, history: list = None) -> str:
        try:
            if self.provider == "anthropic":
                return await asyncio.to_thread(self._call_claude, message, image_url, history)
            else:
                return await asyncio.to_thread(self._call_openai, message, image_url, history)
        except Exception as e:
            logger.warning(f"Primary provider failed ({self.provider}): {e}. Falling back.")
            try:
                if self.provider == "anthropic":
                    return await asyncio.to_thread(self._call_openai_fallback, message, image_url)
                else:
                    return await asyncio.to_thread(self._call_claude_fallback, message, image_url)
            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")
                return "Having a tech issue right now, Boss. Try again in a second."

    def _call_claude(self, message: str, image_url: str = None, history: list = None) -> str:
        messages = []
        if history:
            for h in history:
                messages.append({"role": h["role"], "content": h["content"]})

        if image_url:
            content = [
                {"type": "image", "source": {"type": "url", "url": image_url}},
                {"type": "text",  "text": message}
            ]
        else:
            content = message
        messages.append({"role": "user", "content": content})

        response = self.anthropic_client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            messages=messages
        )
        return response.content[0].text

    def _call_openai(self, message: str, image_url: str = None, history: list = None) -> str:
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            for h in history:
                messages.append({"role": h["role"], "content": h["content"]})

        if image_url:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text",      "text": message}
                ]
            })
        else:
            messages.append({"role": "user", "content": message})

        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=0.7
        )
        return response.choices[0].message.content

    def _call_openai_fallback(self, message: str, image_url: str = None) -> str:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.append({"role": "user", "content": message})
        response = self.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=0.7
        )
        return response.choices[0].message.content

    def _call_claude_fallback(self, message: str, image_url: str = None) -> str:
        response = self.anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": message}]
        )
        return response.content[0].text
