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
