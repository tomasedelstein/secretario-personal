import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print("=" * 60)
    print(" [SECRETARIO] INICIANDO AGENTE SECRETARIO PERSONAL POR WHATSAPP Y WEB")
    print(f" Escuchando en el puerto: {port}")
    print("=" * 60)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
