
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .openai_client import process_message

app=FastAPI()

@app.post("/webhook_chat")
async def webhook_chat(req: Request):
    data=await req.json()
    bc_id=str(data.get("bc_contact_id","")).strip()
    phone=str(data.get("phone","")).strip()
    msg=str(data.get("message","")).strip()

    if not msg or not bc_id:
        return JSONResponse({"resposta":{"mensagem":"Não consegui entender sua mensagem 😅"}})

    resposta=process_message(bc_id, phone, msg)
    return JSONResponse({"resposta":{"mensagem":resposta}})
