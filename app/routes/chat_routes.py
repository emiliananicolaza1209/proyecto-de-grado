"""Chat básico por reglas. La ruta solo recibe la pregunta y delega en chat_service (sin SQL, sin cálculos)."""
from flask import Blueprint, g, jsonify, request

from ..auth import require, role
from ..services import chat_service

chat = Blueprint('chat', __name__)


@chat.post('/chat/consultar')
@require('chat')
def consultar():
    usuario = getattr(g, 'usuario', None)
    try:
        resultado = chat_service.responder(role(), request.form.get('pregunta', ''),
                                           usuario=usuario.nombre if usuario else None, usuario_id=usuario.id if usuario else 0)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    respuesta = jsonify(resultado)
    respuesta.headers['Cache-Control'] = 'no-store'
    return respuesta
