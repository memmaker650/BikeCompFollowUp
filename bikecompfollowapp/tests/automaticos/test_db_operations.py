"""Tests de DB_Operations.BaseDatos y de la separación entre pantallas (app.py) y datos (DB_Operations.py)."""

import re
import sqlite3
from pathlib import Path

import pytest

from bikecompfollowapp import DB_Operations
from bikecompfollowapp.DB_Operations import DESCRIPCION_POR_DEFECTO, BaseDatos

APP_PY = Path(DB_Operations.__file__).with_name("app.py")


@pytest.fixture
def bd(app):
    return app.db


# ---- Separación de responsabilidades ----

def test_app_py_no_tiene_sql():
    codigo = APP_PY.read_text(encoding="utf-8")
    assert not re.search(r"\.execute(many)?\(|\.commit\(\)|sqlite3\.connect|\b(SELECT|INSERT INTO|UPDATE \w+ SET|"
                         r"CREATE TABLE|DELETE FROM)\b", codigo), "Las consultas van en DB_Operations.py"


def test_la_app_usa_basedatos_sobre_su_conexion(app):
    assert isinstance(app.db, BaseDatos)
    assert app.db.conexion is app.sqliteConnection
    assert app.db is app.db, "Se reutiliza mientras la conexión sea la misma"


def test_si_cambia_la_conexion_db_la_sigue(app, tmp_path):
    otra = sqlite3.connect(tmp_path / "otra.db")
    app.sqliteConnection = otra
    try:
        assert app.db.conexion is otra
    finally:
        otra.close()


def test_abrir_crea_y_siembra_una_bd_nueva(tmp_path):
    bd = BaseDatos.abrir(tmp_path / "nueva.db")
    try:
        assert bd.nombresComponentes()[:1] and len(bd.nombresComponentes()) == 10
        assert "Bici MTB" in bd.tiposVehiculo()
    finally:
        bd.cerrarDB()


def test_preparar_tablas_crea_las_tablas_de_cada_arranque(tmp_path, tablas):
    bd = BaseDatos.abrir(tmp_path / "nueva.db")
    try:
        bd.prepararTablas()
        assert {"LimitesAlerta", "ajustes", "ActividadesStrava", "datosComponente"} <= tablas(bd.conexion)
    finally:
        bd.cerrarDB()


# ---- Lecturas para las pantallas ----

def test_usuarios_y_entradas(bd):
    assert bd.usuarios() == []
    assert bd.insertarEntrada("2026-01-01", "Jorge", "memmaker650", "Bici Gravel", "") is True
    assert bd.usuarios() == [("Jorge", "memmaker650")]
    assert bd.vehiculoDelUsuario("memmaker650") == "Bici Gravel"


def test_listas_con_valor_por_defecto_si_falla(bd):
    bd.conexion.execute("DROP TABLE tipo_vehiculo")
    assert bd.tiposVehiculo(por_defecto=["Carretera"]) == ["Carretera"]
    assert bd.leerLista("SELECT x FROM no_existe", por_defecto=("a",)) == ["a"]


def test_tipos_limite_usados_y_elementos_de_usuario(bd):
    assert bd.tiposLimiteUsados(por_defecto=["superior", "inferior"]) == ["superior", "inferior"]
    assert bd.insertarLimiteAlerta("superior", 100, "Plato") is True
    assert bd.insertarLimiteAlerta("superior", 200, "Plato") is True       # ya existe: no se duplica
    assert bd.seleccionarLimitesComponente("Plato") == [("Plato", "superior", 100)]
    assert bd.tiposLimiteUsados() == ["superior"]
    bd.guardarComponente("2026-01-01", "u", "Plato", "", "", 5000, 500, None)
    assert bd.elementosDeUsuario("u") == ["Plato"]


# ---- Escrituras ----

def test_guardar_componente_actualiza_el_por_defecto(bd):
    DB_Operations.crearComponentesPorDefecto(bd.conexion, "u")
    assert bd.guardarComponente("2026-06-01", "u", "Plato", "Plato 50", "SRAM", 5000, 500, None) is True
    filas = bd.conexion.execute("SELECT descripcion, marca FROM archivoscomponentes WHERE usuario = 'u' "
                                "AND elemento = 'Plato'").fetchall()
    assert filas == [("Plato 50", "SRAM")]
    assert bd.conexion.execute("SELECT COUNT(*) FROM archivoscomponentes WHERE descripcion = ?",
                               (DESCRIPCION_POR_DEFECTO,)).fetchone() == (9,)


def test_errores_de_escritura_devuelven_false(bd):
    bd.conexion.execute("DROP TABLE archivoscomponentes")
    bd.conexion.execute("DROP TABLE LimitesAlerta")
    bd.conexion.execute("DROP TABLE EntradasUsers")
    assert bd.guardarComponente("2026-01-01", "u", "Plato", "", "", 1, 1, None) is False
    assert bd.desactivarComponente("Plato", "u") is False
    assert bd.insertarLimiteAlerta("superior", 1, "Plato") is False
    assert bd.insertarEntrada("2026-01-01", "x", "x", "x", "x") is False
    assert bd.usuarios() == []
