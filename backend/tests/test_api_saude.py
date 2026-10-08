from fastapi.testclient import TestClient

from app.main import create_app


def test_saude_responde_e_informa_se_o_chat_esta_habilitado():
    with TestClient(create_app()) as cliente:
        resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok"
    assert isinstance(corpo["chat_habilitado"], bool)
