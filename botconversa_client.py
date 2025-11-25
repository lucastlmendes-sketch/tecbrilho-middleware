import logging
from typing import List, Dict, Any

# Aqui vamos apenas simular a etiquetagem.
# Se quiser realmente usar a API oficial, você pode implementar
# usando as rotas descritas em https://backend.botconversa.com.br/swagger/
# e um token de API (BOTCONVERSA_API_TOKEN).
#
# A ideia é ter a função disponível como ferramenta para o Assistente.

logger = logging.getLogger(__name__)


def tag_contact_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Função chamada pelo Assistente para etiquetar um contato.

    Espera algo como:
      {
        "contact_id": "123456",
        "tags": ["Polimento", "Lead Quente"]
      }

    No momento, apenas registra em log. Depois você pode
    implementar a chamada real à API do BotConversa.
    """
    contact_id = str(args.get("contact_id") or "")
    tags: List[str] = list(args.get("tags") or [])

    logger.info("[FAKE TAG] Etiquetando contato %s com tags: %s", contact_id, tags)

    return {
        "status": "ok",
        "contact_id": contact_id,
        "tags": tags,
        "note": "No momento isto é apenas logado no middleware.",
    }
