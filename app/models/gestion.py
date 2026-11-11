"""Extensiones v16. Historial y saldos nunca se borran al desactivar un catálogo."""
from ..extensions import db

class Usuario(db.Model):
    __tablename__='usuarios'
    id=db.Column(db.Integer,primary_key=True)
    nombre=db.Column(db.String(120),nullable=False)
    login=db.Column(db.String(120),nullable=False,unique=True)
    password_hash=db.Column(db.String(255),nullable=False)
    rol=db.Column(db.String(30),nullable=False)
    socio_id=db.Column(db.Integer,db.ForeignKey('socios.id'))
    activo=db.Column(db.Boolean,nullable=False,default=True)
    session_version=db.Column(db.Integer,nullable=False,default=1)

class RegistroGestion(db.Model):
    __tablename__='registro_gestion'
    id=db.Column(db.Integer,primary_key=True)
    entidad=db.Column(db.String(40),nullable=False)
    entidad_id=db.Column(db.Integer,nullable=False)
    accion=db.Column(db.String(100),nullable=False)
    motivo=db.Column(db.String(500),nullable=False)
    actor=db.Column(db.String(120),nullable=False)
    datos=db.Column(db.JSON,nullable=False)
    fecha=db.Column(db.String,server_default=db.text('CAST(CURRENT_TIMESTAMP AS TEXT)'))

class DatosProveedor(db.Model):
    __tablename__='datos_proveedor'
    proveedor_id=db.Column(db.Integer,db.ForeignKey('catalog.id'),primary_key=True)
    identificacion=db.Column(db.String(40),nullable=False,default='')
    telefono=db.Column(db.String(40),nullable=False,default='')
    correo=db.Column(db.String(120),nullable=False,default='')
    direccion=db.Column(db.String(200),nullable=False,default='')

class AliasReferencia(db.Model):
    __tablename__='alias_referencia'
    id=db.Column(db.Integer,primary_key=True)
    clave=db.Column(db.String(200),unique=True,nullable=False)
    descripcion=db.Column(db.String(200),nullable=False)
    referencia_id=db.Column(db.Integer,db.ForeignKey('catalog.id'),nullable=False)
    activo=db.Column(db.Boolean,nullable=False,default=True)

class ControlLote(db.Model):
    __tablename__='control_lote'
    lote_id=db.Column(db.Integer,db.ForeignKey('purchase_lot.id'),primary_key=True)
    estado=db.Column(db.String(20),nullable=False,default='Borrador')
    moneda=db.Column(db.String(3),nullable=False,default='USD')
    sociedad_id=db.Column(db.Integer,db.ForeignKey('sociedades.id'))
    heredado=db.Column(db.Boolean,nullable=False,default=False)
    revision=db.Column(db.Integer,nullable=False,default=1)
    __mapper_args__={'version_id_col':revision}

class LineaLote(db.Model):
    __tablename__='lineas_lote'
    id=db.Column(db.Integer,primary_key=True)
    lote_id=db.Column(db.Integer,db.ForeignKey('purchase_lot.id'),nullable=False,index=True)
    tipo=db.Column(db.String(20),nullable=False,default='Equipo')
    datos=db.Column(db.JSON,nullable=False)
    producto_id=db.Column(db.Integer,db.ForeignKey('equipment.id'))
    articulo_id=db.Column(db.Integer,db.ForeignKey('articulos_stock.id'))

class FacturaLote(db.Model):
    __tablename__='facturas_lote'
    id=db.Column(db.Integer,primary_key=True)
    lote_id=db.Column(db.Integer,db.ForeignKey('purchase_lot.id'),nullable=False)
    nombre=db.Column(db.String(200),nullable=False)
    archivo=db.Column(db.String(80),nullable=False,unique=True)
    mime=db.Column(db.String(80),nullable=False)
    sha256=db.Column(db.String(64),nullable=False)

class CategoriaStock(db.Model):
    __tablename__='categorias_stock'
    id=db.Column(db.Integer,primary_key=True)
    nombre=db.Column(db.String(120),nullable=False,unique=True)
    activa=db.Column(db.Boolean,nullable=False,default=True)

class ArticuloStock(db.Model):
    __tablename__='articulos_stock'
    id=db.Column(db.Integer,primary_key=True)
    categoria_id=db.Column(db.Integer,db.ForeignKey('categorias_stock.id'),nullable=False)
    nombre=db.Column(db.String(120),nullable=False,unique=True)
    serializado=db.Column(db.Boolean,nullable=False,default=False)
    minimo=db.Column(db.Integer,nullable=False,default=0)
    costo_administracion=db.Column(db.BigInteger,nullable=False,default=0)
    fondo=db.Column(db.String(40),nullable=False,default='CP VARIOS')
    activo=db.Column(db.Boolean,nullable=False,default=True)

class UnidadStock(db.Model):
    __tablename__='unidades_stock'
    id=db.Column(db.Integer,primary_key=True)
    articulo_id=db.Column(db.Integer,db.ForeignKey('articulos_stock.id'),nullable=False)
    serial=db.Column(db.String(100),nullable=False)
    disponible=db.Column(db.Boolean,nullable=False,default=True)
    __table_args__=(db.UniqueConstraint('articulo_id','serial'),)

class MovimientoStock(db.Model):
    __tablename__='movimientos_stock'
    id=db.Column(db.Integer,primary_key=True)
    articulo_id=db.Column(db.Integer,db.ForeignKey('articulos_stock.id'),nullable=False,index=True)
    cantidad=db.Column(db.Integer,nullable=False)
    costo_unitario=db.Column(db.BigInteger,nullable=False)
    lote_id=db.Column(db.Integer,db.ForeignKey('purchase_lot.id'))
    operacion_id=db.Column(db.Integer,db.ForeignKey('finance_operation.id'))
    unidad_id=db.Column(db.Integer,db.ForeignKey('unidades_stock.id'))
    motivo=db.Column(db.String(500),nullable=False)
    actor=db.Column(db.String(120),nullable=False)
    fecha=db.Column(db.String,server_default=db.text('CAST(CURRENT_TIMESTAMP AS TEXT)'))

class AliadoCredito(db.Model):
    __tablename__='aliados_credito'
    id=db.Column(db.Integer,primary_key=True)
    nombre=db.Column(db.String(120),nullable=False,unique=True)
    porcentaje_bp=db.Column(db.Integer,nullable=False,default=0)
    persona_id=db.Column(db.Integer,db.ForeignKey('personas_contables.id'))
    banco_id=db.Column(db.Integer,db.ForeignKey('bancos_destino.id'))
    activo=db.Column(db.Boolean,nullable=False,default=True)

class CreditoVenta(db.Model):
    __tablename__='creditos_venta'
    id=db.Column(db.Integer,primary_key=True)
    operacion_id=db.Column(db.Integer,db.ForeignKey('finance_operation.id'),nullable=False)
    indice=db.Column(db.Integer,nullable=False)
    aliado_id=db.Column(db.Integer,db.ForeignKey('aliados_credito.id'),nullable=False)
    bruto=db.Column(db.BigInteger,nullable=False)
    costo=db.Column(db.BigInteger,nullable=False)
    neto=db.Column(db.BigInteger,nullable=False)
    recibido=db.Column(db.BigInteger,nullable=False,default=0)
    condiciones=db.Column(db.JSON,nullable=False)
    estado=db.Column(db.String(20),nullable=False,default='Pendiente')
    __table_args__=(db.UniqueConstraint('operacion_id','indice'),)

class DesembolsoCredito(db.Model):
    __tablename__='desembolsos_credito'
    id=db.Column(db.Integer,primary_key=True)
    aliado_id=db.Column(db.Integer,db.ForeignKey('aliados_credito.id'),nullable=False)
    fecha=db.Column(db.String(10),nullable=False)
    monto=db.Column(db.BigInteger,nullable=False)
    persona_id=db.Column(db.Integer,db.ForeignKey('personas_contables.id'),nullable=False)
    banco_id=db.Column(db.Integer,db.ForeignKey('bancos_destino.id'),nullable=False)
    referencia=db.Column(db.String(100),nullable=False)
    consignacion_id=db.Column(db.Integer,db.ForeignKey('consignaciones_bancarias.id'),nullable=False,unique=True)
    token=db.Column(db.String(64),nullable=False,unique=True)
    activo=db.Column(db.Boolean,nullable=False,default=True)

class AplicacionCredito(db.Model):
    __tablename__='aplicaciones_credito'
    id=db.Column(db.Integer,primary_key=True)
    desembolso_id=db.Column(db.Integer,db.ForeignKey('desembolsos_credito.id'),nullable=False)
    credito_id=db.Column(db.Integer,db.ForeignKey('creditos_venta.id'),nullable=False)
    monto=db.Column(db.BigInteger,nullable=False)
    cobro_id=db.Column(db.Integer,db.ForeignKey('customer_collection.id'))
    __table_args__=(db.UniqueConstraint('desembolso_id','credito_id'),)

class Socio(db.Model):
    __tablename__='socios'
    id=db.Column(db.Integer,primary_key=True)
    nombre=db.Column(db.String(120),nullable=False,unique=True)
    activo=db.Column(db.Boolean,nullable=False,default=True)

class Sociedad(db.Model):
    __tablename__='sociedades'
    id=db.Column(db.Integer,primary_key=True)
    nombre=db.Column(db.String(120),nullable=False,unique=True)
    activa=db.Column(db.Boolean,nullable=False,default=True)

class Participacion(db.Model):
    __tablename__='participaciones_sociedad'
    id=db.Column(db.Integer,primary_key=True)
    sociedad_id=db.Column(db.Integer,db.ForeignKey('sociedades.id'),nullable=False)
    socio_id=db.Column(db.Integer,db.ForeignKey('socios.id'),nullable=False)
    capital_bp=db.Column(db.Integer,nullable=False)
    utilidad_bp=db.Column(db.Integer,nullable=False)
    aportado=db.Column(db.BigInteger,nullable=False,default=0)
    __table_args__=(db.UniqueConstraint('sociedad_id','socio_id'),)

class PropiedadEquipo(db.Model):
    __tablename__='propiedad_equipo'
    producto_id=db.Column(db.Integer,db.ForeignKey('equipment.id'),primary_key=True)
    sociedad_id=db.Column(db.Integer,db.ForeignKey('sociedades.id'))
    participaciones=db.Column(db.JSON,nullable=False)
    capital=db.Column(db.BigInteger,nullable=False)

class CompraPool(db.Model):
    __tablename__='compras_pool'
    producto_id=db.Column(db.Integer,db.ForeignKey('equipment.id'),primary_key=True)
    tipo=db.Column(db.String(30),nullable=False)
    venta_origen_id=db.Column(db.Integer,db.ForeignKey('finance_operation.id'))
    operacion_id=db.Column(db.Integer,db.ForeignKey('finance_operation.id'),nullable=False,unique=True)
    aporte=db.Column(db.BigInteger,nullable=False)
    pago_cliente=db.Column(db.BigInteger,nullable=False)
    costos_pagados=db.Column(db.BigInteger,nullable=False,default=0)
    ganancia=db.Column(db.BigInteger,nullable=False)

class ComisionPool(db.Model):
    __tablename__='comisiones_pool'
    id=db.Column(db.Integer,primary_key=True)
    operacion_id=db.Column(db.Integer,db.ForeignKey('finance_operation.id'),nullable=False,unique=True)
    monto=db.Column(db.BigInteger,nullable=False)
    reparto=db.Column(db.JSON,nullable=False)
    pago_operacion_id=db.Column(db.Integer,db.ForeignKey('finance_operation.id'),unique=True)

class ResultadoSocio(db.Model):
    __tablename__='resultados_socio'
    id=db.Column(db.Integer,primary_key=True)
    producto_id=db.Column(db.Integer,db.ForeignKey('equipment.id'),nullable=False)
    operacion_id=db.Column(db.Integer,db.ForeignKey('finance_operation.id'),nullable=False)
    sociedad_id=db.Column(db.Integer,db.ForeignKey('sociedades.id'))
    socio_id=db.Column(db.Integer,db.ForeignKey('socios.id'),nullable=False)
    capital=db.Column(db.BigInteger,nullable=False)
    utilidad=db.Column(db.BigInteger,nullable=False)
    condiciones=db.Column(db.JSON,nullable=False)
    __table_args__=(db.UniqueConstraint('operacion_id','socio_id'),)

class LiquidacionSocio(db.Model):
    __tablename__='liquidaciones_socio'
    id=db.Column(db.Integer,primary_key=True)
    socio_id=db.Column(db.Integer,db.ForeignKey('socios.id'),nullable=False)
    desde=db.Column(db.String(10),nullable=False)
    hasta=db.Column(db.String(10),nullable=False)
    fecha=db.Column(db.String(10),nullable=False)
    monto=db.Column(db.BigInteger,nullable=False)
    capital=db.Column(db.BigInteger,nullable=False,default=0)
    anticipo=db.Column(db.Boolean,nullable=False,default=False)
    fuente=db.Column(db.String(120),nullable=False)
    referencia=db.Column(db.String(150),nullable=False)
    detalle=db.Column(db.JSON,nullable=False)
    token=db.Column(db.String(64),nullable=False,unique=True)

class AplicacionLiquidacion(db.Model):
    __tablename__='aplicaciones_liquidacion'
    id=db.Column(db.Integer,primary_key=True)
    liquidacion_id=db.Column(db.Integer,db.ForeignKey('liquidaciones_socio.id'),nullable=False)
    resultado_id=db.Column(db.Integer,db.ForeignKey('resultados_socio.id'),nullable=False)
    utilidad=db.Column(db.BigInteger,nullable=False)
    capital=db.Column(db.BigInteger,nullable=False,default=0)

class DisolucionSociedad(db.Model):
    __tablename__='disoluciones_sociedad'
    id=db.Column(db.Integer,primary_key=True)
    sociedad_id=db.Column(db.Integer,db.ForeignKey('sociedades.id'),nullable=False)
    socio_id=db.Column(db.Integer,db.ForeignKey('socios.id'),nullable=False)
    producto_id=db.Column(db.Integer,db.ForeignKey('equipment.id'),nullable=False)
    fecha=db.Column(db.String(10),nullable=False)
    modalidad=db.Column(db.String(30),nullable=False)
    valor_equipo=db.Column(db.BigInteger,nullable=False)
    dinero=db.Column(db.BigInteger,nullable=False)
    detalle=db.Column(db.JSON,nullable=False)
    token=db.Column(db.String(64),nullable=False,unique=True)
