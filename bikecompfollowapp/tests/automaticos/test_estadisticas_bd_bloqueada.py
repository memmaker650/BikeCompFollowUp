"""Estadísticas con la BD bloqueada por otro programa (p. ej. DB Browser con cambios sin guardar)."""

import sqlite3
import time

import pytest

from bikecompfollowapp.app import COLUMNAS_COMPONENTES

USUARIO = "memmaker650"


@pytest.fixture
def otro_programa(app):
    """Segunda conexión con una escritura sin confirmar: deja la BD bloqueada para escribir."""
    otra = sqlite3.connect(app.db_path)
    otra.execute("BEGIN IMMEDIATE")
    otra.execute("UPDATE Componente SET nombre = nombre WHERE id = 1")
    yield otra
    otra.rollback()
    otra.close()


def nombres(con):
    return sorted(f[0] for f in con.execute("SELECT nombre FROM Componente"))


def test_bd_bloqueada_muestra_los_nombres_de_los_componentes(app, otro_programa):
    filas = app.db.componentesEstadisticas(USUARIO)
    assert sorted(f[0] for f in filas) == nombres(app.sqliteConnection)
    assert all(len(f) == len(COLUMNAS_COMPONENTES) for f in filas)


def test_bd_bloqueada_no_congela_la_pantalla(app, otro_programa):
    inicio = time.monotonic()
    app.db.componentesEstadisticas(USUARIO)
    assert time.monotonic() - inicio < 3, "Antes tardaba 5 s por cada escritura bloqueada"


def test_tras_estadisticas_se_recupera_la_espera_normal(app, otro_programa):
    app.db.componentesEstadisticas(USUARIO)
    assert app.sqliteConnection.execute("PRAGMA busy_timeout").fetchone() == (5000,)


def test_sin_columna_meses_limite_se_pinta_igual(app):
    con = app.sqliteConnection
    con.execute("DROP TABLE archivoscomponentes")
    con.execute("CREATE TABLE archivoscomponentes (id INTEGER PRIMARY KEY, usuario NOT NULL, elemento TEXT NOT NULL, "
                "descripcion TEXT, marca TEXT, fechaInsercion Date NOT NULL, distanciaLimite integer, "
                "tiempoLimite integer, activo BOOLEAN DEFAULT True)")
    con.execute("INSERT INTO archivoscomponentes (usuario, elemento, descripcion, fechaInsercion, activo) "
                "VALUES (?, 'Plato', 'mío', '2026-04-04', 1)", (USUARIO,))
    con.commit()
    otra = sqlite3.connect(app.db_path)       # impide que se añada la columna mesesLimite
    otra.execute("BEGIN IMMEDIATE")
    otra.execute("UPDATE Componente SET nombre = nombre WHERE id = 1")
    try:
        filas = {f[0]: f for f in app.db.componentesEstadisticas(USUARIO)}
    finally:
        otra.rollback()
        otra.close()
    assert filas["Plato"][1] == "mío"
    assert filas["Plato"][7] is None          # Meses máx: la columna aún no existe
    assert len(filas) == 10


def test_pantalla_estadisticas_con_bd_bloqueada(ui, db, otro_programa):
    ui.construir_pantalla_tres(USUARIO)
    assert len(list(ui.tabla.data)) == 10
    assert ui.label_pantalla_dos.text == "", "No se muestra error de lectura"


def test_tabla_componente_sin_columnas_nuevas_solo_usa_los_nombres(app):
    con = app.sqliteConnection
    con.execute("DROP TABLE Componente")
    con.execute('CREATE TABLE "Componente" (id INTEGER PRIMARY KEY, nombre TEXT)')
    con.executemany("INSERT INTO Componente (nombre) VALUES (?)", [("cadena",), ("Plato",)])
    con.commit()
    otra = sqlite3.connect(app.db_path)       # las columnas tipoRoad... no se pueden añadir
    otra.execute("BEGIN IMMEDIATE")
    otra.execute("UPDATE ajustes SET valor = valor")
    try:
        assert [f[0] for f in app.db.componentesEstadisticas(USUARIO)] == ["cadena", "Plato"]
    finally:
        otra.rollback()
        otra.close()
