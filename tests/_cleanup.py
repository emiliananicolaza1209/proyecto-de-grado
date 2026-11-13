"""Libera sesion y motor SQLAlchemy antes de borrar el directorio temporal (Windows bloquea el .sqlite abierto)."""
import gc
from contextlib import nullcontext

from flask import current_app, has_app_context

from app.extensions import db


def release(app):
    # La sesion de Flask-SQLAlchemy se liga al contexto de aplicacion: si el test ya
    # tiene uno activo (self.ctx) hay que limpiar en ESE contexto, no en uno anidado.
    active = has_app_context() and current_app._get_current_object() is app
    with (nullcontext() if active else app.app_context()):
        db.session.remove()
        gc.collect()  # sesiones/conexiones en ciclos de referencias aun sin liberar
        db.engine.dispose()
    gc.collect()
