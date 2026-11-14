-- Esquema SQLite de ensayo: rama Andres, versiones 1..12.

-- Origen: c6ef7c0a4592e213e9e65ba83f08754923140d8a.

-- Generado SOLO con migrations/ y app/models/ de ese commit;

-- no utiliza la base privada ni el esquema/modelos actuales.

-- Sin datos reales. Los casos insertan registros ficticios en temporales.

PRAGMA foreign_keys=ON;

CREATE TABLE admin_receipt (
            id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES customer_collection(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0), administrator TEXT NOT NULL,
            method TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '', effective_date TEXT NOT NULL,
            note TEXT NOT NULL, voided BOOLEAN NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE bancos_destino (
	id INTEGER NOT NULL,
	nombre VARCHAR(60) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (nombre)
);

CREATE TABLE catalog (
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
        normal_key TEXT NOT NULL, parent_id INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1, UNIQUE(kind,normal_key,parent_id));

CREATE TABLE consignaciones_bancarias (
	id INTEGER NOT NULL,
	persona_id INTEGER NOT NULL,
	banco_id INTEGER NOT NULL,
	monto NUMERIC(14, 2) NOT NULL,
	fecha DATETIME NOT NULL,
	referencia VARCHAR(100),
	PRIMARY KEY (id),
	FOREIGN KEY(persona_id) REFERENCES personas_contables (id),
	FOREIGN KEY(banco_id) REFERENCES bancos_destino (id)
);

CREATE TABLE correcciones_clasificacion (
            id INTEGER PRIMARY KEY, entidad TEXT NOT NULL DEFAULT 'ingreso_gasto',
            entidad_id INTEGER NOT NULL, anterior TEXT NOT NULL, nueva TEXT NOT NULL,
            motivo TEXT NOT NULL, actor TEXT NOT NULL DEFAULT 'Sesión local sin autenticación',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE customer_collection (
            id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES equipment(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            destination TEXT NOT NULL, collector TEXT NOT NULL, method TEXT NOT NULL,
            reference TEXT NOT NULL DEFAULT '', effective_date TEXT NOT NULL,
            note TEXT NOT NULL, legacy BOOLEAN NOT NULL DEFAULT 0,
            voided BOOLEAN NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE equipment (
            id INTEGER PRIMARY KEY, imei TEXT NOT NULL UNIQUE,
            model TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity > 0),
            color TEXT NOT NULL, condition TEXT NOT NULL,
            cost_cents INTEGER NOT NULL CHECK(cost_cents >= 0),
            location TEXT NOT NULL, supplier TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Disponible',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        , reference_id INTEGER REFERENCES catalog(id), color_id INTEGER REFERENCES catalog(id), capacity_id INTEGER REFERENCES catalog(id), supplier_id INTEGER REFERENCES catalog(id), location_id INTEGER REFERENCES catalog(id), purchase_usd TEXT, exchange_rate TEXT, shipping_cents INTEGER, subtotal_cents INTEGER, archived INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1, responsible TEXT, movement_date TEXT, payment_status TEXT NOT NULL DEFAULT 'No aplica', sale_value_cents INTEGER, payment_date TEXT, paid_cents INTEGER NOT NULL DEFAULT 0, purpose TEXT, due_date TEXT, battery INTEGER, warranty_previous TEXT, lot_id INTEGER REFERENCES purchase_lot(id), seller TEXT, loan_date TEXT, sale_date TEXT, last_note TEXT, warranty_until TEXT, loan_handler TEXT, loan_price_cents INTEGER);

CREATE TABLE equipment_event (
                id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES equipment(id),
                action TEXT NOT NULL, reason TEXT NOT NULL, before_data TEXT NOT NULL,
                after_data TEXT NOT NULL, actor TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE finance_audit(id INTEGER PRIMARY KEY,day_id INTEGER NOT NULL REFERENCES finance_day(id),
          action TEXT NOT NULL,reason TEXT NOT NULL,detail JSON NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE finance_day(id INTEGER PRIMARY KEY,date TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL DEFAULT 'Abierta',revision INTEGER NOT NULL DEFAULT 1,
          config JSON NOT NULL,snapshot JSON);

CREATE TABLE finance_operation(id INTEGER PRIMARY KEY,day_id INTEGER NOT NULL REFERENCES finance_day(id),
          token TEXT NOT NULL UNIQUE,kind TEXT NOT NULL,description TEXT NOT NULL,seller TEXT NOT NULL,
          amount INTEGER NOT NULL CHECK(amount>=0),minor_cost INTEGER NOT NULL DEFAULT 0 CHECK(minor_cost>=0),
          product_id INTEGER UNIQUE REFERENCES equipment(id),costs JSON NOT NULL,payments JSON NOT NULL,
          voided BOOLEAN NOT NULL DEFAULT 0);

CREATE TABLE finance_supplier_payment(id INTEGER PRIMARY KEY,day_id INTEGER NOT NULL REFERENCES finance_day(id),
          operation_id INTEGER NOT NULL REFERENCES finance_operation(id),cost_index INTEGER NOT NULL,
          amount INTEGER NOT NULL CHECK(amount>0),account TEXT NOT NULL,token TEXT NOT NULL UNIQUE);

CREATE TABLE ingresos_gastos (
            id INTEGER PRIMARY KEY, tipo TEXT NOT NULL, concepto TEXT NOT NULL,
            categoria TEXT NOT NULL DEFAULT 'OTRO', valor_cents INTEGER NOT NULL,
            fecha TEXT NOT NULL, relacion TEXT NOT NULL DEFAULT '',
            soporte_ref TEXT NOT NULL DEFAULT '', responsable TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE personas_contables (
	id INTEGER NOT NULL,
	nombre VARCHAR(120) NOT NULL,
	identificacion VARCHAR(20) NOT NULL,
	tipo VARCHAR(50) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (identificacion)
);

CREATE TABLE purchase_lot (
            id INTEGER PRIMARY KEY, entry_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            supplier_id INTEGER NOT NULL REFERENCES catalog(id), exchange_rate TEXT NOT NULL,
            expected_count INTEGER NOT NULL CHECK(expected_count > 0), note TEXT NOT NULL DEFAULT '');

CREATE TABLE reportes_generados (
            id INTEGER PRIMARY KEY, fecha_ini TEXT NOT NULL, fecha_fin TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'Sesión local sin autenticación',
            totales_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE schema_version(version INTEGER PRIMARY KEY);

CREATE INDEX ix_admin_receipt_collection_id ON admin_receipt(collection_id);

CREATE INDEX ix_customer_collection_product_id ON customer_collection(product_id);

CREATE INDEX ix_finance_operation_day_id ON finance_operation(day_id);

INSERT INTO schema_version(version) VALUES (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),(12);
