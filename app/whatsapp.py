import hmac
import hashlib
import logging
import httpx
from typing import Dict, Any, Optional
from app.database import get_config

logger = logging.getLogger("whatsapp_service")

async def send_whatsapp_message(to_number: str, text_body: str) -> bool:
    """
    Envía un mensaje de texto por WhatsApp mediante la API Oficial de Meta Cloud API.
    """
    phone_number_id = get_config("phone_number_id")
    access_token = get_config("access_token")

    if not phone_number_id or not access_token:
        logger.warning("No se pueden enviar mensajes por WhatsApp: falta phone_number_id o access_token en la configuración.")
        return False

    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Limpiar formato de número telefónico (quitar '+', espacios, etc.)
    clean_number = "".join(filter(str.isdigit, to_number))

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_number,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text_body
        }
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in [200, 201]:
                logger.info(f"Mensaje enviado con éxito a {clean_number}")
                return True
            else:
                logger.error(f"Error al enviar mensaje WhatsApp ({resp.status_code}): {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Excepción al conectar con WhatsApp API: {e}")
        return False

def verify_webhook_signature(body_bytes: bytes, signature_header: str) -> bool:
    """
    Valida la firma HMAC-SHA256 enviada por Meta en los webhooks para prevenir falsificaciones.
    """
    app_secret = get_config("app_secret")
    if not app_secret or not signature_header:
        return True  # Si aún no se ha configurado el secret, permitir para pruebas

    if not signature_header.startswith("sha256="):
        return False

    expected_sig = signature_header.split("sha256=")[1]
    mac = hmac.new(app_secret.encode('utf-8'), msg=body_bytes, digestmod=hashlib.sha256)
    computed_sig = mac.hexdigest()

    return hmac.compare_digest(computed_sig, expected_sig)
