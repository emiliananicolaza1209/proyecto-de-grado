"""Extensión aditiva: conserva las tablas y cierres anteriores."""
import sqlite3
from app.sqlite_resources import sqlite_connection
from pathlib import Path
from datetime import datetime

def backup_before_upgrade(path):
    p=Path(path)
    if not p.exists() or not p.stat().st_size:return
    with sqlite_connection(str(p)) as src:
        old=src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='equipment'").fetchone()
        new=src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='control_lote'").fetchone()
        if old and not new:
            target=p.parent/'respaldos';target.mkdir(exist_ok=True)
            with sqlite_connection(str(target/('antes_v16_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.sqlite'))) as dest:src.backup(dest)

def seed():
    from app.extensions import db
    from app.models import Lote
    from app.models.gestion import ControlLote,AliadoCredito,Socio
    for lot in db.session.scalars(db.select(Lote)):
        if not db.session.get(ControlLote,lot.id):
            db.session.add(ControlLote(lote_id=lot.id,estado='Confirmado',heredado=True,moneda='USD'))
    for name in ('ADDI','SISTECRÉDITO','SU+PAY','BANCO DE BOGOTÁ','IPHONE ALIADOS'):
        if not db.session.scalar(db.select(AliadoCredito.id).where(AliadoCredito.nombre==name)):
            db.session.add(AliadoCredito(nombre=name))
    if not db.session.scalar(db.select(Socio.id).limit(1)):db.session.add(Socio(nombre='JONATAN'))
    db.session.commit()
