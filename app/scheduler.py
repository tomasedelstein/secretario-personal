import logging
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import ARG_TZ
from app.database import get_due_reminders, mark_reminder_sent, get_config
from app.whatsapp import send_whatsapp_message

logger = logging.getLogger("reminder_scheduler")
scheduler = AsyncIOScheduler(timezone=ARG_TZ)

async def check_and_send_reminders():
    """
    Revisa periódicamente los recordatorios pendientes y los envía por WhatsApp.
    """
    now = datetime.now(ARG_TZ)
    now_iso = now.isoformat()
    
    due_list = get_due_reminders(now_iso)
    if not due_list:
        return

    logger.info(f"Procesando {len(due_list)} recordatorio(s) pendiente(s)...")

    authorized_phone = get_config("authorized_phone")

    for item in due_list:
        cid = item['id']
        title = item['title']
        event_dt = datetime.fromisoformat(item['event_datetime'])
        time_str = event_dt.strftime("%H:%M")
        date_str = event_dt.strftime("%d/%m/%Y")

        # Texto amigable en español rioplatense
        message_body = (
            f"🔔 *Recordatorio de tu Secretario Personal*\n\n"
            f"📌 *{title}*\n"
            f"📅 Fecha: {date_str}\n"
            f"⏰ Horario: {time_str} hs\n\n"
            f"¡Recordá estar preparado/a!"
        )

        # Si tenemos un teléfono autorizado, enviamos el WhatsApp
        if authorized_phone:
            success = await send_whatsapp_message(authorized_phone, message_body)
            if success:
                mark_reminder_sent(cid)
                logger.info(f"Recordatorio #{cid} ({title}) enviado con éxito a {authorized_phone}.")
            else:
                logger.error(f"No se pudo enviar el recordatorio #{cid} por WhatsApp.")
        else:
            logger.warning(f"Recordatorio #{cid} no enviado: No hay número de teléfono autorizado configurado.")

def start_scheduler():
    scheduler.add_job(check_and_send_reminders, 'interval', minutes=1, id='reminder_checker', replace_existing=True)
    scheduler.start()
    logger.info("Programador de recordatorios activado (frecuencia: cada 1 minuto).")
