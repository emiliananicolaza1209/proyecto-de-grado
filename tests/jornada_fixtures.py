"""Preparación válida requerida desde V18.2 para escenarios que no prueban la apertura."""
from app.services.finanzas_service import defaults

def opening(day,names=('ANA',)):
    cfg=defaults(day)
    fields={key:str(cfg[key]/100) for key in ('normal_base','sandra_extra','extra_a','extra_b','normal_return','sandra_sunday','sandra_control_sunday','sandra_control_work','sandra_control_absent')}
    fields.update(actor='ADMIN',reviewed='1',staff_name=list(names),staff_role=['Principal']*len(names),staff_salary=['0']*len(names),staff_attended=[str(i) for i in range(len(names))])
    if cfg['holiday']:fields['holiday']='1'
    return fields
