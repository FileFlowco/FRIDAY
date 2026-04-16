"""
FRIDAY-INVOICE
Generate professional invoices and proposals.
Saves as HTML to ~/Documents/FRIDAY/output/invoices/ — optionally emails via Brevo.
"""

import os
import re
import json
import asyncio
import requests
from datetime import datetime, timedelta
from .base import BaseAgent

INVOICE_DIR   = os.path.expanduser("~/Documents/FRIDAY/output/invoices")
PROJECTS_FILE = os.path.expanduser("~/Documents/FRIDAY/logs/projects.json")

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
COMPANY_EMAIL = os.getenv("COMPANY_EMAIL", "")
COMPANY_NAME  = os.getenv("COMPANY_NAME",  "FileFlow Inc")
REPLY_TO      = os.getenv("REPLY_TO_EMAIL", "")


class FridayInvoice(BaseAgent):
    provider   = "anthropic"
    model      = "claude-sonnet-4-6"
    max_tokens = 2048

    system_prompt = """You are FRIDAY, the AI assistant for FileFlow Inc — a web design agency.
You handle invoices and proposals.

Personality: professional, efficient, call the user "Boss" occasionally.

When the user wants to create an invoice or proposal, extract this info and output it as JSON:

For INVOICE:
{
  "type": "invoice",
  "invoice_number": "INV-[auto if not given]",
  "client_name": "...",
  "client_email": "...",
  "client_company": "...",
  "due_days": 14,
  "items": [
    {"description": "...", "qty": 1, "rate": 0.00}
  ],
  "notes": "..."
}

For PROPOSAL:
{
  "type": "proposal",
  "client_name": "...",
  "client_email": "...",
  "project_name": "...",
  "items": [
    {"description": "...", "qty": 1, "rate": 0.00}
  ],
  "timeline": "2-3 weeks",
  "notes": "..."
}

OUTPUT ONLY the JSON block — no other text.
If info is missing, use sensible defaults (client_email: "", due_days: 14, qty: 1).
"""

    # ── Main handler ──────────────────────────────────────────────────────────

    async def handle(self, message: str, update=None, image_url: str = None, history=None) -> str:
        msg_lower = message.lower().strip()

        invoice_triggers = [
            "invoice", "bill", "charge", "receipt",
            "proposal", "quote", "estimate", "scope",
            "send invoice", "create invoice", "make invoice",
            "write proposal", "create proposal",
        ]

        is_invoice = any(t in msg_lower for t in invoice_triggers)
        if not is_invoice:
            return await super().handle(message, update, image_url, history=history)

        # Extract structured data via LLM
        raw = await super().handle(message, update, image_url, history=history)
        data = self._parse_json(raw)

        if not data:
            return (
                "Give me the details, Boss, and I'll build it:\n\n"
                "Invoice: client name, items + amounts, due date\n"
                "Proposal: client name, project scope, pricing\n\n"
                "Example: 'Invoice for John Smith — Website Redesign $1500, SEO Setup $500, due in 14 days'"
            )

        doc_type = data.get("type", "invoice")

        if doc_type == "invoice":
            path, fname = self._build_invoice(data)
        else:
            path, fname = self._build_proposal(data)

        if not path:
            return "Couldn't build the document. Make sure all details are included."

        # Auto-send email if client email provided
        client_email = data.get("client_email", "").strip()
        email_result = ""
        if client_email and "@" in client_email:
            email_result = self._send_invoice_email(data, client_email, path)

        reply = (
            f"{'Invoice' if doc_type == 'invoice' else 'Proposal'} ready, Boss.\n\n"
            f"Client: {data.get('client_name', 'Unknown')}\n"
        )
        if doc_type == "invoice":
            total = sum(i.get("qty", 1) * i.get("rate", 0) for i in data.get("items", []))
            reply += f"Total: ${total:,.2f}\n"
        if email_result:
            reply += f"\n{email_result}\n"

        reply += f"\n[INVOICE:{path}|{fname}]"
        return reply

    # ── Invoice HTML builder ──────────────────────────────────────────────────

    def _build_invoice(self, data: dict) -> tuple[str, str]:
        os.makedirs(INVOICE_DIR, exist_ok=True)
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        inv = data.get("invoice_number") or f"INV-{datetime.now().strftime('%Y%m%d')}"
        inv_clean = re.sub(r'[^\w\-]', '', inv)
        fname = f"{inv_clean}_{ts}.html"
        path  = os.path.join(INVOICE_DIR, fname)

        date_issued = datetime.now().strftime("%B %d, %Y")
        due_days    = int(data.get("due_days", 14))
        date_due    = (datetime.now() + timedelta(days=due_days)).strftime("%B %d, %Y")

        items     = data.get("items", [])
        subtotal  = sum(i.get("qty", 1) * i.get("rate", 0) for i in items)
        tax_rate  = 0.0
        tax_amt   = subtotal * tax_rate
        total     = subtotal + tax_amt

        items_html = ""
        for item in items:
            qty   = item.get("qty", 1)
            rate  = item.get("rate", 0)
            amt   = qty * rate
            items_html += f"""
            <tr>
              <td class="item-desc">{item.get('description','')}</td>
              <td class="item-num">{qty}</td>
              <td class="item-num">${rate:,.2f}</td>
              <td class="item-num item-total">${amt:,.2f}</td>
            </tr>"""

        notes = data.get("notes", "Thank you for your business.")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Invoice {inv}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: #f5f5f5; color: #1a1a1a; }}
  .page {{ max-width: 780px; margin: 40px auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 40px rgba(0,0,0,0.12); }}
  .header {{ background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 40px 48px; display: flex; justify-content: space-between; align-items: flex-start; }}
  .company-name {{ font-size: 22px; font-weight: 700; color: #fff; letter-spacing: 0.5px; }}
  .company-sub {{ font-size: 12px; color: #8899bb; margin-top: 4px; }}
  .invoice-badge {{ text-align: right; }}
  .invoice-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 2px; color: #8b7fff; font-weight: 600; }}
  .invoice-num {{ font-size: 24px; font-weight: 700; color: #fff; margin-top: 4px; }}
  .meta {{ padding: 32px 48px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 24px; border-bottom: 1px solid #eee; }}
  .meta-block label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: #999; font-weight: 600; display: block; margin-bottom: 6px; }}
  .meta-block .val {{ font-size: 14px; color: #1a1a1a; font-weight: 500; }}
  .meta-block .val.due {{ color: #ef4444; font-weight: 600; }}
  .bill-to {{ padding: 24px 48px; background: #fafafa; border-bottom: 1px solid #eee; }}
  .bill-to label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: #999; font-weight: 600; display: block; margin-bottom: 8px; }}
  .bill-to .client-name {{ font-size: 16px; font-weight: 600; }}
  .bill-to .client-co {{ font-size: 13px; color: #666; margin-top: 2px; }}
  .bill-to .client-email {{ font-size: 13px; color: #8b7fff; margin-top: 2px; }}
  .items {{ padding: 32px 48px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead th {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: #999; font-weight: 600; padding: 0 0 12px; border-bottom: 2px solid #eee; }}
  thead th:not(:first-child) {{ text-align: right; }}
  .item-desc {{ font-size: 14px; color: #1a1a1a; padding: 14px 0; border-bottom: 1px solid #f0f0f0; font-weight: 500; }}
  .item-num {{ font-size: 14px; color: #666; padding: 14px 0; border-bottom: 1px solid #f0f0f0; text-align: right; }}
  .item-total {{ color: #1a1a1a; font-weight: 600; }}
  .totals {{ padding: 16px 48px 32px; border-top: 2px solid #eee; margin-top: 8px; }}
  .totals-row {{ display: flex; justify-content: flex-end; gap: 48px; margin-top: 12px; font-size: 14px; color: #666; }}
  .totals-row.grand {{ margin-top: 16px; padding-top: 16px; border-top: 2px solid #eee; }}
  .totals-row.grand span:last-child {{ font-size: 22px; font-weight: 700; color: #1a1a2e; }}
  .totals-row.grand span:first-child {{ font-size: 13px; font-weight: 600; color: #1a1a1a; display: flex; align-items: center; }}
  .notes {{ padding: 24px 48px; background: #fafafa; border-top: 1px solid #eee; }}
  .notes label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: #999; font-weight: 600; display: block; margin-bottom: 8px; }}
  .notes p {{ font-size: 13px; color: #555; line-height: 1.6; }}
  .footer {{ padding: 20px 48px; display: flex; justify-content: space-between; align-items: center; }}
  .footer-tag {{ font-size: 11px; color: #ccc; }}
  .status-badge {{ background: #fef3c7; color: #92400e; font-size: 11px; font-weight: 600; padding: 4px 12px; border-radius: 20px; text-transform: uppercase; letter-spacing: 1px; }}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div>
      <div class="company-name">{COMPANY_NAME}</div>
      <div class="company-sub">{COMPANY_EMAIL}</div>
    </div>
    <div class="invoice-badge">
      <div class="invoice-label">Invoice</div>
      <div class="invoice-num">{inv}</div>
    </div>
  </div>

  <div class="meta">
    <div class="meta-block">
      <label>Issue Date</label>
      <div class="val">{date_issued}</div>
    </div>
    <div class="meta-block">
      <label>Due Date</label>
      <div class="val due">{date_due}</div>
    </div>
    <div class="meta-block">
      <label>Status</label>
      <div class="val"><span class="status-badge">Unpaid</span></div>
    </div>
  </div>

  <div class="bill-to">
    <label>Bill To</label>
    <div class="client-name">{data.get('client_name','')}</div>
    {"<div class='client-co'>" + data.get('client_company','') + "</div>" if data.get('client_company') else ""}
    {"<div class='client-email'>" + data.get('client_email','') + "</div>" if data.get('client_email') else ""}
  </div>

  <div class="items">
    <table>
      <thead>
        <tr>
          <th style="text-align:left;">Description</th>
          <th>Qty</th>
          <th>Rate</th>
          <th>Amount</th>
        </tr>
      </thead>
      <tbody>{items_html}</tbody>
    </table>
  </div>

  <div class="totals">
    <div class="totals-row"><span>Subtotal</span><span>${subtotal:,.2f}</span></div>
    <div class="totals-row grand"><span>Total Due</span><span>${total:,.2f}</span></div>
  </div>

  <div class="notes">
    <label>Notes</label>
    <p>{notes}</p>
  </div>

  <div class="footer">
    <span class="footer-tag">Generated by FRIDAY — {COMPANY_NAME}</span>
  </div>
</div>
</body>
</html>"""

        with open(path, 'w') as f:
            f.write(html)

        return path, fname

    # ── Proposal HTML builder ─────────────────────────────────────────────────

    def _build_proposal(self, data: dict) -> tuple[str, str]:
        os.makedirs(INVOICE_DIR, exist_ok=True)
        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug  = re.sub(r'[^\w]', '_', data.get('client_name', 'client').lower())[:20]
        fname = f"proposal_{slug}_{ts}.html"
        path  = os.path.join(INVOICE_DIR, fname)

        items    = data.get("items", [])
        total    = sum(i.get("qty", 1) * i.get("rate", 0) for i in items)
        timeline = data.get("timeline", "2-3 weeks")

        items_html = ""
        for item in items:
            qty  = item.get("qty", 1)
            rate = item.get("rate", 0)
            amt  = qty * rate
            items_html += f"""
            <tr>
              <td class="item-desc">{item.get('description','')}</td>
              <td class="item-num">${rate:,.2f}</td>
              <td class="item-num item-total">${amt:,.2f}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Proposal — {data.get('project_name','Web Project')}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: #f5f5f5; color: #1a1a1a; }}
  .page {{ max-width: 780px; margin: 40px auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 40px rgba(0,0,0,0.12); }}
  .header {{ background: linear-gradient(135deg, #1a1a2e, #312e81); padding: 48px 48px; }}
  .prop-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 2.5px; color: #8b7fff; font-weight: 600; margin-bottom: 12px; }}
  .prop-title {{ font-size: 28px; font-weight: 700; color: #fff; line-height: 1.2; }}
  .prop-sub {{ font-size: 14px; color: #8899bb; margin-top: 8px; }}
  .meta {{ padding: 32px 48px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 24px; background: #fafafa; border-bottom: 1px solid #eee; }}
  .meta-block label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: #999; font-weight: 600; display: block; margin-bottom: 6px; }}
  .meta-block .val {{ font-size: 14px; color: #1a1a1a; font-weight: 500; }}
  .section {{ padding: 32px 48px; border-bottom: 1px solid #eee; }}
  .section h2 {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1.5px; color: #999; font-weight: 600; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead th {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: #999; font-weight: 600; padding: 0 0 12px; border-bottom: 2px solid #eee; }}
  thead th:not(:first-child) {{ text-align: right; }}
  .item-desc {{ font-size: 14px; color: #1a1a1a; padding: 14px 0; border-bottom: 1px solid #f0f0f0; font-weight: 500; }}
  .item-num {{ font-size: 14px; color: #666; padding: 14px 0; border-bottom: 1px solid #f0f0f0; text-align: right; }}
  .item-total {{ color: #1a1a1a; font-weight: 600; }}
  .total-row {{ display: flex; justify-content: flex-end; gap: 48px; margin-top: 20px; padding-top: 16px; border-top: 2px solid #eee; }}
  .total-row span:first-child {{ font-size: 13px; font-weight: 600; }}
  .total-row span:last-child {{ font-size: 22px; font-weight: 700; color: #312e81; }}
  .cta {{ padding: 32px 48px; background: linear-gradient(135deg, #f5f3ff, #ede9fe); text-align: center; }}
  .cta p {{ font-size: 14px; color: #555; margin-bottom: 16px; }}
  .cta a {{ display: inline-block; background: #7c3aed; color: #fff; padding: 12px 32px; border-radius: 8px; font-weight: 600; font-size: 14px; text-decoration: none; }}
  .footer {{ padding: 20px 48px; }}
  .footer-tag {{ font-size: 11px; color: #ccc; }}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div class="prop-label">Project Proposal</div>
    <div class="prop-title">{data.get('project_name','Web Design Project')}</div>
    <div class="prop-sub">Prepared for {data.get('client_name','')} by {COMPANY_NAME}</div>
  </div>

  <div class="meta">
    <div class="meta-block">
      <label>Prepared For</label>
      <div class="val">{data.get('client_name','')}</div>
    </div>
    <div class="meta-block">
      <label>Date</label>
      <div class="val">{datetime.now().strftime('%B %d, %Y')}</div>
    </div>
    <div class="meta-block">
      <label>Timeline</label>
      <div class="val">{timeline}</div>
    </div>
  </div>

  <div class="section">
    <h2>Scope &amp; Pricing</h2>
    <table>
      <thead>
        <tr>
          <th style="text-align:left;">Deliverable</th>
          <th>Price</th>
          <th>Total</th>
        </tr>
      </thead>
      <tbody>{items_html}</tbody>
    </table>
    <div class="total-row">
      <span>Total Investment</span>
      <span>${total:,.2f}</span>
    </div>
  </div>

  <div class="cta">
    <p>Ready to move forward? Reach out to get started.</p>
    <a href="mailto:{COMPANY_EMAIL}">Accept &amp; Get Started</a>
  </div>

  <div class="footer">
    <span class="footer-tag">Generated by FRIDAY — {COMPANY_NAME} · {COMPANY_EMAIL}</span>
  </div>
</div>
</body>
</html>"""

        with open(path, 'w') as f:
            f.write(html)
        return path, fname

    # ── Email delivery ────────────────────────────────────────────────────────

    def _send_invoice_email(self, data: dict, to_email: str, html_path: str) -> str:
        if not BREVO_API_KEY or not COMPANY_EMAIL:
            return ""
        doc_type = data.get("type", "invoice")
        subject  = (
            f"Invoice {data.get('invoice_number','')}" if doc_type == "invoice"
            else f"Proposal — {data.get('project_name','Web Project')}"
        )
        body = (
            f"Hi {data.get('client_name','')},\n\n"
            f"Please find your {'invoice' if doc_type == 'invoice' else 'project proposal'} attached.\n\n"
            f"{'Payment is due by ' + (datetime.now() + timedelta(days=int(data.get('due_days',14)))).strftime('%B %d, %Y') + '.' if doc_type == 'invoice' else 'Let me know if you have any questions.'}\n\n"
            f"Thank you,\n{COMPANY_NAME}\n{COMPANY_EMAIL}"
        )
        try:
            resp = requests.post(
                "https://api.brevo.com/v3/smtp/email",
                json={
                    "sender":      {"name": COMPANY_NAME, "email": COMPANY_EMAIL},
                    "to":          [{"email": to_email}],
                    "replyTo":     {"email": REPLY_TO or COMPANY_EMAIL},
                    "subject":     subject,
                    "textContent": body,
                },
                headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code in (200, 201):
                return f"Emailed to {to_email}."
        except Exception:
            pass
        return ""

    # ── JSON parser ───────────────────────────────────────────────────────────

    def _parse_json(self, text: str) -> dict | None:
        try:
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                return json.loads(m.group(0))
        except Exception:
            pass
        return None
