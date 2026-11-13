'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {sectionMatches}=require('../app/static/js/navigation.js');
const origin='https://cp.example';
test('El lateral distingue la sección financiera sin perder la fecha',()=>{
 assert.equal(sectionMatches('/finanzas?date=2026-10-01&tab=personal',origin+'/finanzas?date=2026-10-01&tab=personal',origin),true);
 assert.equal(sectionMatches('/finanzas?date=2026-10-01&tab=cierre',origin+'/finanzas?date=2026-10-01&tab=personal',origin),false);
 assert.equal(sectionMatches('/finanzas?tab=movimientos',origin+'/finanzas?date=2026-10-01&accion=registrar',origin),true);
 assert.equal(sectionMatches('/ventas/recepciones',origin+'/ventas/recepciones?q=990',origin),true);
 assert.equal(sectionMatches('//otro.example/finanzas',origin+'/finanzas',origin),false);
});
