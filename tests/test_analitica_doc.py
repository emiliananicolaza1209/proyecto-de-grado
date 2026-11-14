"""docs/ANALITICA.md: que tenga todas las secciones pedidas y que cada prueba que cita exista de verdad."""
import importlib
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOC = RAIZ / 'docs' / 'ANALITICA.md'
NOMBRE_DE_PRUEBA = re.compile(r'`(test_\w+\.\w+\.test_\w+)`')
sys.path.insert(0, str(RAIZ / 'tests'))


class DocumentoDeAnaliticaTests(unittest.TestCase):
    def setUp(self):
        self.texto = DOC.read_text(encoding='utf-8')

    def test_cada_prueba_citada_existe(self):
        citadas = sorted(set(NOMBRE_DE_PRUEBA.findall(self.texto)))
        self.assertGreaterEqual(len(citadas), 15)
        faltan = []
        for nombre in citadas:
            modulo, clase, metodo = nombre.split('.')
            try:
                if not callable(getattr(getattr(importlib.import_module(modulo), clase), metodo, None)):
                    faltan.append(nombre)
            except (ImportError, AttributeError):
                faltan.append(nombre)
        self.assertEqual(faltan, [])

    def test_tiene_las_secciones_pedidas(self):
        titulos = re.findall(r'^## (\d+)\. (.+)$', self.texto, re.M)
        self.assertEqual([int(n) for n, _ in titulos], list(range(1, 10)))
        resumen = ' '.join(t.lower() for _, t in titulos)
        for palabra in ('principios', 'contrato', 'consultas', 'límites', 'queda para después', 'modelo predictivo', 'se prueba'):
            self.assertIn(palabra, resumen)

    def test_describe_entradas_metodo_salidas_y_reglas_de_cada_consulta_nueva(self):
        for consulta in ('comparar_periodos', 'permanencia_inventario'):
            self.assertIn(consulta, self.texto)
        for pieza in ('**Entrada', '**Método', '**Salidas'):
            self.assertGreaterEqual(self.texto.count(pieza), 2, pieza)
        plano = re.sub(r'\s+', ' ', self.texto).lower()  # sin saltos de línea ni mayúsculas
        for regla in ('puntos básicos', 'cobertura completa en ambos periodos', 'es_comparacion', 'no es una predicción', 'roles_con_costo',
                      'nunca el imei', 'más** de', 'periodo anterior de igual duración'):
            self.assertIn(regla, plano, regla)

    def test_explica_la_limitacion_de_igual_duracion_frente_a_mismo_tramo_equivalente(self):
        limite = self.texto.split('## 5.')[1].split('## 6.')[0]
        self.assertIn('"Periodo anterior de igual duración" no es "mismo tramo equivalente"', limite)
        self.assertIn('lunes a miércoles', limite)
        self.assertIn('viernes a domingo', limite)
        self.assertIn('modo "equivalente"', limite)

    def test_dice_que_quedo_para_despues(self):
        despues = self.texto.split('## 6.')[1].split('## 7.')[0]
        for pendiente in ('tendencia_ventas', 'proyeccion_uvt', 'MCP', 'Alertas', 'equivalente'):
            self.assertIn(pendiente, despues, pendiente)

    def test_el_modelo_predictivo_futuro_tiene_las_seis_piezas(self):
        modelo = self.texto.split('## 7.')[1].split('## 8.')[0]
        for pieza in ('Variable a estimar', 'Historial requerido', 'Método de referencia', 'Separación temporal', 'Medida de error',
                      'Respuesta con datos insuficientes'):
            self.assertIn(pieza, modelo, pieza)
        for detalle in ('26 semanas', 'promedio móvil', 'origen móvil', 'MAE', 'sMAPE', 'sin_datos', 'ninguna cifra'):
            self.assertIn(detalle, modelo, detalle)
        self.assertIn('no está implementado', self.texto)

    def test_no_presenta_nada_propuesto_como_si_estuviera_hecho(self):
        for aun_no in ('tendencia_ventas', 'proyeccion_uvt'):
            for linea in self.texto.splitlines():
                if aun_no in linea and linea.startswith('| `'):
                    self.fail(f'{aun_no} aparece como consulta implementada en una tabla')

    def test_cita_el_chat_y_los_reportes_y_el_cuidado_con_los_datos_de_prueba(self):
        for pista in ('/chat', '/reportes/', 'redactar_respuesta', 'registro_gestion', 'demuestran que el proceso funciona'):
            self.assertIn(pista, self.texto, pista)


if __name__ == '__main__':
    unittest.main()
