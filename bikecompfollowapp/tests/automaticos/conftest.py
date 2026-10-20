"""
Fixtures comunes para los tests automáticos de BikeCompFollowApp.

Los tests no arrancan la interfaz gráfica de Toga: se crea la instancia de la
app sin llamar a su constructor y se le conecta una base de datos SQLite
temporal, de modo que nunca se tocan los datos reales del usuario.

Las pantallas se construyen con el backend de pruebas de Toga (toga_dummy), que
crea los widgets sin abrir ventanas y permite simular pulsaciones de botones.
"""

import os

os.environ["TOGA_BACKEND"] = "toga_dummy"

import sqlite3
from types import SimpleNamespace

import pytest

from bikecompfollowapp.app import AppPaths, BikeCompFollowApp


class Campo:
    """Imita un widget de Toga (TextInput, Selection, Label...) con .value/.text."""

    def __init__(self, value=None, text=""):
        self.value = value
        self.text = text
        self.style = SimpleNamespace(color=None)


@pytest.fixture
def campo():
    return Campo


@pytest.fixture
def app_paths(tmp_path):
    """Hace que AppPaths apunte a una carpeta temporal en vez de a la real."""
    fake_app = SimpleNamespace(paths=SimpleNamespace(data=tmp_path, cache=tmp_path / "cache"))
    anterior = AppPaths.app
    AppPaths.init(fake_app)
    yield tmp_path
    AppPaths.app = anterior


@pytest.fixture
def app(app_paths):
    """Instancia de la app (sin GUI) con la BD temporal ya creada y sembrada."""
    instancia = object.__new__(BikeCompFollowApp)
    instancia.label_pantalla_dos = Campo()
    instancia.label_pantalla_LimiteNuevaAlerta = Campo(text="Límites ")
    instancia.label_estado = ""
    instancia.arrancarDB()
    instancia.crearTablaAlertThresholds()
    yield instancia
    instancia.sqliteConnection.close()


@pytest.fixture
def db(app):
    """Cursor directo a la BD de la app para comprobar resultados."""
    return app.sqliteConnection.cursor()


@pytest.fixture
def tablas():
    def _tablas(conexion: sqlite3.Connection):
        filas = conexion.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {f[0] for f in filas}

    return _tablas


@pytest.fixture
def ui(app, monkeypatch):
    """App con una ventana falsa: `ui.main_window.content` es la pantalla visible."""
    # main_window es una propiedad de toga.App; se sustituye solo durante el test.
    monkeypatch.setattr(BikeCompFollowApp, "main_window", SimpleNamespace(content=None))
    return app
