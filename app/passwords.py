"""Política de contraseñas: largo mínimo y rechazo de claves comunes o fáciles de adivinar."""
import re
import unicodedata
from functools import lru_cache

MINIMO = 12
MAXIMO = 128

# Palabras base muy usadas (sin tildes, en minúscula). Una clave cuyas letras se arman solo con estas palabras,
# aunque lleve números o símbolos intercalados ("Password-2026!"), se considera común.
BASES = frozenset('''
password pass contrasena clave claves secreto secret segura seguro fuerte nueva nuevo qwerty qwertyuiop asdfghjkl zxcvbnm abc abcdef
admin administrador administrator root user usuario login master test prueba demo
cpstore cp store cpcelulares celular celulares iphone tienda gestion inventario ventas finanzas
propietario vendedora socio contador bienvenido bienvenida welcome letmein changeme iloveyou teamo
colombia bucaramanga santander unab bogota medellin cali nacional millonarios junior futbol football
dragon monkey sunshine princess shadow superman batman hola amor dios familia mama papa
enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre
'''.split())

COMUNES = frozenset('''
123456789012 1234567890123 12345678901234 111111111111 000000000000 123123123123 123412341234
qwertyuiop12 qwertyuiop123 1q2w3e4r5t6y 1qaz2wsx3edc qazwsxedcrfv zaq12wsxcde3
'''.split())


def _normalizar(texto):
    s = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return s.lower()


@lru_cache(maxsize=None)
def _se_arma_con_bases(letras):
    if not letras:
        return True
    return any(letras.startswith(b) and _se_arma_con_bases(letras[len(b):]) for b in BASES)


def _secuencia(s):
    """Escalera de teclas o de letras/números consecutivos (abcdefghijkl, 123456789012, 987654321098)."""
    if len(s) < 6:
        return False
    pasos = {ord(b) - ord(a) for a, b in zip(s, s[1:])}
    return pasos <= {1} or pasos <= {-1}


def _repetida(s):
    if len(set(s)) <= 3:
        return True
    for n in range(1, len(s) // 2 + 1):
        if len(s) % n == 0 and s[:n] * (len(s) // n) == s:
            return True
    return False


def problema_de_clave(clave, *datos_personales):
    """Devuelve el motivo por el que la clave no sirve, o None si es aceptable."""
    clave = clave or ''
    if len(clave) < MINIMO:
        return f'La contraseña debe tener al menos {MINIMO} caracteres.'
    if len(clave) > MAXIMO:
        return f'La contraseña no puede superar {MAXIMO} caracteres.'
    norm = _normalizar(clave)
    compacta = re.sub(r'[^a-z0-9]', '', norm)
    letras = re.sub(r'[^a-z]', '', norm)
    if norm in COMUNES or compacta in COMUNES:
        return 'Esa contraseña es de las más usadas. Elige otra.'
    if _secuencia(compacta) or _repetida(compacta):
        return 'La contraseña es una secuencia o repetición fácil de adivinar. Elige otra.'
    if not letras or _se_arma_con_bases(letras):
        return 'La contraseña se arma con palabras demasiado comunes. Elige una frase o combinación propia.'
    for dato in datos_personales:
        d = re.sub(r'[^a-z0-9]', '', _normalizar(str(dato or '')))
        if len(d) >= 4 and d in compacta:
            return 'La contraseña no debe contener el usuario ni el nombre de la persona.'
    return None


def validar_clave(clave, *datos_personales):
    motivo = problema_de_clave(clave, *datos_personales)
    if motivo:
        raise ValueError(motivo)
