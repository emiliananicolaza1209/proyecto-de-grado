"""Festivos nacionales: Ley 51/1983 y Ley 2578/2026. Sin red; no modifica cierres."""
from datetime import date, timedelta
from functools import lru_cache

def easter(year):
    a=year%19;b=year//100;c=year%100;d=b//4;e=b%4;f=(b+8)//25
    g=(b-f+1)//3;h=(19*a+b-d-g+15)%30;i=c//4;k=c%4
    l=(32+2*e+2*i-h-k)%7;m=(a+11*h+22*l)//451
    return date(year,(h+l-7*m+114)//31,(h+l-7*m+114)%31+1)

@lru_cache(maxsize=32)
def holidays(year):
    days={}
    def add(d,name,monday=False):
        if monday:d+=timedelta(days=(-d.weekday())%7)
        days[d.isoformat()]=name
    for month,day,name in [(1,1,'Año Nuevo'),(5,1,'Día del Trabajo'),(7,20,'Independencia'),(8,7,'Batalla de Boyacá'),(12,8,'Inmaculada Concepción'),(12,25,'Navidad')]:
        add(date(year,month,day),name)
    for month,day,name in [(1,6,'Reyes Magos'),(3,19,'San José'),(6,29,'San Pedro y San Pablo'),(8,15,'Asunción'),(10,12,'Día de la Diversidad Étnica y Cultural'),(11,1,'Todos los Santos'),(11,11,'Independencia de Cartagena')]:
        add(date(year,month,day),name,True)
    for offset,name in [(-3,'Jueves Santo'),(-2,'Viernes Santo'),(43,'Ascensión'),(64,'Corpus Christi'),(71,'Sagrado Corazón')]:
        add(easter(year)+timedelta(days=offset),name)
    if year>=2026:add(date(year,7,9),'Nuestra Señora del Rosario de Chiquinquirá',True)
    return days

def day_info(value):
    d=date.fromisoformat(value)
    name=holidays(d.year).get(value)
    return dict(sunday=d.weekday()==6,holiday=bool(name),name=name or '',special=d.weekday()==6 or bool(name))
