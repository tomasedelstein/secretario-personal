import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from app.config import ARG_TZ
from app.database import (
    init_db, create_commitment, get_commitments, get_commitment_by_id,
    update_commitment, delete_commitment, find_commitment_by_title_approx,
    set_config, get_config, get_all_config, is_message_processed, mark_message_processed
)
from app.nlp_engine import process_message, format_lead_time
from app.whatsapp import send_whatsapp_message, verify_webhook_signature
from app.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main_server")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización de la base de datos y del programador al arrancar
    init_db()
    start_scheduler()
    logger.info("Base de datos inicializada y programador de recordatorios activo.")
    yield

app = FastAPI(title="Agente Secretario Personal", lifespan=lifespan)

# Montar archivos estáticos y plantillas
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Modelos de Petición REST ---

class CommitmentCreateReq(BaseModel):
    title: str
    category: Optional[str] = "General"
    event_datetime: str
    reminder_offset_minutes: Optional[int] = 60

class CommitmentUpdateReq(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    event_datetime: Optional[str] = None
    reminder_offset_minutes: Optional[int] = None
    status: Optional[str] = None

class SettingsReq(BaseModel):
    phone_number_id: str
    access_token: str
    app_id: Optional[str] = ""
    app_secret: Optional[str] = ""
    webhook_token: Optional[str] = "secretario_verify_token_2026"
    authorized_phone: str

# --- Rutas de la Interfaz Web ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/status")
async def get_system_status():
    phone_id = get_config("phone_number_id")
    token = get_config("access_token")
    auth_phone = get_config("authorized_phone")
    configured = bool(phone_id and token and auth_phone)
    return {"configured": configured, "authorized_phone": auth_phone}

@app.get("/api/settings")
async def get_settings():
    cfg = get_all_config()
    # Ocultar parcialmente tokens sensibles
    token = cfg.get("access_token", "")
    masked_token = (token[:6] + "..." + token[-4:]) if len(token) > 10 else token
    
    sec = cfg.get("app_secret", "")
    masked_sec = (sec[:3] + "..." + sec[-3:]) if len(sec) > 6 else sec

    return {
        "phone_number_id": cfg.get("phone_number_id", ""),
        "access_token": masked_token,
        "app_id": cfg.get("app_id", ""),
        "app_secret": masked_sec,
        "webhook_token": cfg.get("webhook_token", "secretario_verify_token_2026"),
        "authorized_phone": cfg.get("authorized_phone", "")
    }

@app.post("/api/settings")
async def save_settings(req: SettingsReq):
    # Si el usuario mandó un token enmascarado y ya existía uno guardado, no sobreescribir con la máscara
    if "..." in req.access_token:
        existing_token = get_config("access_token")
        if existing_token:
            req.access_token = existing_token
            
    if "..." in req.app_secret:
        existing_sec = get_config("app_secret")
        if existing_sec:
            req.app_secret = existing_sec

    set_config("phone_number_id", req.phone_number_id.strip())
    set_config("access_token", req.access_token.strip())
    set_config("app_id", req.app_id.strip())
    set_config("app_secret", req.app_secret.strip())
    set_config("webhook_token", req.webhook_token.strip())
    set_config("authorized_phone", req.authorized_phone.strip())
    return {"status": "success", "message": "Configuración guardada correctamente."}

# --- Rutas CRUD de Compromisos (REST) ---

@app.get("/api/commitments")
async def list_commitments(status: Optional[str] = None):
    return get_commitments(status_filter=status)

@app.post("/api/commitments")
async def add_commitment(req: CommitmentCreateReq):
    c = create_commitment(
        title=req.title,
        event_datetime_iso=req.event_datetime,
        reminder_offset_minutes=req.reminder_offset_minutes or 60,
        category=req.category or "General"
    )
    return c

@app.put("/api/commitments/{cid}")
async def edit_commitment(cid: int, req: CommitmentUpdateReq):
    updated = update_commitment(
        cid=cid,
        title=req.title,
        category=req.category,
        event_datetime_iso=req.event_datetime,
        reminder_offset_minutes=req.reminder_offset_minutes,
        status=req.status
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Compromiso no encontrado")
    return updated

@app.delete("/api/commitments/{cid}")
async def remove_commitment(cid: int):
    ok = delete_commitment(cid)
    if not ok:
        raise HTTPException(status_code=404, detail="Compromiso no encontrado")
    return {"status": "success"}

# --- Webhook de WhatsApp (API Oficial de Meta) ---

@app.get("/api/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge")
):
    expected_token = get_config("webhook_token") or "secretario_verify_token_2026"
    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        logger.info("Webhook verificado exitosamente con Meta.")
        return Response(content=hub_challenge, media_type="text/plain")
    else:
        logger.warning("Fallo en la verificación del Webhook de Meta.")
        raise HTTPException(status_code=403, detail="Token de verificación inválido")

@app.post("/api/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    body_bytes = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    
    # Validar firma HMAC si está configurada
    if not verify_webhook_signature(body_bytes, signature):
        logger.warning("Firma de webhook no válida recibida.")
        raise HTTPException(status_code=401, detail="Firma no válida")

    payload = await request.json()

    # Extraer mensajes estructurados de Meta
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg in messages:
                    msg_id = msg.get("id")
                    from_number = msg.get("from")
                    msg_type = msg.get("type")

                    # Filtrar únicamente mensajes de texto
                    if msg_type != "text":
                        continue

                    text_body = msg.get("text", {}).get("body", "")

                    # Verificar teléfono autorizado
                    authorized_phone = get_config("authorized_phone")
                    if authorized_phone:
                        clean_auth = "".join(filter(str.isdigit, authorized_phone))
                        clean_from = "".join(filter(str.isdigit, from_number))
                        if clean_auth not in clean_from and clean_from not in clean_auth:
                            logger.warning(f"Mensaje ignorado de número no autorizado: {from_number}")
                            continue

                    # Desduplicación por wamid de WhatsApp
                    if is_message_processed(msg_id):
                        logger.info(f"Mensaje repetido omitido: {msg_id}")
                        continue
                    
                    mark_message_processed(msg_id)

                    # Procesar mensaje en segundo plano para responder rápido a Meta HTTP 200 OK
                    background_tasks.add_task(process_and_reply_whatsapp, from_number, text_body, msg_id)

    except Exception as e:
        logger.error(f"Error procesando estructura del webhook: {e}")

    return {"status": "received"}

async def process_and_reply_whatsapp(from_number: str, text_body: str, msg_id: str):
    """
    Procesa el texto en lenguaje natural, ejecuta la acción en la base de datos y responde por WhatsApp.
    """
    parsed = process_message(text_body)
    intent = parsed.get("intent")

    if intent == "AMBIGUOUS":
        reply_text = parsed.get("prompt", "Disculpá, ¿podrías darme más detalles de la fecha u hora de tu compromiso?")
        await send_whatsapp_message(from_number, reply_text)
        return

    if intent == "CREATE":
        title = parsed["title"]
        event_dt = parsed["event_datetime"]
        offset = parsed["reminder_offset_minutes"]
        
        c = create_commitment(
            title=title,
            event_datetime_iso=event_dt.isoformat(),
            reminder_offset_minutes=offset,
            whatsapp_msg_id=msg_id
        )

        date_str = event_dt.strftime("%d/%m")
        is_today = event_dt.date() == datetime.now(ARG_TZ).date()
        is_tomorrow = event_dt.date() == (datetime.now(ARG_TZ) + timedelta(days=1)).date()
        
        day_text = "hoy" if is_today else ("mañana" if is_tomorrow else f"el {date_str}")
        time_str = event_dt.strftime("%H:%M")
        lead_str = format_lead_time(offset)

        reply_text = f"Listo, agendé *{title}* para {day_text} a las {time_str}. Te avisaré {lead_str}."
        await send_whatsapp_message(from_number, reply_text)
        return

    if intent == "QUERY":
        dt_target = parsed.get("date")
        target_day_str = parsed.get("target_day_str")

        commitments = get_commitments(status_filter="PENDING")
        
        if dt_target:
            commitments = [c for c in commitments if datetime.fromisoformat(c["event_datetime"]).date() == dt_target.date()]

        if not commitments:
            day_label = f"para {target_day_str}" if target_day_str else "próximos"
            reply_text = f"No tenés compromisos pendientes {day_label}."
        else:
            lines = ["📋 *Tus próximos compromisos:*"]
            for c in commitments[:10]:  # Mostrar hasta 10
                dt = datetime.fromisoformat(c["event_datetime"])
                d_str = dt.strftime("%d/%m")
                t_str = dt.strftime("%H:%M")
                lines.append(f"• *{c['title']}* - {d_str} a las {t_str} hs")
            reply_text = "\n".join(lines)

        await send_whatsapp_message(from_number, reply_text)
        return

    if intent == "UPDATE":
        search_term = parsed.get("search_term", "")
        new_time = parsed.get("new_time")
        new_date = parsed.get("new_date")

        matching = find_commitment_by_title_approx(search_term)
        if not matching:
            reply_text = f"No encontré ningún compromiso pendiente que coincida con '{search_term}'."
            await send_whatsapp_message(from_number, reply_text)
            return

        dt_orig = datetime.fromisoformat(matching["event_datetime"])
        target_dt = dt_orig

        if new_date:
            target_dt = target_dt.replace(year=new_date.year, month=new_date.month, day=new_date.day)
        if new_time:
            target_dt = target_dt.replace(hour=new_time[0], minute=new_time[1])

        updated = update_commitment(
            cid=matching["id"],
            event_datetime_iso=target_dt.isoformat()
        )

        time_str = target_dt.strftime("%H:%M")
        date_str = target_dt.strftime("%d/%m")
        reply_text = f"Listo, cambié *{matching['title']}* para el {date_str} a las {time_str} hs."
        await send_whatsapp_message(from_number, reply_text)
        return

    if intent == "CANCEL":
        search_term = parsed.get("search_term", "")
        matching = find_commitment_by_title_approx(search_term)
        if not matching:
            reply_text = f"No encontré ningún compromiso pendiente llamado '{search_term}'."
            await send_whatsapp_message(from_number, reply_text)
            return

        update_commitment(cid=matching["id"], status="CANCELLED")
        reply_text = f"Listo, cancelé el compromiso *{matching['title']}*."
        await send_whatsapp_message(from_number, reply_text)
        return

    if intent == "MARK_COMPLETED":
        search_term = parsed.get("search_term", "")
        matching = find_commitment_by_title_approx(search_term)
        if not matching:
            reply_text = f"No encontré ningún compromiso pendiente coincidente para marcar como realizado."
            await send_whatsapp_message(from_number, reply_text)
            return

        update_commitment(cid=matching["id"], status="COMPLETED")
        reply_text = f"¡Buenísimo! Marcá como realizada: *{matching['title']}*."
        await send_whatsapp_message(from_number, reply_text)
        return
