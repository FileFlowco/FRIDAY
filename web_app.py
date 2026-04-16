"""
FRIDAY Web Dashboard
Runs alongside the Telegram bot. Opens in browser at http://localhost:7771
"""

import os
import re
import json
import glob
import requests as req
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import sys as _sys
_sys.path.insert(0, os.path.dirname(__file__))
from config import LEADS_DIR, OUTPUT_DIR, IMAGES_DIR, INVOICES_DIR, USAGE_FILE
import state as _state

app = FastAPI()

# Agents will be injected from main.py
agents = {}
openai_client = None
anthropic_client = None

HTML = open(os.path.join(os.path.dirname(__file__), "dashboard.html")).read()


@app.get("/")
async def root():
    return HTMLResponse(HTML)


@app.get("/api/stats")
async def stats():
    leads  = len(glob.glob(os.path.join(LEADS_DIR, "*.json"))) if os.path.exists(LEADS_DIR) else 0
    builds = len(os.listdir(OUTPUT_DIR)) if os.path.exists(OUTPUT_DIR) else 0
    images = len(glob.glob(os.path.join(IMAGES_DIR, "*.png"))) if os.path.exists(IMAGES_DIR) else 0

    emails = 0
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE) as f:
                usage  = json.load(f)
                emails = sum(1 for u in usage if u.get("agent") == "OUTREACH")
        except:
            pass

    return {"leads": leads, "builds": builds, "emails": emails, "images": images}


# ── Leads download ─────────────────────────────────────────────────────────────

@app.get("/api/leads/download/{filename}")
async def download_lead_file(filename: str):
    safe = re.sub(r'[^a-zA-Z0-9_\-.]', '', filename)
    path = os.path.join(LEADS_DIR, safe)
    if not os.path.exists(path):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "File not found"}, status_code=404)
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
            if safe.endswith(".xlsx") else "application/octet-stream"
    return FileResponse(path, media_type=media, filename=safe)


@app.get("/api/leads")
async def get_leads():
    files = sorted(glob.glob(os.path.join(LEADS_DIR, "*.json")), reverse=True)[:5]
    results = []
    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
                results.append({"file": os.path.basename(f), "count": len(data), "data": data[:3]})
        except:
            pass
    return results


# ── Images endpoint ────────────────────────────────────────────────────────────

@app.get("/api/images/{filename}")
async def serve_image(filename: str):
    safe = re.sub(r'[^a-zA-Z0-9_\-.]', '', filename)
    path = os.path.join(IMAGES_DIR, safe)
    if not os.path.exists(path):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Image not found"}, status_code=404)
    ext  = safe.rsplit('.', 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    return FileResponse(path, media_type=mime)


# ── Invoice / proposal download ────────────────────────────────────────────────

@app.get("/api/invoices/{filename}")
async def serve_invoice(filename: str):
    safe = re.sub(r'[^a-zA-Z0-9_\-.]', '', filename)
    path = os.path.join(INVOICES_DIR, safe)
    if not os.path.exists(path):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(path, media_type="text/html", filename=safe)


# ── Builds list ────────────────────────────────────────────────────────────────

@app.get("/api/builds")
async def get_builds():
    if not os.path.exists(OUTPUT_DIR):
        return []
    dirs = sorted(
        [d for d in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, d))],
        reverse=True
    )[:10]
    return [{"name": d, "path": f"~/Documents/FRIDAY/output/{d}/index.html"} for d in dirs]


# ── ElevenLabs TTS ─────────────────────────────────────────────────────────────

@app.post("/api/speak")
async def speak(request: Request):
    import re, asyncio
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return {"error": "No text provided"}

    api_key  = os.getenv("ELEVENLABS_API_KEY", "")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "")

    if not api_key or not voice_id:
        return {"error": "ElevenLabs not configured"}

    text = re.sub(r'\*+', '', text)
    text = re.sub(r'#{1,6}\s', '', text)
    text = re.sub(r'`+', '', text)
    text = re.sub(r'\n+', ' ', text)
    text = text[:600]

    def call_elevenlabs():
        return req.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
            json={"text": text, "voice_settings": {"stability": 0.45, "similarity_boost": 0.80}},
            timeout=20
        )

    try:
        resp         = await asyncio.to_thread(call_elevenlabs)
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type or resp.status_code != 200:
            try:    err = resp.json()
            except: err = resp.text[:200]
            return {"error": f"ElevenLabs: {err}"}

        audio_bytes = resp.content
        from io import BytesIO
        return StreamingResponse(BytesIO(audio_bytes), media_type="audio/mpeg",
                                 headers={"Content-Length": str(len(audio_bytes)),
                                          "Cache-Control": "no-cache"})
    except Exception as e:
        return {"error": str(e)}


# ── Whisper STT ───────────────────────────────────────────────────────────────

@app.post("/api/transcribe")
async def transcribe(request: Request):
    import asyncio, tempfile
    from fastapi import UploadFile
    content_type = request.headers.get("content-type", "")
    if "multipart" not in content_type:
        return {"error": "Send audio as multipart/form-data"}

    form  = await request.form()
    audio = form.get("audio")
    if not audio:
        return {"error": "No audio field"}

    audio_bytes = await audio.read()
    if not audio_bytes:
        return {"error": "Empty audio"}

    if openai_client is None:
        return {"error": "OpenAI not configured"}

    # Write to tmp file so Whisper can read it
    suffix = ".webm"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        def call_whisper():
            with open(tmp_path, "rb") as f:
                return openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="text"
                )

        text = await asyncio.to_thread(call_whisper)
        return {"text": text.strip()}
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass


# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.post("/api/clear")
async def clear_history():
    _state.clear_history("web")
    return {"ok": True}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    history = []
    try:
        while True:
            data    = await websocket.receive_text()
            payload = json.loads(data)
            message = payload.get("message", "")
            module  = payload.get("module", "FRIDAY")

            if module not in agents:
                module = "FRIDAY"

            agent    = agents[module]
            response = await agent.handle(message, history=history)

            # ── Extract all file markers ──────────────────────────────────────
            download_url  = None
            download_name = None
            image_url     = None
            image_name    = None
            invoice_url   = None
            invoice_name  = None

            # Spreadsheet
            m = re.search(r'\[SPREADSHEET:(.+?)\|(.+?)\]', response)
            if m:
                download_name = m.group(2)
                download_url  = f"/api/leads/download/{download_name}"
                response      = response[:m.start()].rstrip()

            # Image
            m = re.search(r'\[IMAGE:(.+?)\|(.+?)\]', response)
            if m:
                image_name = m.group(2)
                image_url  = f"/api/images/{image_name}"
                response   = response[:m.start()].rstrip()

            # Invoice / proposal
            m = re.search(r'\[INVOICE:(.+?)\|(.+?)\]', response)
            if m:
                invoice_name = m.group(2)
                invoice_url  = f"/api/invoices/{invoice_name}"
                response     = response[:m.start()].rstrip()

            history.append({"role": "user",      "content": message})
            history.append({"role": "assistant",  "content": response[:500]})
            history = history[-20:]

            out = {"response": response}
            if download_url:
                out["download_url"]  = download_url
                out["download_name"] = download_name
            if image_url:
                out["image_url"]  = image_url
                out["image_name"] = image_name
            if invoice_url:
                out["invoice_url"]  = invoice_url
                out["invoice_name"] = invoice_name

            await websocket.send_text(json.dumps(out))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"response": f"Error: {str(e)}"}))
        except:
            pass
