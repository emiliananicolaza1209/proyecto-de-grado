'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {formSignature}=require('../app/static/js/navigation.js');
test('Restituir un importe elimina cambios pendientes; otro medio sí los conserva',()=>{
 const initial=[['amount','25000'],['staff_choice','Pago sueldo|ANA'],['payment_account','EFECTIVO']];
 const changed=initial.map(row=>[...row]);changed[0][1]='10000';assert.notEqual(formSignature(changed),formSignature(initial));
 changed[0][1]='25000';assert.equal(formSignature(changed),formSignature(initial));
 changed[2][1]='TRANSFERENCIA';assert.notEqual(formSignature(changed),formSignature(initial));
});
test('Tokens no son cambios comerciales; valores repetidos no se pierden',()=>{
 assert.equal(formSignature([['csrf','a'],['token','b'],['amount','25000']]),formSignature([['csrf','x'],['token','y'],['amount','25000']]));
 assert.notEqual(formSignature([['payment_amount','10'],['payment_amount','20']]),formSignature([['payment_amount','10'],['payment_amount','30']]));
});
