"""Extensiones sin una aplicación vinculada para evitar dependencias circulares."""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
