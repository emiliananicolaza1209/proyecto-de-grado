"""Regresión del filtro PostgreSQL y del campo de fecha de corrección."""
import os
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
import test_gestion_v16 as fixture
from app.extensions import db
from app.models import ConsignacionBancaria
from app.services.contabilidad_service import consolidar_periodo


class AccountingPublicationTests(unittest.TestCase):
    setUp=fixture.GestionTests.setUp
    tearDown=fixture.GestionTests.tearDown

    def test_range_includes_last_microsecond_and_excludes_next_day_and_voided(self):
        day=datetime.fromisoformat(self.day)
        rows=[(day,True),(day+timedelta(days=1,microseconds=-1),True),(day+timedelta(days=1),True),(day,False)]
        for timestamp,active in rows:
            db.session.add(ConsignacionBancaria(persona_id=self.person.id,banco_id=self.bank.id,monto=Decimal('100.25'),fecha=timestamp,activa=active))
        db.session.commit()
        result=consolidar_periodo(self.day,self.day)['consignaciones']
        self.assertEqual((result['count'],result['total_cents']),(2,20050))
        client=self.app.test_client();response=client.get('/modulos/tributario/')
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertNotIn('value="<time',html)
        self.assertIn('type="date" value="'+self.day+'"',html)

    def test_postgres_filter_binds_datetime_not_varchar(self):
        from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
        statements=[]
        original=db.session.query
        def capture(*entities):
            query=original(*entities)
            class Query:
                def filter(self,*clauses):
                    statements.append(str(query.filter(*clauses).statement.compile(dialect=PGDialect_psycopg())))
                    return query.filter(*clauses)
            return Query()
        with patch.object(db.session,'query',side_effect=capture):consolidar_periodo(self.day,self.day)
        sql='\n'.join(statements)
        self.assertNotIn('date(consignaciones_bancarias.fecha)',sql)
        self.assertIn('::TIMESTAMP WITHOUT TIME ZONE',sql)


@unittest.skipUnless(os.getenv('CPSTORE_TEST_PG_URL'),'Falta PostgreSQL de pruebas; no se utiliza DATABASE_URL')
class AccountingPublicationPostgresTests(AccountingPublicationTests):
    import test_postgres_integration as pg
    setUp=pg.PostgresIntegrationTests.setUp
    clean_schema=pg.PostgresIntegrationTests.clean_schema


if __name__=='__main__':unittest.main()
