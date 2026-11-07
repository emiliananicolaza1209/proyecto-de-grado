from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def purchase_cost(data):
    values = {}
    for key, label, maximum in [('purchase_usd', 'Compra en dólares', '1000000'),
                                ('exchange_rate', 'Precio pagado por cada dólar', '1000000'),
                                ('shipping_cop', 'Envío de este equipo', '999999999')]:
        raw = data.get(key, '').strip()
        try:
            number = Decimal(raw)
            if not number.is_finite() or number < 0 or number > Decimal(maximum):
                raise ValueError()
            if number != number.quantize(Decimal('0.01')):
                raise ValueError()
            if key != 'shipping_cop' and number == 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            raise ValueError(f'{label}: ingresa un valor válido con máximo dos decimales. Usa 0 en envío si no tiene costo.')
        values[key] = number
    subtotal = (values['purchase_usd'] * values['exchange_rate']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    total = subtotal + values['shipping_cop']
    if total > Decimal('999999999'):
        raise ValueError('El costo total supera el máximo permitido de $999.999.999 COP.')
    return values, subtotal, total


def retoma_cost(data):
    if any(str(data.get(k,'')).strip() for k in ('purchase_usd','exchange_rate','shipping_cop')):
        raise ValueError('Los equipos de retoma se compran en pesos: deja vacíos USD, TRM y envío del lote.')
    try:
        base=Decimal(str(data.get('purchase_cop','')).strip())
        if not base.is_finite() or not 0<base<=999999999 or base!=base.quantize(Decimal('.01')):
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise ValueError('Ingresa el valor pagado por el equipo en COP, con máximo dos decimales.')
    names=data.get('additional_name',[])
    amounts=data.get('additional_amount',[])
    if len(names)!=len(amounts) or len(names)>5:
        raise ValueError('Puedes agregar máximo cinco costos de comisión o reparación.')
    costs=[]
    for name,raw in zip(names,amounts):
        name=' '.join(name.upper().split())
        if not name and not raw.strip():continue
        if not 2<=len(name)<=120:raise ValueError('Describe cada costo adicional (2 a 120 caracteres).')
        try:
            amount=Decimal(raw)
            if not amount.is_finite() or not 0<amount<=999999999 or amount!=amount.quantize(Decimal('.01')):
                raise ValueError()
        except (InvalidOperation, ValueError):raise ValueError('Ingresa un costo adicional positivo válido.')
        costs.append({'name':name,'amount_cents':int(amount*100)})
    total_cents=int(base*100)+sum(x['amount_cents'] for x in costs)
    if total_cents>99999999900:raise ValueError('El costo total de la retoma excede el máximo permitido.')
    return int(base*100),costs,total_cents
