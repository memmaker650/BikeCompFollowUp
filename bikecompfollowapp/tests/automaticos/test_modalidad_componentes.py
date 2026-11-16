"""Columna obligatoria modalidad (Road / MTB / Gravel) de los componentes del usuario (archivoscomponentes)."""

import sqlite3

import pytest

from bikecompfollowapp.DB_Operations import (
    DESCRIPCION_POR_DEFECTO,
    asegurarColumnasArchivosComponentes,
    calcularKmComponentes,
    crearComponentesPorDefecto,
)

USUARIO = "memmaker650"


@pytest.fixture
def con(app):
    return app.sqliteConnection


def usuario(con, alias, vehiculo):
    con.execute("INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) VALUES (?, ?, ?, '')",
                (alias, alias, vehiculo))
    con.commit()


def alta(con, elemento, modalidad, fecha="2026-03-01", usuario_=USUARIO, descripcion="mío"):
    con.execute("INSERT INTO archivoscomponentes (usuario, elemento, modalidad, descripcion, fechaInsercion, activo) "
                "VALUES (?, ?, ?, ?, ?, 1)", (usuario_, elemento, modalidad, descripcion, fecha))
    con.commit()


def actividad(con, n, modalidad, km, fecha="2026-05-01", tipo="Ride"):
    con.execute("INSERT INTO ActividadesStrava (StravaID, tipo, Modalidad, distancia, duracion, user, fecha) "
                "VALUES (?, ?, ?, ?, 1, ?, ?)", (n, tipo, modalidad, km, USUARIO, fecha))
    con.commit()


# ---- Base de datos ----

def test_modalidad_va_tras_elemento_y_es_obligatoria(con):
    info = {f[1]: f for f in con.execute("PRAGMA table_info(archivoscomponentes)")}
    columnas = [f[1] for f in con.execute("PRAGMA table_info(archivoscomponentes)")]
    assert columnas[columnas.index("elemento") + 1] == "modalidad"
    assert info["modalidad"][3] == 1, "NOT NULL"
    assert info["modalidad"][4] is None, "Sin valor por defecto: hay que darla siempre"
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO archivoscomponentes (usuario, elemento, fechaInsercion) VALUES ('u', 'Plato', '2026-01-01')")


@pytest.mark.parametrize("valor", ["Carretera", "road", "", "BMX"])
def test_modalidad_solo_admite_road_mtb_gravel(con, valor):
    with pytest.raises(sqlite3.IntegrityError):
        alta(con, "Plato", valor)


def test_tabla_antigua_se_migra_con_la_modalidad_de_la_bici_de_cada_usuario(con):
    usuario(con, "gravelero", "Bici Gravel")
    usuario(con, "montañero", 4)                 # id de tipo_vehiculo: Bici MTB
    con.execute("DROP TABLE archivoscomponentes")
    con.execute("CREATE TABLE archivoscomponentes (id INTEGER PRIMARY KEY, usuario NOT NULL, elemento TEXT NOT NULL, "
                "descripcion TEXT, marca TEXT, fechaInsercion Date NOT NULL, distanciaLimite integer, "
                "tiempoLimite integer, activo BOOLEAN DEFAULT True, mesesLimite integer)")
    con.executemany("INSERT INTO archivoscomponentes (id, usuario, elemento, descripcion, fechaInsercion, distanciaLimite) "
                    "VALUES (?, ?, ?, ?, '2026-04-04', ?)",
                    [(4, "gravelero", "Plato", "40 Ovalado", 5000), (7, "montañero", "Cadena", "KMC", 2000),
                     (9, "sin_bici", "Cubierta", "", None)])
    con.commit()
    asegurarColumnasArchivosComponentes(con)
    asegurarColumnasArchivosComponentes(con)          # idempotente
    assert con.execute("SELECT id, usuario, elemento, modalidad, descripcion, distanciaLimite FROM archivoscomponentes "
                       "ORDER BY id").fetchall() == [
        (4, "gravelero", "Plato", "Gravel", "40 Ovalado", 5000),
        (7, "montañero", "Cadena", "MTB", "KMC", 2000),
        (9, "sin_bici", "Cubierta", "Road", "", None),
    ]
    assert "archivoscomponentes_nueva" not in {f[0] for f in con.execute("SELECT name FROM sqlite_master")}
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO archivoscomponentes (usuario, elemento, fechaInsercion) VALUES ('u', 'x', '2026-01-01')")


def test_la_migracion_conserva_los_id_de_datos_componente(con):
    alta(con, "Plato", "Road")
    calcularKmComponentes(con, USUARIO)
    ids = con.execute("SELECT id FROM archivoscomponentes").fetchall()
    assert {f[0] for f in con.execute("SELECT idComponente FROM datosComponente")} <= {i[0] for i in ids}


# ---- Escrituras ----

def test_guardar_componente_exige_modalidad_valida(app):
    for modalidad in (None, "", "Carretera"):
        assert app.db.guardarComponente("2026-01-01", USUARIO, "Plato", "", "", 1, 1, None, modalidad) is False
    assert app.db.guardarComponente("2026-01-01", USUARIO, "Plato", "", "", 1, 1, None, "MTB") is True
    assert app.sqliteConnection.execute("SELECT modalidad FROM archivoscomponentes").fetchall() == [("MTB",)]


def test_por_defecto_con_la_modalidad_de_la_bici(con):
    usuario(con, USUARIO, "Bici Gravel")
    crearComponentesPorDefecto(con, USUARIO)
    assert {f[0] for f in con.execute("SELECT DISTINCT modalidad FROM archivoscomponentes")} == {"Gravel"}


def test_definir_un_componente_de_otra_modalidad_no_pisa_el_por_defecto(app, con):
    usuario(con, USUARIO, "Bici Gravel")
    crearComponentesPorDefecto(con, USUARIO)
    assert app.db.guardarComponente("2026-06-01", USUARIO, "Plato", "MTB 32", "SRAM", 5000, 500, None, "MTB")
    assert app.db.guardarComponente("2026-06-01", USUARIO, "Plato", "Gravel 40", "SRAM", 5000, 500, None, "Gravel")
    platos = con.execute("SELECT modalidad, descripcion FROM archivoscomponentes WHERE elemento = 'Plato' "
                         "ORDER BY modalidad").fetchall()
    assert platos == [("Gravel", "Gravel 40"), ("MTB", "MTB 32")], "El POR DEFECTO de Gravel se rellena; el de MTB es nuevo"
    assert ("Plato", DESCRIPCION_POR_DEFECTO) not in con.execute("SELECT elemento, descripcion FROM archivoscomponentes")


def test_limites_por_defecto_segun_la_modalidad(app, con):
    con.execute("UPDATE Componente SET limiteRoad = 5000, limiteGravel = 4000, limiteMTB = 2500 WHERE nombre = 'Cubierta'")
    assert app.db.limitesComponente("Cubierta", USUARIO, "MTB") == (2500, 500, None)
    assert app.db.limitesComponente("Cubierta", USUARIO, "Gravel") == (4000, 500, None)


# ---- Km y horas: solo actividades de la misma modalidad ----

def test_cada_componente_suma_solo_su_modalidad(con):
    alta(con, "Cadena", "Road")
    alta(con, "Cadena", "MTB")
    actividad(con, 1, "Road", 50)
    actividad(con, 2, "MTB", 20)
    actividad(con, 3, "Gravel", 70)
    calcularKmComponentes(con, USUARIO)
    km = dict(con.execute("SELECT ac.modalidad, dc.km FROM datosComponente dc "
                          "JOIN archivoscomponentes ac ON ac.id = dc.idComponente").fetchall())
    assert km == {"Road": 50.0, "MTB": 20.0}


# ---- Pantallas ----

@pytest.fixture
def ui_usuario(ui):
    usuario(ui.sqliteConnection, USUARIO, "Bici Gravel")
    return ui


def test_estadisticas_muestra_la_modalidad_junto_al_componente(ui_usuario):
    alta(ui_usuario.sqliteConnection, "Plato", "MTB")
    ui_usuario.construir_pantalla_tres(USUARIO)
    assert [c.heading for c in ui_usuario.tabla.columns][:2] == ["Componente", "Modalidad"]
    filas = [(f.elemento, f.modalidad) for f in ui_usuario.tabla.data]
    assert ("Plato", "MTB") in filas and ("Plato", "Gravel") in filas, "Una línea por componente y modalidad"
    assert all(m in ("Road", "MTB", "Gravel") for _, m in filas)


def test_alta_componente_tiene_modalidad_de_la_bici_del_usuario(ui_usuario):
    ui_usuario.construir_pantalla_cinco(USUARIO, elemento="Plato")
    assert [i.value for i in ui_usuario.selection_modalidad.items] == ["Road", "MTB", "Gravel"]
    assert ui_usuario.selection_modalidad.value == "Gravel"


def test_alta_desde_mantenimiento_trae_la_modalidad_elegida(ui_usuario):
    ui_usuario.usuarioSeleccionado = USUARIO
    ui_usuario.ir_a_preparacion_mantenimiento()
    ui_usuario.elegir_mecanico("hoy")
    ui_usuario.elegir_modalidad_mantenimiento("MTB")
    ui_usuario.continuar_a_mantenimiento()
    ui_usuario.pulsar_boton_mantenimiento("mantenimiento", "taller.cadena")
    ui_usuario.empezar_detalles_cambiados()
    assert ui_usuario.selection_modalidad.value == "MTB"


def test_cambiar_modalidad_cambia_los_limites(ui_usuario):
    ui_usuario.sqliteConnection.execute("UPDATE Componente SET limiteRoad = 5000, limiteMTB = 2500 WHERE nombre = 'Cubierta'")
    ui_usuario.construir_pantalla_cinco(USUARIO, elemento="Cubierta", modalidad="Road")
    assert ui_usuario.distancialim_texto.value == "5000"
    ui_usuario.selection_modalidad.value = "MTB"
    assert ui_usuario.distancialim_texto.value == "2500"


def test_cargar_guarda_la_modalidad_elegida(ui_usuario):
    pantalla = ui_usuario.construir_pantalla_cinco(USUARIO, elemento="Plato", modalidad="Road")
    ui_usuario.usuarioSeleccionado = USUARIO
    ui_usuario.selection_modalidad.value = "MTB"
    import toga
    pendientes, cargar = [pantalla], None
    while pendientes:
        w = pendientes.pop(0)
        if isinstance(w, toga.Button) and w.text == "Cargar":
            cargar = w
        pendientes.extend(getattr(w, "children", None) or [])
        if isinstance(w, toga.ScrollContainer) and w.content is not None:   # p. ej. Estadísticas
            pendientes.append(w.content)
    cargar._impl.simulate_press()
    assert ui_usuario.sqliteConnection.execute(
        "SELECT elemento, modalidad FROM archivoscomponentes WHERE descripcion IS NOT ?", (DESCRIPCION_POR_DEFECTO,)
    ).fetchall() == [("Plato", "MTB")]


def test_campo_modalidad_traducido(ui_usuario):
    from bikecompfollowapp import translations
    translations.set_language("en")
    ui_usuario.construir_pantalla_cinco(USUARIO)
    caja = ui_usuario.selection_modalidad.parent
    assert caja.children[0].children[0].text == "Type of ride: "
