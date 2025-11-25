
from openai import OpenAI
import time, json, re
from .config import OPENAI_API_KEY, OPENAI_ASSISTANT_ID
from .state_store import load_state, save_state
from .calendar_client import handle_agendar_block
from .botconversa_client import add_tag

client=OpenAI(api_key=OPENAI_API_KEY)

def process_message(bc_id, phone, text):
    state=load_state()
    if bc_id not in state:
        thread=client.beta.threads.create(metadata={"bc_id": bc_id})
        state[bc_id]={"thread_id": thread.id}
        save_state(state)
    thread_id=state[bc_id]["thread_id"]

    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=text,
        metadata={"phone":phone}
    )

    run=client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=OPENAI_ASSISTANT_ID,
    )

    while True:
        r=client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if r.status in ("completed","failed","cancelled","expired"):
            break
        time.sleep(1)

    msgs=client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=10)
    reply=""
    for msg in msgs.data:
        if msg.role=="assistant":
            for c in msg.content:
                if c.type=="text":
                    reply=c.text.value
            break

    # TAGS
    m=re.search(r"\[\[TAGS\]\](.*?)\[\[/TAGS\]\]", reply, re.DOTALL)
    if m:
        try:
            tags=json.loads(m.group(1).strip())
            for t in tags:
                add_tag(phone, t)
        except: pass
        reply=re.sub(r"\[\[TAGS\]\](.*?)\[\[/TAGS\]\]","",reply, flags=re.DOTALL)

    reply=handle_agendar_block(reply, phone)
    return reply
