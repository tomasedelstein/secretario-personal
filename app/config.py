import os
import pytz
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "secretario.db"

# Timezone de Buenos Aires, Argentina
ARG_TZ = pytz.timezone("America/Argentina/Buenos_Aires")

# Clave secreta predeterminada para cifrado local de credenciales de Meta
# (Se genera una clave de 32 bytes si no existe)
SECRET_KEY = os.getenv("SECRET_KEY", "secretario_rioplatense_buenos_aires_key_2026_32b!")
