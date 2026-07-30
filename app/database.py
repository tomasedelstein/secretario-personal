import sqlite3
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.config import DB_PATH, ARG_TZ
from app.crypto import encrypt_val, decrypt_val

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS commitments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT DEFAULT 'General',
        event_datetime TEXT NOT NULL,
        reminder_offset_minutes INTEGER DEFAULT 60,
        reminder_datetime TEXT NOT NULL,
        reminder_status TEXT DEFAULT 'PENDING',
        status TEXT DEFAULT 'PENDING',
        whatsapp_message_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS processed_messages (
        message_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL
    );
    """)
    
    conn.commit()
    conn.close()

def set_config(key: str, value: str):
    conn = get_db()
    cursor = conn.cursor()
    enc_val = encrypt_val(value)
    now = datetime.now(ARG_TZ).isoformat()
    cursor.execute("""
        INSERT INTO system_config (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?
    """, (key, enc_val, now, enc_val, now))
    conn.commit()
    conn.close()

def get_config(key: str) -> str:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row and row['value']:
        val = decrypt_val(row['value'])
        if val:
            return val
            
    # Fallback a variables de entorno para Render
    env_map = {
        "phone_number_id": os.getenv("PHONE_NUMBER_ID", ""),
        "access_token": os.getenv("ACCESS_TOKEN", ""),
        "authorized_phone": os.getenv("AUTHORIZED_PHONE", ""),
        "app_id": os.getenv("APP_ID", ""),
        "app_secret": os.getenv("APP_SECRET", ""),
        "webhook_token": os.getenv("WEBHOOK_TOKEN", "secretario_verify_token_2026")
    }
    return env_map.get(key, "")

def get_all_config() -> Dict[str, str]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM system_config")
    rows = cursor.fetchall()
    conn.close()
    res = {}
    for r in rows:
        res[r['key']] = decrypt_val(r['value']) if r['value'] else ""
        
    # Completar con env vars si faltan
    if not res.get("phone_number_id"):
        res["phone_number_id"] = os.getenv("PHONE_NUMBER_ID", "")
    if not res.get("access_token"):
        res["access_token"] = os.getenv("ACCESS_TOKEN", "")
    if not res.get("authorized_phone"):
        res["authorized_phone"] = os.getenv("AUTHORIZED_PHONE", "")
    if not res.get("webhook_token"):
        res["webhook_token"] = os.getenv("WEBHOOK_TOKEN", "secretario_verify_token_2026")
    return res

def is_message_processed(msg_id: str) -> bool:
    if not msg_id:
        return False
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT message_id FROM processed_messages WHERE message_id = ?", (msg_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def mark_message_processed(msg_id: str):
    if not msg_id:
        return
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now(ARG_TZ).isoformat()
    try:
        cursor.execute("INSERT INTO processed_messages (message_id, created_at) VALUES (?, ?)", (msg_id, now))
        conn.commit()
    except Exception:
        pass
    conn.close()

def create_commitment(
    title: str,
    event_datetime_iso: str,
    reminder_offset_minutes: int = 60,
    category: str = "General",
    reminder_datetime_iso: Optional[str] = None,
    whatsapp_msg_id: Optional[str] = None
) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now(ARG_TZ).isoformat()

    if not reminder_datetime_iso:
        dt = datetime.fromisoformat(event_datetime_iso)
        from datetime import timedelta
        rem_dt = dt - timedelta(minutes=reminder_offset_minutes)
        reminder_datetime_iso = rem_dt.isoformat()

    cursor.execute("""
        INSERT INTO commitments (
            title, category, event_datetime, reminder_offset_minutes,
            reminder_datetime, reminder_status, status, whatsapp_message_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'PENDING', 'PENDING', ?, ?, ?)
    """, (
        title, category, event_datetime_iso, reminder_offset_minutes,
        reminder_datetime_iso, whatsapp_msg_id, now, now
    ))
    
    commitment_id = cursor.lastrowid
    conn.commit()
    
    cursor.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,))
    row = dict(cursor.fetchone())
    conn.close()
    return row

def get_commitments(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if status_filter:
        cursor.execute("SELECT * FROM commitments WHERE status = ? ORDER BY event_datetime ASC", (status_filter,))
    else:
        cursor.execute("SELECT * FROM commitments ORDER BY event_datetime ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_commitment_by_id(cid: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM commitments WHERE id = ?", (cid,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_commitment(
    cid: int,
    title: Optional[str] = None,
    category: Optional[str] = None,
    event_datetime_iso: Optional[str] = None,
    reminder_offset_minutes: Optional[int] = None,
    status: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    existing = get_commitment_by_id(cid)
    if not existing:
        return None
    
    new_title = title if title is not None else existing['title']
    new_category = category if category is not None else existing['category']
    new_event_dt = event_datetime_iso if event_datetime_iso is not None else existing['event_datetime']
    new_offset = reminder_offset_minutes if reminder_offset_minutes is not None else existing['reminder_offset_minutes']
    new_status = status if status is not None else existing['status']
    
    from datetime import timedelta
    dt = datetime.fromisoformat(new_event_dt)
    new_rem_dt = (dt - timedelta(minutes=new_offset)).isoformat()
    
    new_rem_status = 'INVALIDATED' if new_status in ['CANCELLED', 'COMPLETED'] else 'PENDING'
    
    now = datetime.now(ARG_TZ).isoformat()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE commitments
        SET title = ?, category = ?, event_datetime = ?, reminder_offset_minutes = ?,
            reminder_datetime = ?, reminder_status = ?, status = ?, updated_at = ?
        WHERE id = ?
    """, (
        new_title, new_category, new_event_dt, new_offset,
        new_rem_dt, new_rem_status, new_status, now, cid
    ))
    conn.commit()
    conn.close()
    return get_commitment_by_id(cid)

def delete_commitment(cid: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM commitments WHERE id = ?", (cid,))
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count > 0

def find_commitment_by_title_approx(search_term: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    term = f"%{search_term.strip()}%"
    cursor.execute("""
        SELECT * FROM commitments 
        WHERE status = 'PENDING' AND title LIKE ? 
        ORDER BY event_datetime ASC LIMIT 1
    """, (term,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_due_reminders(current_time_iso: str) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM commitments 
        WHERE status = 'PENDING' 
          AND reminder_status = 'PENDING' 
          AND reminder_datetime <= ?
        ORDER BY reminder_datetime ASC
    """, (current_time_iso,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def mark_reminder_sent(cid: int):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now(ARG_TZ).isoformat()
    cursor.execute("""
        UPDATE commitments 
        SET reminder_status = 'SENT', updated_at = ? 
        WHERE id = ?
    """, (now, cid))
    conn.commit()
    conn.close()
