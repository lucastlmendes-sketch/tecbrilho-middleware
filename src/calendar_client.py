
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re, json

from .config import (
    get_service_account,
    CAL_POLIMENTOS_ID,
    CAL_HIGIENIZACAO_ID,
    CAL_LAVAGENS_ID,
    CAL_PELICULAS_ID,
    CAL_INSTALACOES_ID,
    CAL_MARTELINHO_ID,
    CAL_ROLE_GUARULHOS_ID,
)

EXTRACT_BLOCK=re.compile(r"\[\[AGENDAR\]\](.*?)\[\[/AGENDAR\]\]", re.DOTALL)

creds=service_account.Credentials.from_service_account_info(
    get_service_account(),
    scopes=["https://www.googleapis.com/auth/calendar"]
)
svc=build("calendar","v3",credentials=creds)

def pick_calendar(cat):
    cat=cat.lower()
    if "polimento" in cat: return CAL_POLIMENTOS_ID
    if "higien" in cat: return CAL_HIGIENIZACAO_ID
    if "lava" in cat: return CAL_LAVAGENS_ID
    if "pelic" in cat: return CAL_PELICULAS_ID
    if "instala" in cat: return CAL_INSTALACOES_ID
    if "martel" in cat: return CAL_MARTELINHO_ID
    if "role" in cat or "guarulhos" in cat: return CAL_ROLE_GUARULHOS_ID
    return CAL_POLIMENTOS_ID

def handle_agendar_block(text, phone):
    m=EXTRACT_BLOCK.search(text)
    if not m: return text
    try:
        data=json.loads(m.group(1))
        categoria=data["categoria"]
        data_str=data["data"]
        hora=data["hora_inicio"]
        dur=int(data["duracao_minutos"])
        nome=data.get("nome_cliente","")
        carro=data.get("carro","")

        dt_start=datetime.fromisoformat(f"{data_str}T{hora}:00").replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
        dt_end=dt_start+timedelta(minutes=dur)

        cal=pick_calendar(categoria)
        body={
            "summary": f"{categoria} - {nome}",
            "description": f"Cliente: {nome}\nTelefone: {phone}\nCarro: {carro}",
            "start": {"dateTime": dt_start.isoformat()},
            "end": {"dateTime": dt_end.isoformat()},
        }
        svc.events().insert(calendarId=cal, body=body).execute()
    except Exception as e:
        print("Erro agenda:",e)
    cleaned=EXTRACT_BLOCK.sub("",text).strip()
    return cleaned
