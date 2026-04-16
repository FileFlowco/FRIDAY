"""
FRIDAY-AUDIT
Real website audit: PageSpeed Insights + tech stack + SEO + email/contact check.
No new API key needed — uses Google PageSpeed (free), sitecheck.py, scrape.py.
"""

import os
import re
import sys
import asyncio
import requests
from .base import BaseAgent

# ── LeadForge modules ─────────────────────────────────────────────────────────
_LF = os.path.expanduser("~/Documents/leadforge/app")
if _LF not in sys.path:
    sys.path.insert(0, _LF)

try:
    from leadforge.core import sitecheck as _sitecheck
    from leadforge.core import scrape    as _scrape
    _LF_AVAILABLE = True
except ImportError:
    _LF_AVAILABLE = False


class FridayAudit(BaseAgent):
    provider   = "anthropic"
    model      = "claude-sonnet-4-6"
    max_tokens = 2048

    system_prompt = """You are FRIDAY, the AI assistant for FileFlow Inc.
You handle website audits — but ONLY when given real audit data.

Your job is to summarize audit results and add strategic advice.
Never invent scores or technical data. Only interpret the data you're given.
Call the user "Boss" occasionally. Be direct and specific."""

    # ── Main handler ──────────────────────────────────────────────────────────

    async def handle(self, message: str, update=None, image_url: str = None, history=None) -> str:
        msg_lower = message.lower().strip()

        audit_triggers = [
            "audit", "check", "analyze", "analyse", "score",
            "speed", "performance", "pagespeed", "lighthouse",
            "seo check", "site check", "website check",
            "how fast", "how good", "is this site", "grade",
        ]

        # Extract URL from message
        url = self._extract_url(message)

        is_audit = url or any(t in msg_lower for t in audit_triggers)
        if not is_audit:
            return await super().handle(message, update, image_url, history=history)

        if not url:
            return (
                "Drop a URL and I'll audit it, Boss.\n\n"
                "Example: Audit https://example.com\n\n"
                "I'll check: speed score, mobile, SEO, tech stack, contact info — full report."
            )

        return await self._run_audit(url)

    # ── Full audit runner ─────────────────────────────────────────────────────

    async def _run_audit(self, url: str) -> str:
        # Ensure URL has scheme
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        display_url = re.sub(r'^https?://', '', url).rstrip('/')

        lines = [f"AUDIT REPORT — {display_url}", "=" * 50]

        # Run all checks concurrently
        pagespeed_mobile, pagespeed_desktop, sitecheck_result, email_result = await asyncio.gather(
            self._pagespeed(url, "mobile"),
            self._pagespeed(url, "desktop"),
            self._sitecheck(url),
            self._scrape_contact(url),
            return_exceptions=True
        )

        # ── PageSpeed ─────────────────────────────────────────────────────────
        lines.append("\nPERFORMANCE SCORES")
        lines.append("-" * 30)

        mobile_score  = None
        desktop_score = None

        if isinstance(pagespeed_mobile, dict):
            mobile_score = pagespeed_mobile.get("score")
            lines.append(f"Mobile:  {self._score_bar(mobile_score)}")
            cwv = pagespeed_mobile.get("cwv", {})
            if cwv.get("fcp"):    lines.append(f"  First Contentful Paint: {cwv['fcp']}")
            if cwv.get("lcp"):    lines.append(f"  Largest Contentful Paint: {cwv['lcp']}")
            if cwv.get("tbt"):    lines.append(f"  Total Blocking Time: {cwv['tbt']}")
            if cwv.get("cls"):    lines.append(f"  Cumulative Layout Shift: {cwv['cls']}")
            if cwv.get("speed"):  lines.append(f"  Speed Index: {cwv['speed']}")
        else:
            lines.append("Mobile:  Could not fetch (site may be blocking crawlers)")

        if isinstance(pagespeed_desktop, dict):
            desktop_score = pagespeed_desktop.get("score")
            lines.append(f"Desktop: {self._score_bar(desktop_score)}")
        else:
            lines.append("Desktop: Could not fetch")

        # ── Opportunities ─────────────────────────────────────────────────────
        if isinstance(pagespeed_mobile, dict) and pagespeed_mobile.get("opportunities"):
            lines.append("\nTOP IMPROVEMENTS (from PageSpeed)")
            lines.append("-" * 30)
            for opp in pagespeed_mobile["opportunities"][:4]:
                lines.append(f"  • {opp['title']}")
                if opp.get("savings"):
                    lines.append(f"    → Potential savings: {opp['savings']}")

        # ── Tech stack ────────────────────────────────────────────────────────
        lines.append("\nTECH STACK & SITE QUALITY")
        lines.append("-" * 30)

        skip    = None
        signals = []
        if isinstance(sitecheck_result, tuple):
            skip, signals = sitecheck_result
            if not signals:
                if skip:
                    lines.append("  Modern stack detected (Webflow/Next.js/Shopify)")
                else:
                    lines.append("  No major issues detected")
            else:
                for s in signals:
                    icon = "X" if s != "template-based website" else "!"
                    lines.append(f"  [{icon}] {s.title()}")
        else:
            lines.append("  Could not reach site for tech stack check")

        # ── Mobile check ──────────────────────────────────────────────────────
        mobile_tag = ""
        if isinstance(sitecheck_result, tuple):
            if "not mobile optimized" in signals:
                mobile_tag = "NOT MOBILE OPTIMIZED — Google will penalize this"
            else:
                mobile_tag = "Mobile viewport tag present"
        lines.append(f"\nMOBILE\n{'-'*30}\n  {mobile_tag or 'Unknown'}")

        # ── Contact / Email ───────────────────────────────────────────────────
        lines.append("\nCONTACT INFO FOUND")
        lines.append("-" * 30)
        if isinstance(email_result, str) and email_result:
            lines.append(f"  Email: {email_result}")
        else:
            lines.append("  No email found on contact/about pages")

        # ── SEO quick check ───────────────────────────────────────────────────
        seo_data = await self._quick_seo(url)
        lines.append("\nSEO QUICK CHECK")
        lines.append("-" * 30)
        for k, v in seo_data.items():
            lines.append(f"  {k}: {v}")

        # ── Overall verdict ───────────────────────────────────────────────────
        lines.append("\nVERDICT")
        lines.append("-" * 30)
        verdict = self._verdict(mobile_score, desktop_score, signals, bool(email_result))
        lines.append(verdict)

        # ── Sales angle ───────────────────────────────────────────────────────
        pitch = self._pitch_angle(mobile_score, signals, bool(email_result))
        if pitch:
            lines.append("\nSALES ANGLE")
            lines.append("-" * 30)
            lines.append(pitch)

        return "\n".join(lines)

    # ── PageSpeed Insights ────────────────────────────────────────────────────

    async def _pagespeed(self, url: str, strategy: str = "mobile") -> dict:
        try:
            params = {
                "url":      url,
                "strategy": strategy,
                "category": "performance",
            }
            resp = await asyncio.to_thread(
                requests.get,
                "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                params=params,
                timeout=30
            )
            data = resp.json()
            cats  = data.get("lighthouseResult", {}).get("categories", {})
            score = int((cats.get("performance", {}).get("score", 0) or 0) * 100)

            audits = data.get("lighthouseResult", {}).get("audits", {})

            # Core Web Vitals
            cwv = {
                "fcp":   self._fmt_audit(audits.get("first-contentful-paint")),
                "lcp":   self._fmt_audit(audits.get("largest-contentful-paint")),
                "tbt":   self._fmt_audit(audits.get("total-blocking-time")),
                "cls":   self._fmt_audit(audits.get("cumulative-layout-shift")),
                "speed": self._fmt_audit(audits.get("speed-index")),
            }

            # Top opportunities
            opps = []
            for key, audit in audits.items():
                if audit.get("details", {}).get("type") == "opportunity":
                    savings = audit.get("details", {}).get("overallSavingsMs")
                    if savings and savings > 200:
                        opps.append({
                            "title":   audit.get("title", key),
                            "savings": f"{savings/1000:.1f}s" if savings else None,
                        })
            opps.sort(key=lambda x: float(x["savings"].replace("s","")) if x.get("savings") else 0, reverse=True)

            return {"score": score, "cwv": cwv, "opportunities": opps[:5]}
        except Exception:
            return {}

    def _fmt_audit(self, audit: dict | None) -> str | None:
        if not audit:
            return None
        return audit.get("displayValue", "")

    # ── Site check ────────────────────────────────────────────────────────────

    async def _sitecheck(self, url: str) -> tuple:
        if _LF_AVAILABLE:
            return await asyncio.to_thread(_sitecheck.analyze, url)
        # Fallback: basic check
        try:
            resp = await asyncio.to_thread(
                requests.get, url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10
            )
            signals = []
            html = resp.text.lower()
            if '<meta name="viewport"' not in html:
                signals.append("not mobile optimized")
            if len(html) < 8000:
                signals.append("basic / thin site")
            for bad in ["wix", "weebly", "squarespace", "wp-content", "wordpress"]:
                if bad in html:
                    signals.append("template-based website")
                    break
            return (False, signals)
        except Exception:
            return (False, ["website unreachable"])

    # ── Email scrape ──────────────────────────────────────────────────────────

    async def _scrape_contact(self, url: str) -> str:
        if _LF_AVAILABLE:
            return await asyncio.to_thread(_scrape.scrape_site, url)
        return ""

    # ── Quick SEO headers check ───────────────────────────────────────────────

    async def _quick_seo(self, url: str) -> dict:
        result = {}
        try:
            from bs4 import BeautifulSoup
            resp = await asyncio.to_thread(
                requests.get, url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
                timeout=12
            )
            soup = BeautifulSoup(resp.text, "html.parser")

            title = soup.find("title")
            result["Title tag"] = f'"{title.get_text()[:60]}"' if title else "MISSING"

            desc = soup.find("meta", attrs={"name": "description"})
            if desc and desc.get("content"):
                content = desc["content"][:80]
                result["Meta description"] = f'"{content}..."'
            else:
                result["Meta description"] = "MISSING — critical for search rankings"

            h1s = soup.find_all("h1")
            result["H1 tags"] = f"{len(h1s)} found" if h1s else "MISSING — add one with your main keyword"

            canonical = soup.find("link", attrs={"rel": "canonical"})
            result["Canonical URL"] = "Present" if canonical else "Missing"

            og_image = soup.find("meta", attrs={"property": "og:image"})
            result["Social preview image"] = "Present" if og_image else "Missing (affects social sharing)"

        except Exception as e:
            result["Error"] = "Could not fetch page for SEO check"
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_url(self, message: str) -> str | None:
        m = re.search(r'https?://[^\s]+', message)
        if m:
            return m.group(0).rstrip(".,!?)")
        # Try "audit example.com" pattern
        m2 = re.search(r'(?:audit|check|analyze|score|test)\s+((?:www\.)?[a-z0-9\-]+\.[a-z]{2,}(?:/[^\s]*)?)', message, re.I)
        if m2:
            return "https://" + m2.group(1)
        # Bare domain
        m3 = re.search(r'\b((?:www\.)?[a-z0-9\-]{3,}\.(com|net|org|io|co|dev|app|agency)(?:/[^\s]*)?)\b', message, re.I)
        if m3:
            return "https://" + m3.group(1)
        return None

    def _score_bar(self, score: int | None) -> str:
        if score is None:
            return "N/A"
        filled = round(score / 10)
        bar    = "█" * filled + "░" * (10 - filled)
        label  = "FAST" if score >= 90 else ("NEEDS WORK" if score >= 50 else "SLOW")
        return f"{score}/100  [{bar}]  {label}"

    def _verdict(self, mob: int | None, desk: int | None, signals: list, has_email: bool) -> str:
        issues = []
        if mob and mob < 50:    issues.append("Very slow on mobile")
        elif mob and mob < 90:  issues.append("Mobile speed needs improvement")
        if "not mobile optimized" in signals:  issues.append("Not mobile-friendly")
        if "template-based website" in signals: issues.append("Cookie-cutter template site")
        if "basic / thin site" in signals:      issues.append("Thin/minimal website")
        if not has_email:                        issues.append("No contact email found")

        if not issues:
            return "Site looks solid. Hard to find obvious quick wins here — pitch SEO or redesign for growth."
        return "Issues found:\n" + "\n".join(f"  • {i}" for i in issues)

    def _pitch_angle(self, mob: int | None, signals: list, has_email: bool) -> str:
        parts = []
        if mob and mob < 60:
            parts.append("Lead with speed: 'Your site loads in Xs on mobile — you're losing 40% of visitors before they see anything.'")
        if "not mobile optimized" in signals:
            parts.append("Lead with mobile: 'Over 60% of your customers are on phone — your site isn't optimized for them.'")
        if "template-based website" in signals:
            parts.append("Lead with credibility: 'Your Wix/WordPress site looks like thousands of others — custom build sets you apart.'")
        if not has_email:
            parts.append("Lead with trust: 'Hard to contact you — no visible email on your site. You're losing potential clients.'")
        return "\n".join(parts) if parts else ""
