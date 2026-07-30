import re
from datetime import datetime, timedelta
import pytz
from typing import Dict, Any, Tuple, Optional
from app.config import ARG_TZ

DAYS_MAP = {
    'lunes': 0,
    'martes': 1,
    'miercoles': 2,
    'miércoles': 2,
    'jueves': 3,
    'viernes': 4,
    'sabado': 5,
    'sábado': 5,
    'domingo': 6
}

MONTHS_MAP = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
    'noviembre': 11, 'diciembre': 12
}

NUMBER_WORDS = {
    'un': 1, 'una': 1, 'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4,
    'cinco': 5, 'media': 0.5, 'media hora': 0.5, '1/2': 0.5
}

def get_now_arg() -> datetime:
    return datetime.now(ARG_TZ)

def format_lead_time(minutes: int) -> str:
    if minutes == 30:
        return "30 minutos antes"
    elif minutes == 60:
        return "una hora antes"
    elif minutes == 120:
        return "dos horas antes"
    elif minutes == 1440:
        return "un día antes"
    elif minutes % 60 == 0:
        hrs = minutes // 60
        return f"{hrs} horas antes"
    else:
        return f"{minutes} minutos antes"

def parse_lead_time(text: str) -> int:
    """Extrae la anticipación solicitada en minutos. Por defecto 60 min (1 hora)."""
    text_lower = text.lower()
    
    if "media hora" in text_lower or "30 minutos" in text_lower or "30 min" in text_lower:
        return 30
    if "un dia" in text_lower or "1 dia" in text_lower or "un día" in text_lower or "1 día" in text_lower:
        return 1440
    
    hrs_match = re.search(r'avisame\s+(?:con\s+)?(\w+|\d+)\s+horas?\s+antes', text_lower)
    if not hrs_match:
        hrs_match = re.search(r'(\w+|\d+)\s+horas?\s+antes', text_lower)
    
    if hrs_match:
        val_str = hrs_match.group(1)
        num = NUMBER_WORDS.get(val_str, None)
        if num is None and val_str.isdigit():
            num = int(val_str)
        if num:
            return int(num * 60)

    min_match = re.search(r'(\w+|\d+)\s+minutos?\s+antes', text_lower)
    if min_match:
        val_str = min_match.group(1)
        num = NUMBER_WORDS.get(val_str, None)
        if num is None and val_str.isdigit():
            num = int(val_str)
        if num:
            return int(num)

    return 60  # Default 1 hora

def parse_time(text: str) -> Optional[Tuple[int, int]]:
    """Extrae la hora y los minutos en formato 24hs. Devuelve (hora, minuto) o None."""
    text_lower = text.lower()
    
    # 1. Patrón "a las 17:30", "17:30", "17.30"
    m_full = re.search(r'(?:a\s+las\s+|las\s+)?(\d{1,2})[:\.](\d{2})', text_lower)
    if m_full:
        h, m = int(m_full.group(1)), int(m_full.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return (h, m)

    # 2. Patrón "a las 17", "las 17", "17 hs", "17hs"
    # Asegurar que el número no sea parte de una fecha tipo "5 de agosto"
    for m in re.finditer(r'(?:a\s+las\s+|las\s+)(\d{1,2})|\b(\d{1,2})\s*(?:hs|hrs|hora|horas)\b', text_lower):
        val_str = m.group(1) or m.group(2)
        if val_str:
            val = int(val_str)
            # Verificar si después viene "de <mes>"
            after_match = text_lower[m.end():m.end()+15]
            if re.match(r'\s+de\s+[a-z]+', after_match):
                continue
                
            if "pm" in text_lower or "de la tarde" in text_lower or "de la noche" in text_lower:
                if val < 12:
                    val += 12
            if 0 <= val <= 23:
                return (val, 0)
    
    return None

def parse_date(text: str) -> Optional[datetime]:
    """Extrae la fecha objetivo (en ARG_TZ) a partir del texto."""
    now = get_now_arg()
    text_lower = text.lower()

    if "hoy" in text_lower:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if "pasado mañana" in text_lower or "pasado manana" in text_lower:
        target = now + timedelta(days=2)
        return target.replace(hour=0, minute=0, second=0, microsecond=0)
        
    if "mañana" in text_lower or "manana" in text_lower:
        target = now + timedelta(days=1)
        return target.replace(hour=0, minute=0, second=0, microsecond=0)

    # Días de la semana ("el martes", "martes")
    for day_name, day_num in DAYS_MAP.items():
        if re.search(r'\b' + day_name + r'\b', text_lower):
            days_ahead = day_num - now.weekday()
            if days_ahead <= 0:  # Si es hoy o ya pasó en la semana, apuntar a la próxima semana
                days_ahead += 7
            target = now + timedelta(days=days_ahead)
            return target.replace(hour=0, minute=0, second=0, microsecond=0)

    # Fechas explícitas: "5 de agosto", "el 12 de septiembre"
    m_exp = re.search(r'(?:el\s+)?(\d{1,2})\s+de\s+([a-z]+)(?:\s+de\s+(\d{4}))?', text_lower)
    if m_exp:
        day = int(m_exp.group(1))
        month_name = m_exp.group(2)
        year = int(m_exp.group(3)) if m_exp.group(3) else now.year
        month = MONTHS_MAP.get(month_name)
        if month:
            target_dt = datetime(year, month, day, 0, 0, 0, tzinfo=ARG_TZ)
            if target_dt < now.replace(hour=0, minute=0, second=0, microsecond=0) and not m_exp.group(3):
                target_dt = datetime(year + 1, month, day, 0, 0, 0, tzinfo=ARG_TZ)
            return target_dt

    return None

def extract_title(text: str) -> str:
    """Limpia la frase borrando expresiones de fecha, hora y avisos para obtener el título."""
    t = text
    # 1. Remover aviso
    t = re.sub(r'avisame.*$', '', t, flags=re.IGNORECASE)
    # 2. Remover fecha explícita "el 5 de agosto", "5 de agosto"
    t = re.sub(r'(?:el\s+)?\d{1,2}\s+de\s+[a-z]+(?:\s+de\s+\d{4})?', '', t, flags=re.IGNORECASE)
    # 3. Remover horas "a las 17", "17hs", "a las 10:30"
    t = re.sub(r'(?:a\s+las\s+|las\s+)?\d{1,2}(?:[:\.]\d{2})?\s*(?:hs|hrs|hora|horas|pm|am)?', '', t, flags=re.IGNORECASE)
    # 4. Remover relativas "mañana", "hoy", "martes", etc.
    t = re.sub(r'\b(hoy|mañana|manana|pasado mañana|pasado manana|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\b', '', t, flags=re.IGNORECASE)
    # 5. Remover conectores iniciales y finales
    t = re.sub(r'\b(el|para|la|las)\b', '', t, flags=re.IGNORECASE)
    
    t = re.sub(r'^[,\.\s\-\:]+', '', t)
    t = re.sub(r'[,\.\s\-\:]+$', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    
    return t.capitalize() if t else "Compromiso"

def process_message(text: str) -> Dict[str, Any]:
    """
    Analiza la intención del mensaje del usuario y devuelve una estructura de respuesta.
    Intenciones: 'CREATE', 'QUERY', 'UPDATE', 'CANCEL', 'MARK_COMPLETED', 'AMBIGUOUS'
    """
    raw_text = text.strip()
    text_lower = raw_text.lower()
    
    # 1. Intención de CONSULTA
    if any(phrase in text_lower for phrase in [
        "¿qué tengo", "que tengo", "mostrame", "ver mis", "cuáles son", "cuales son", "mis compromisos", "próximos compromisos", "proximos compromisos", "agenda"
    ]):
        dt = parse_date(text_lower)
        target_day = "mañana" if "mañana" in text_lower or "manana" in text_lower else ("hoy" if "hoy" in text_lower else None)
        return {
            "intent": "QUERY",
            "date": dt,
            "target_day_str": target_day
        }

    # 2. Intención de MODIFICACIÓN / CAMBIO
    if text_lower.startswith("cambiá") or text_lower.startswith("cambia") or text_lower.startswith("modificá") or text_lower.startswith("modifica") or "mover" in text_lower:
        time_res = parse_time(text_lower)
        dt_res = parse_date(text_lower)
        clean_search = re.sub(r'^(cambiá|cambia|modificá|modifica|mover)\s+(el|la|mi)?\s*', '', text_lower)
        clean_search = re.sub(r'\s*\b(para|a)\b\s+.*$', '', clean_search).strip()
        
        return {
            "intent": "UPDATE",
            "search_term": clean_search,
            "new_time": time_res,
            "new_date": dt_res
        }

    # 3. Intención de CANCELAR / ELIMINAR
    if text_lower.startswith("cancelá") or text_lower.startswith("cancela") or text_lower.startswith("eliminá") or text_lower.startswith("elimina") or text_lower.startswith("borrá") or text_lower.startswith("borra"):
        clean_search = re.sub(r'^(cancelá|cancela|eliminá|elimina|borrá|borra)\s+(el|la|mi)?\s*', '', text_lower)
        clean_search = re.sub(r'\s+(del|de)\s+.*$', '', clean_search).strip()
        return {
            "intent": "CANCEL",
            "search_term": clean_search
        }

    # 4. Intención de MARCAR COMO REALIZADA
    if "marcá como realizada" in text_lower or "marca como realizada" in text_lower or "completá" in text_lower or "completa" in text_lower or "terminé" in text_lower or "termine" in text_lower or "listo el" in text_lower or "lista la" in text_lower:
        clean_search = re.sub(r'^(marcá como realizada|marca como realizada|completá|completa|terminé|termine|listo el|lista la)\s+(el|la|mi|reunión|reunion)?\s*', '', text_lower)
        return {
            "intent": "MARK_COMPLETED",
            "search_term": clean_search if clean_search else "reunión"
        }

    # 5. Intención de CREACIÓN (Default)
    dt_res = parse_date(text_lower)
    time_res = parse_time(text_lower)
    lead_minutes = parse_lead_time(text_lower)

    # Verificación estricta de ambigüedad
    if not dt_res and not time_res:
        return {
            "intent": "AMBIGUOUS",
            "prompt": "Disculpá, no llegué a entender la fecha y hora de tu compromiso. ¿Podrías indicarme para cuándo es y a qué hora?"
        }
    if not dt_res:
        return {
            "intent": "AMBIGUOUS",
            "prompt": "¡Entendido la hora! ¿Para qué día sería este compromiso? (por ejemplo: hoy, mañana, o el próximo martes)."
        }
    if not time_res:
        return {
            "intent": "AMBIGUOUS",
            "prompt": f"¡Anotado para el {dt_res.strftime('%d/%m')}! ¿A qué hora tenés este compromiso?"
        }

    final_dt = dt_res.replace(hour=time_res[0], minute=time_res[1], second=0, microsecond=0)
    title = extract_title(raw_text)

    return {
        "intent": "CREATE",
        "title": title,
        "event_datetime": final_dt,
        "reminder_offset_minutes": lead_minutes
    }
