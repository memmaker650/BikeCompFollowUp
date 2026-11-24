"""Tests de los límites por tipo de bici de la tabla Componente (tipoRoad/limiteRoad, Gravel, MTB)."""

import pytest

from bikecompfollowapp.DB_Operations import (
    COLUMNAS_LIMITES_COMPONENTE,
    asegurarColumnasComponente,
    crearComponentesPorDefecto,
    limitesComponente,
    tipoBici,
)

COLUMNAS = ["tipoRoad", "limiteRoad", "tipoGravel", "limiteGravel", "tipoMTB", "limiteMTB"]


@pytest.fixture
def con(app):
    return app.sqliteConnection


def usuario(con, alias, vehiculo):
    con.execute("INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) VALUES (?, ?, ?, '')",
                (alias, alias, vehiculo))
    con.commit()


def limites_de(con, nombre):
    return con.execute(f"SELECT {', '.join(COLUMNAS)} FROM Componente WHERE nombre = ?", (nombre,)).fetchone()


def test_componente_tiene_las_columnas_nuevas(con):
    columnas = {f[1]: f[2] for f in con.execute("PRAGMA table_info(Componente)")}
    assert {c: columnas[c] for c in COLUMNAS} == {
        "tipoRoad": "TEXT", "limiteRoad": "FLOAT", "tipoGravel": "TEXT", "limiteGravel": "FLOAT",
        "tipoMTB": "TEXT", "limiteMTB": "FLOAT"}
    assert set(COLUMNAS_LIMITES_COMPONENTE) == set(COLUMNAS)


@pytest.mark.parametrize("nombre, unidad, limite", [
    ("Cubierta", "km", 4000), ("cadena", "km", 2000), ("pastillas freno", "km", 4000),
    ("Líquido Frenos", "meses", 12), ("Plato", "km", 5000), ("Cámara", "km", 5000),
])
def test_bd_nueva_rellena_los_limites_iguales_para_las_tres_bicis(con, nombre, unidad, limite):
    assert limites_de(con, nombre) == (unidad, limite) * 3


def test_componente_antiguo_se_migra_y_rellena_conservando_filas(con):
    con.execute("DROP TABLE Componente")
    con.execute("CREATE TABLE Componente (id INTEGER PRIMARY KEY, nombre TEXT)")
    con.executemany("INSERT INTO Componente (nombre) VALUES (?)", [("cadena",), ("Mi pieza",)])
    asegurarColumnasComponente(con)
    asegurarColumnasComponente(con)                       # idempotente
    assert [f[0] for f in con.execute("SELECT nombre FROM Componente ORDER BY id")] == ["cadena", "Mi pieza"]
    assert limites_de(con, "cadena") == ("km", 2000) * 3
    assert limites_de(con, "Mi pieza") == ("km", 5000) * 3


def test_no_pisa_limites_ya_definidos(con):
    con.execute("UPDATE Componente SET tipoMTB = 'horas', limiteMTB = 80 WHERE nombre = 'cadena'")
    asegurarColumnasComponente(con)
    assert limites_de(con, "cadena") == ("km", 2000, "km", 2000, "horas", 80)


@pytest.mark.parametrize("vehiculo, bici", [
    ("Bici Carretera", "Road"), ("Bici Gravel", "Gravel"), ("Bici MTB", "MTB"), ("Montaña", "MTB"),
    ("Carretera", "Road"), ("Coche", "Road"), (None, "Road"),
])
def test_tipo_bici(vehiculo, bici):
    assert tipoBici(vehiculo) == bici


def test_cada_bici_usa_su_limite(con):
    con.execute("UPDATE Componente SET limiteRoad = 5000, limiteGravel = 4000, limiteMTB = 2500 WHERE nombre = 'Cubierta'")
    usuario(con, "rutero", 2)                  # id de tipo_vehiculo: Bici Carretera
    usuario(con, "gravelero", "Bici Gravel")   # tipov guardado como texto
    usuario(con, "montañero", 4)               # Bici MTB
    assert limitesComponente(con, "Cubierta", "rutero") == (5000, 500, None)
    assert limitesComponente(con, "Cubierta", "gravelero") == (4000, 500, None)
    assert limitesComponente(con, "Cubierta", "montañero") == (2500, 500, None)
    assert limitesComponente(con, "Cubierta") == (5000, 500, None), "Sin usuario: Road"


def test_unidades_horas_y_meses(con):
    con.execute("UPDATE Componente SET tipoGravel = 'horas', limiteGravel = 120 WHERE nombre = 'cadena'")
    con.execute("UPDATE Componente SET tipoGravel = 'meses', limiteGravel = 6 WHERE nombre = 'Plato'")
    usuario(con, "g", "Bici Gravel")
    assert limitesComponente(con, "cadena", "g") == (None, 120, None)
    assert limitesComponente(con, "Plato", "g") == (None, None, 6)


@pytest.mark.parametrize("nombre", ["Cubiertas", "CUBIERTA", "cubierta"])
def test_busca_el_componente_sin_mayusculas_ni_plural(con, nombre):
    con.execute("UPDATE Componente SET limiteRoad = 3500 WHERE nombre = 'Cubierta'")
    assert limitesComponente(con, nombre) == (3500, 500, None)


def test_pastillas_desde_el_boton_de_taller(con):
    con.execute("UPDATE Componente SET limiteRoad = 3000 WHERE nombre = 'pastillas freno'")
    assert limitesComponente(con, "PASTILLA/S FRENO") == (3000, 500, None)


def test_fuera_del_catalogo_usa_los_valores_del_codigo(con):
    assert limitesComponente(con, "Purgado FRENOS") == (None, None, 12)
    assert limitesComponente(con, "HORQUILLA") == (5000, 500, None)


def test_sin_unidad_en_la_tabla_usa_los_valores_del_codigo(con):
    con.execute("UPDATE Componente SET tipoRoad = NULL, limiteRoad = NULL WHERE nombre = 'cadena'")
    assert limitesComponente(con, "cadena") == (2000, 500, None)


def test_componentes_por_defecto_usan_la_bici_del_usuario(con):
    con.execute("UPDATE Componente SET limiteMTB = 1500 WHERE nombre = 'cadena'")
    usuario(con, "mtb", "Bici MTB")
    crearComponentesPorDefecto(con, "mtb")
    assert con.execute("SELECT distanciaLimite FROM archivoscomponentes WHERE usuario = 'mtb' AND elemento = 'cadena'"
                       ).fetchone() == (1500,)


def test_pantalla_alta_usa_la_bici_del_usuario(app, con):
    con.execute("UPDATE Componente SET limiteGravel = 4500 WHERE nombre = 'Cubierta'")
    usuario(con, "g", "Bici Gravel")
    app.construir_pantalla_cinco("g", elemento="Cubierta")
    assert (app.distancialim_texto.value, app.tiempolim_texto.value) == ("4500", "500")


def test_alta_con_cuadro_vacio_usa_el_limite_de_la_tabla(app, con, campo):
    con.execute("UPDATE Componente SET limiteGravel = 1800 WHERE nombre = 'cadena'")
    usuario(con, "g", "Bici Gravel")
    app.anadirComponente(campo("2026-06-01"), "g", campo("cadena"), campo(""), campo(""))
    assert con.execute("SELECT distanciaLimite FROM archivoscomponentes").fetchone() == (1800,)
