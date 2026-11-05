"""Tests del cálculo de km por componente (ActividadesStrava -> datosComponente)."""

from datetime import date

import pytest

from bikecompfollowapp import app as modulo_app
from bikecompfollowapp.app import (
    COLUMNAS_DATOS_COMPONENTE,
    DESCRIPCION_POR_DEFECTO,
    DISTANCIA_LIMITE_DEFECTO,
    FECHA_ALTA_POR_DEFECTO,
    FECHA_INICIO_STRAVA,
    SQL_CREAR_DATOS_COMPONENTE,
    TIEMPO_LIMITE_DEFECTO,
    calcularKmComponentes,
    crearComponentesPorDefecto,
)

USUARIO = "DaMario"


@pytest.fixture
def con(app):
    """BD con el catálogo Componente vacío: así solo existen los componentes que crea cada test."""
    app.sqliteConnection.execute("DELETE FROM Componente")
    app.sqliteConnection.commit()
    return app.sqliteConnection


@pytest.fixture
def con_catalogo(app):
    return app.sqliteConnection


def alta(con, elemento, fecha="2026-03-01", usuario=USUARIO, activo=1):
    cursor = con.execute(
        "INSERT INTO archivoscomponentes (usuario, elemento, fechaInsercion, activo) VALUES (?, ?, ?, ?)",
        (usuario, elemento, fecha, activo),
    )
    con.commit()
    return cursor.lastrowid


def actividad(con, strava_id, km, fecha, tipo="Ride", usuario=USUARIO, horas=None):
    con.execute(
        "INSERT INTO ActividadesStrava (StravaID, tipo, distancia, duracion, user, fecha) VALUES (?, ?, ?, ?, ?, ?)",
        (strava_id, tipo, km, horas, usuario, fecha),
    )
    con.commit()


def km(con):
    return {fila[0]: fila[1:] for fila in con.execute(
        "SELECT componente, km, num_actividades FROM datosComponente ORDER BY componente")}


def test_tabla_datos_componente_columnas(con):
    assert {f[1] for f in con.execute("PRAGMA table_info(datosComponente)")} == COLUMNAS_DATOS_COMPONENTE


def test_suma_los_km_desde_la_fecha_de_alta_incluido_ese_dia(app, con):
    alta(con, "Cadena", "2026-03-01")
    alta(con, "Plato", "2026-04-01")
    actividad(con, 1, 20.5, "2026-02-28")      # antes de las dos altas
    actividad(con, 2, 30.0, "2026-03-01")      # el mismo día del alta de la cadena
    actividad(con, 3, 40.25, "2026-04-01")
    assert app.calcularKmComponentes(USUARIO) == 2
    assert km(con) == {"Cadena": (70.25, 2), "Plato": (40.25, 1)}


def test_solo_cuentan_las_actividades_ride(app, con):
    alta(con, "Cadena")
    for n, tipo in enumerate(["Ride", "VirtualRide", "Run", "Walk", "Workout", None], start=1):
        actividad(con, n, 10, "2026-03-10", tipo)
    app.calcularKmComponentes(USUARIO)
    assert km(con) == {"Cadena": (10.0, 1)}


def test_solo_cuentan_las_actividades_del_mismo_usuario(app, con):
    alta(con, "Cadena")
    alta(con, "Cadena", usuario="Otro")
    actividad(con, 1, 10, "2026-03-10")
    actividad(con, 2, 99, "2026-03-10", usuario="Otro")
    app.calcularKmComponentes()
    filas = dict(con.execute("SELECT usuario, km FROM datosComponente").fetchall())
    assert filas == {USUARIO: 10.0, "Otro": 99.0}


def test_actividades_sin_fecha_no_cuentan(app, con):
    alta(con, "Cadena")
    actividad(con, 1, 10, None)
    app.calcularKmComponentes(USUARIO)
    assert km(con) == {"Cadena": (0.0, 0)}


def test_componente_sin_actividades_queda_a_cero(app, con):
    alta(con, "Cadena")
    app.calcularKmComponentes(USUARIO)
    assert km(con) == {"Cadena": (0.0, 0)}


def test_recalcular_actualiza_sin_duplicar(app, con):
    id_cadena = alta(con, "Cadena")
    actividad(con, 1, 10, "2026-03-10")
    app.calcularKmComponentes(USUARIO)
    actividad(con, 2, 5, "2026-03-11")
    app.calcularKmComponentes(USUARIO)
    assert con.execute("SELECT idComponente, km, num_actividades, fecha FROM datosComponente").fetchall() == [
        (id_cadena, 15.0, 2, date.today().isoformat())
    ]


def test_calcular_un_usuario_no_toca_los_demas(app, con):
    alta(con, "Cadena")
    alta(con, "Plato", usuario="Otro")
    app.calcularKmComponentes(USUARIO)
    assert con.execute("SELECT usuario FROM datosComponente").fetchall() == [(USUARIO,)]


def test_componente_borrado_desaparece_de_datos_componente(app, con):
    id_cadena = alta(con, "Cadena")
    app.calcularKmComponentes(USUARIO)
    con.execute("DELETE FROM archivoscomponentes WHERE id = ?", (id_cadena,))
    app.calcularKmComponentes(USUARIO)
    assert con.execute("SELECT COUNT(*) FROM datosComponente").fetchone() == (0,)


def test_cada_alta_del_mismo_componente_tiene_sus_km(app, con):
    alta(con, "Cadena", "2026-01-01", activo=0)
    alta(con, "Cadena", "2026-03-01")
    actividad(con, 1, 10, "2026-02-01")
    actividad(con, 2, 20, "2026-03-05")
    app.calcularKmComponentes(USUARIO)
    assert con.execute("SELECT km, activo FROM datosComponente ORDER BY idComponente").fetchall() == [
        (30.0, 0), (20.0, 1)
    ]


def test_estructura_antigua_vacia_se_recrea(con):
    con.execute("DROP TABLE datosComponente")
    con.execute("CREATE TABLE datosComponente (id INTEGER PRIMARY KEY, nombre TEXT, fecha TEXT, activo BOOLEAN)")
    modulo_app.asegurarTablaDatosComponente(con)
    assert {f[1] for f in con.execute("PRAGMA table_info(datosComponente)")} == COLUMNAS_DATOS_COMPONENTE


def test_estructura_antigua_con_datos_se_conserva_aparte(con, tablas):
    con.execute("DROP TABLE datosComponente")
    con.execute("CREATE TABLE datosComponente (id INTEGER PRIMARY KEY, nombre TEXT)")
    con.execute("INSERT INTO datosComponente (nombre) VALUES ('viejo')")
    modulo_app.asegurarTablaDatosComponente(con)
    assert con.execute("SELECT nombre FROM datosComponente_antigua").fetchall() == [("viejo",)]
    assert {f[1] for f in con.execute("PRAGMA table_info(datosComponente)")} == COLUMNAS_DATOS_COMPONENTE


def test_crear_es_idempotente(app, con):
    alta(con, "Cadena")
    app.calcularKmComponentes(USUARIO)
    assert app.crearTablaDatosComponente() is True
    assert con.execute("SELECT COUNT(*) FROM datosComponente").fetchone() == (1,)
    assert "UNIQUE" in SQL_CREAR_DATOS_COMPONENTE


def test_error_devuelve_menos_uno(app, monkeypatch):
    import sqlite3

    def falla(*args, **kwargs):
        raise sqlite3.OperationalError("roto")
    monkeypatch.setattr(modulo_app, "calcularKmComponentes", falla)
    assert app.calcularKmComponentes(USUARIO) == -1


# ---- Integración: Estadísticas y Strava Sync ----

def test_estadisticas_muestra_km_desde_alta(app, con_catalogo):
    alta(con_catalogo, "Plato")
    actividad(con_catalogo, 1, 12.5, "2026-03-02")
    actividad(con_catalogo, 2, 7.5, "2026-01-15")    # antes del alta del Plato, después de la de POR DEFECTO
    filas = {f[0]: f for f in app.componentesEstadisticas(USUARIO)}
    assert filas["Plato"][4] == 12.5                # columna 'Km desde alta'
    assert filas["Cubierta"][1] == DESCRIPCION_POR_DEFECTO
    assert filas["Cubierta"][4] == 20.0


# ---- Componentes POR DEFECTO ----

def por_defecto(con, usuario=USUARIO):
    return [fila[0] for fila in con.execute(
        "SELECT elemento FROM archivoscomponentes WHERE usuario = ? AND descripcion = ? ORDER BY elemento",
        (usuario, DESCRIPCION_POR_DEFECTO))]


def test_crea_por_defecto_los_componentes_no_definidos(con_catalogo):
    alta(con_catalogo, "Cadena")                     # 'cadena' del catálogo ya está definida
    assert crearComponentesPorDefecto(con_catalogo, USUARIO) == 9
    nombres = por_defecto(con_catalogo)
    assert "cadena" not in nombres and "Plato" in nombres and len(nombres) == 9
    limites = {f[0]: f[1:] for f in con_catalogo.execute(
        "SELECT elemento, fechaInsercion, distanciaLimite, tiempoLimite, mesesLimite, activo "
        "FROM archivoscomponentes WHERE descripcion = ?", (DESCRIPCION_POR_DEFECTO,))}
    fecha = FECHA_ALTA_POR_DEFECTO.isoformat()
    assert limites["Plato"] == (fecha, DISTANCIA_LIMITE_DEFECTO, TIEMPO_LIMITE_DEFECTO, None, 1)
    assert limites["Cubierta"] == (fecha, 4000, TIEMPO_LIMITE_DEFECTO, None, 1)
    assert limites["pastillas freno"] == (fecha, 4000, TIEMPO_LIMITE_DEFECTO, None, 1)
    assert limites["Líquido Frenos"] == (fecha, None, None, 12, 1)


def test_cadena_por_defecto_tiene_2000_km(con_catalogo):
    crearComponentesPorDefecto(con_catalogo, USUARIO)
    assert con_catalogo.execute(
        "SELECT distanciaLimite FROM archivoscomponentes WHERE elemento = 'cadena'").fetchone() == (2000,)


def test_por_defecto_no_se_duplican(con_catalogo):
    assert crearComponentesPorDefecto(con_catalogo, USUARIO) == 10
    assert crearComponentesPorDefecto(con_catalogo, USUARIO) == 0
    assert len(por_defecto(con_catalogo)) == 10


def test_por_defecto_para_todos_los_usuarios_con_nombre(con_catalogo):
    con_catalogo.executemany(
        "INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) VALUES (?, ?, 1, '')",
        [("Ana", "ana"), ("Sin alias", None), ("Vacío", "  ")])
    assert crearComponentesPorDefecto(con_catalogo) == 10
    assert {f[0] for f in con_catalogo.execute("SELECT DISTINCT usuario FROM archivoscomponentes")} == {"ana"}


def test_strava_sync_sin_componentes_rellena_datos_componente(app, con_catalogo):
    actividad(con_catalogo, 1, 30, "2026-02-01")
    assert calcularKmComponentes(con_catalogo, USUARIO) == 10
    assert set(km(con_catalogo).values()) == {(30.0, 1)}


def test_definir_el_componente_actualiza_el_por_defecto(app, con_catalogo, campo):
    crearComponentesPorDefecto(con_catalogo, USUARIO)
    app.anadirComponente(campo("2026-06-01"), USUARIO, campo("Plato"), campo("Plato 50"), campo("SRAM"))
    filas = con_catalogo.execute(
        "SELECT elemento, descripcion, marca, fechaInsercion FROM archivoscomponentes "
        "WHERE usuario = ? AND elemento = 'Plato'", (USUARIO,)).fetchall()
    assert filas == [("Plato", "Plato 50", "SRAM", "2026-06-01")]
    assert len(por_defecto(con_catalogo)) == 9


def test_segunda_alta_de_un_componente_definido_se_inserta(app, con_catalogo, campo):
    app.anadirComponente(campo("2026-06-01"), USUARIO, campo("Plato"), campo("Plato 50"), campo("SRAM"))
    app.anadirComponente(campo("2026-08-01"), USUARIO, campo("Plato"), campo("Plato 52"), campo("SRAM"))
    assert con_catalogo.execute(
        "SELECT COUNT(*) FROM archivoscomponentes WHERE elemento = 'Plato'").fetchone() == (2,)


def test_strava_sync_calcula_los_km_tras_la_carga(app, monkeypatch):
    orden = []

    class FakeStrava:
        def __init__(self, *a, **k):
            self.actividades = [object()]
            self.sqliteConnection = app.sqliteConnection
        initConexion = crearObjetoCliente = cerrar = lambda self: None
        extraerDatos = lambda self, *a, **k: orden.append("descarga")
        guardarDatosBDD = lambda self, fecha: True
        guardarActividadesBDD = lambda self, *a, **k: orden.append("carga") or 1
        quitarActividadesDuplicadas = lambda self: orden.append("duplicados") or 0

    monkeypatch.setattr(modulo_app.stravaConnect, "StravaData", FakeStrava)
    monkeypatch.setattr(modulo_app, "calcularKmComponentes", lambda con, usuario: orden.append(("km", usuario)))
    app._sincronizar_strava(date(2026, 1, 1), USUARIO, "Bici Gravel")
    assert orden == ["descarga", "carga", "duplicados", ("km", USUARIO)]


# ---- Horas de uso ----

def test_suma_las_horas_de_uso_desde_el_alta(app, con):
    alta(con, "Cadena", "2026-03-01")
    actividad(con, 1, 20, "2026-02-28", horas=9.0)            # antes del alta
    actividad(con, 2, 30, "2026-03-01", horas=1.25)
    actividad(con, 3, 40, "2026-03-09", horas=2.5)
    actividad(con, 4, 10, "2026-03-10", tipo="Run", horas=1.0)
    actividad(con, 5, 10, "2026-03-11")                      # sin duración
    app.calcularKmComponentes(USUARIO)
    assert con.execute("SELECT km, horas, num_actividades FROM datosComponente").fetchall() == [(80.0, 3.75, 3)]


def test_componente_sin_actividades_tiene_cero_horas(app, con):
    alta(con, "Cadena")
    app.calcularKmComponentes(USUARIO)
    assert con.execute("SELECT horas FROM datosComponente").fetchall() == [(0.0,)]


def test_datos_componente_sin_horas_se_migra_conservando_filas(app, con):
    con.execute("DROP TABLE datosComponente")
    con.execute(SQL_CREAR_DATOS_COMPONENTE.replace("    horas FLOAT NOT NULL DEFAULT 0,\n", ""))
    con.execute("INSERT INTO datosComponente (idComponente, usuario, componente, km) VALUES (1, 'x', 'Plato', 12.5)")
    con.commit()
    assert "horas" not in {f[1] for f in con.execute("PRAGMA table_info(datosComponente)")}
    modulo_app.asegurarTablaDatosComponente(con)
    assert {f[1] for f in con.execute("PRAGMA table_info(datosComponente)")} == COLUMNAS_DATOS_COMPONENTE
    assert con.execute("SELECT componente, km, horas FROM datosComponente").fetchall() == [("Plato", 12.5, 0.0)]


def test_estadisticas_muestra_horas_desde_alta(app, con_catalogo):
    alta(con_catalogo, "Plato")
    actividad(con_catalogo, 1, 12.5, "2026-03-02", horas=0.75)
    filas = {f[0]: f for f in app.componentesEstadisticas(USUARIO)}
    assert filas["Plato"][5:7] == (None, 0.75)                 # Horas máx (vacío en esta alta), Horas desde alta


def test_por_defecto_existentes_reciben_los_limites_actuales(con_catalogo):
    alta(con_catalogo, "Plato")                                         # definido por el usuario: no se toca
    con_catalogo.execute("UPDATE archivoscomponentes SET distanciaLimite = 9999")
    con_catalogo.execute(
        "INSERT INTO archivoscomponentes (usuario, elemento, descripcion, fechaInsercion, distanciaLimite, tiempoLimite) "
        "VALUES (?, 'Cubierta', ?, '2026-01-01', 5000, 500)", (USUARIO, DESCRIPCION_POR_DEFECTO))
    crearComponentesPorDefecto(con_catalogo, USUARIO)
    limites = {f[0]: f[1:] for f in con_catalogo.execute(
        "SELECT elemento, distanciaLimite, tiempoLimite, mesesLimite FROM archivoscomponentes")}
    assert limites["Cubierta"] == (4000, 500, None)
    assert limites["Plato"] == (9999, None, None)


def test_por_defecto_no_dependen_de_la_fecha_de_strava_sync():
    assert FECHA_ALTA_POR_DEFECTO.isoformat() == "2026-01-01"
    assert FECHA_INICIO_STRAVA.isoformat() == "2024-01-01"
