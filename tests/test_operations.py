from test_actions import ActionsTests
from app.extensions import db
from app.models import Producto, Movimiento
from app.services.operacion_service import today

class OperationTests(ActionsTests):
    def start(self):
        self.pid,self.rev=self.prepare()
    def post(self,action,expected=302,**extra):
        with self.app.app_context(): rev=db.session.get(Producto,self.pid).revision
        response=self.client.post(f'/ventas/{self.pid}',data={'csrf':self.csrf,'revision':str(rev),'reason':'Prueba del movimiento','action':action,'seller':'VENDEDOR PRUEBA',**extra})
        self.assertEqual(response.status_code,expected,response.get_data(as_text=True)[:500])
        self.assertEqual(self.client.get(f'/inventario/{self.pid}').status_code,200)
    def snapshot(self):
        with self.app.app_context(): return db.session.get(Producto,self.pid).to_dict()
    def test_loan_return_sale_payments(self):
        self.start()
        for _ in range(2):
            self.post('handoff',responsible='PERSONA',purpose='Venta',due_date=today())
            self.post('handoff',200,responsible='OTRA',purpose='Venta',due_date=today())
            self.post('return',location_id=self.fields['location_id'],condition='Usado',battery='92',return_condition='Disponible')
            self.assertEqual(self.snapshot()['status'],'Disponible')
        self.post('sell',responsible='VENDEDOR',sale_value='1000')
        self.post('payment',amount='300')
        self.assertEqual(self.snapshot()['payment_status'],'Parcial')
        self.post('payment',200,amount='701')
        self.post('payment',amount='700')
        self.assertEqual(self.snapshot()['payment_status'],'Pagado')
        self.post('payment',200,amount='1')
        self.post('archive',200,confirm_imei=self.imei(1))
    def test_reservation_cancel_and_warranty(self):
        self.start()
        self.post('reserve',responsible='CLIENTE',due_date=today(),sale_value='1000')
        self.post('payment',amount='200')
        self.post('cancel',200)
        self.post('cancel',confirm_refund='1')
        self.assertEqual(self.snapshot()['paid_cents'],0)
        self.post('warranty')
        self.post('sell',200,sale_value='1000',responsible='VENDEDOR')
        self.post('close_warranty',location_id=self.fields['location_id'],condition='Nuevo')
        self.post('sell',sale_value='1000',responsible='VENDEDOR')
        self.post('warranty')
        self.post('close_warranty',location_id=self.fields['location_id'],condition='Nuevo')
        self.assertEqual(self.snapshot()['status'],'Vendido')
    def test_invalid_inputs_atomic(self):
        self.start()
        before=self.snapshot()
        for value in ['NaN','Infinity','0','-1','1.001','9999999999999999999']:
            self.post('sell',200,sale_value=value,responsible='VENDEDOR')
            self.assertEqual(before,self.snapshot())
        for date in ['2099-01-01','2026-02-30','incorrecta']:
            self.post('handoff',200,responsible='PERSONA',purpose='Venta',due_date=today(),movement_date=date)
            self.assertEqual(before,self.snapshot())
        self.post('handoff',responsible='PERSONA',purpose='Reemplazo por garantía',due_date=today())
        self.post('sell',200,sale_value='1000',responsible='VENDEDOR')
        self.post('return',200,return_condition='OTRO',location_id=self.fields['location_id'],condition='Nuevo')
        self.post('return',200,battery='101',location_id=self.fields['location_id'],condition='Nuevo')
    def test_repeat_and_date_correction(self):
        self.start()
        old=self.snapshot()['revision']
        self.post('handoff',responsible='PERSONA',purpose='Venta',due_date=today())
        response=self.client.post(f'/inventario/{self.pid}',data={'csrf':self.csrf,'revision':str(old),'action':'return','reason':'Reenvío'})
        self.assertEqual(response.status_code,200)
        self.post('correct_date',200)
        self.post('correct_date',date_reason='Confirmación de fecha',movement_date=today())
