import sqlite3
import os

# Importamos desde la carpeta migrations
from migrations import apple_catalog

# Ruta exacta a la base de datos según tu estructura
DB_PATH = os.path.join("instance", "cpstore.sqlite")

def run():
    if not os.path.exists(DB_PATH):
        print(f"❌ Error: No se encontró la base de datos en '{DB_PATH}'.")
        return

    print(f"🔌 Conectando a la base de datos: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    
    try:
        print("🌱 Ejecutando seed del catálogo de Apple...")
        apple_catalog.seed(conn)
        conn.commit()
        print("✅ ¡Catálogo de Apple poblado exitosamente!")
    except Exception as e:
        print(f"❌ Ocurrió un error al poblar la base de datos: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run()