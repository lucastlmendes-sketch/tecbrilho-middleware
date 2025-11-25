
import os, requests

API_TOKEN=os.getenv("BOTCONVERSA_API_TOKEN")

def add_tag(phone, tag):
    url="https://backend.botconversa.com.br/api/v1/zapier/add-tag/"
    headers={"Authorization": f"Token {API_TOKEN}", "Content-Type":"application/json"}
    payload={"phone": phone, "tag": tag}
    r=requests.post(url, json=payload, headers=headers, timeout=10)
    return r.status_code, r.text
