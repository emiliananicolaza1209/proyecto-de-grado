"""Servidor EXCLUSIVO de pruebas UI, con datos temporales y puerto de loopback.
No utiliza .env/DATABASE_URL ni la base de Render. Nunca es el startCommand.
"""
import atexit
import secrets
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.extensions import db
from app.models import Producto, Cobro
from app.models.contabilidad import PersonaContable, BancoDestino, PersonaBanco
from werkzeug.datastructures import MultiDict
from app.services.operacion_service import today
from app.services import finanzas_service as finance


def main():
    tmp=tempfile.TemporaryDirectory(prefix='cpstore_ui_')
    app=create_app(dict(TESTING=True,DATABASE=str(Path(tmp.name)/'preview.sqlite'),
        SECRET_KEY=secrets.token_hex(32),APP_ENV='development'))
    with app.app_context():
        for i in range(24):
            sold=i%2==0
            p=Producto(imei='99000000'+str(i).zfill(7),model='PREVIEW IPHONE '+str(i),capacity=128,
                color='AZUL',condition='Nuevo',cost_cents=30000000,location='LOCAL CP STORE',
                supplier='PRUEBA UI',status='Vendido' if sold else 'Disponible',seller='PRUEBA',
                sale_value_cents=65000000 if sold else None,paid_cents=20000000 if sold else 0,
                sale_date=today() if sold else None,payment_status='Abono' if sold else 'No aplica')
            db.session.add(p)
        day=finance.open_day(today())
        day.config={**day.config,'reviewed':True,'actor':'PRUEBA UI','staff':[dict(name='PRUEBA',role='Principal',salary=0,attended=True)]};db.session.flush()
        for product in db.session.scalars(db.select(Producto).where(Producto.status=='Vendido')):
            db.session.add(Cobro(product_id=product.id,amount_cents=product.paid_cents,
                destination='Negocio',collector='PRUEBA UI',method='Efectivo',
                effective_date=today(),note='Abono inicial temporal'))
            finance.incorporate(day,product.id,secrets.token_hex(16))
        db.session.commit()
        person=PersonaContable(nombre='TITULAR PRUEBA UI',identificacion='00000001',tipo='Natural')
        bank=BancoDestino(nombre='BANCO PRUEBA UI')
        db.session.add_all([person,bank]);db.session.flush()
        db.session.add(PersonaBanco(persona_id=person.id,banco_id=bank.id));db.session.commit()
        finance.add_operation(day,MultiDict(dict(kind='Venta',description='TRANSFERENCIA TEMPORAL UI',
            seller='__other__',seller_other='PRUEBA UI',token=secrets.token_hex(16),amount='120000.25',minor_cost='',
            payment_account='TRANSFERENCIA',payment_amount='120000.25',payment_person_id=str(person.id),payment_bank_id=str(bank.id))))
        db.session.commit()
    @app.after_request
    def fixture_header(response):
        response.headers['X-CPStore-Test-Fixture']='temporary-sqlite-loopback'
        return response
    def close():
        with app.app_context():db.session.remove();db.engine.dispose()
        tmp.cleanup()
    atexit.register(close)
    app.run(host='127.0.0.1',port=5018,debug=False,use_reloader=False)


if __name__=='__main__':main()
