"""Bicis del usuario: descarga de Strava, tabla Bicicletas y tabla 'Mis bicis' de Estadísticas."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import toga

from bikecompfollowapp import DB_Operations
from bikecompfollowapp import app as modulo_app
from bikecompfollowapp.DB_Operations import anioDeBici, guardarBicicletas
from bikecompfollowapp.stravaConnect import StravaData

USUARIO = "memmaker650"


def bici(id_, nombre, marca=None, modelo=None, principal=False, modalidad=None):
    return {"id": id_, "nombre": nombre, "marca": marca, "modelo": modelo, "modalidad": modalidad,
            "principal": principal}


def filas(con, usuario=USUARIO):
    return con.execute("SELECT id, usuario, nombre, marca, modelo, anio, activa FROM Bicicletas "
                       "WHERE usuario = ? ORDER BY id", (usuario,)).fetchall()


def actividad(gear_id, deporte="Ride"):
    return SimpleNamespace(gear_id=gear_id, type="Ride", sport_type=deporte)


# ---- Tabla Bicicletas ----

def test_tabla_bicicletas_columnas(app):
    columnas = [f[1] for f in app.sqliteConnection.execute("PRAGMA table_info(Bicicletas)")]
    assert columnas == ["id", "usuario", "nombre", "marca", "modelo", "modalidad", "anio", "activa"]


@pytest.mark.parametrize("textos, anio", [
    (("Nerve 7.9", "Canyon Nerve 7.9 2016"), 2016), (("Slate 2019", "x"), 2019), (("Slate", "Naranjita"), None),
    ((None, None), None), (("Modelo 1234", "Bici 3000"), None),
])
def test_anio_de_bici(textos, anio):
    assert anioDeBici(*textos) == anio


def test_guardar_bicicletas(app):
    con = app.sqliteConnection
    assert guardarBicicletas(con, USUARIO, [
        bici("b1", "Cannondale Slate Naranjita", "Cannondale", "Slate"),
        bici("b2", "Canyon Nerve 7.9 2016", "Canyon", "Nerve 7.9"),
        bici("b3", "La de paseo"),                                   # sin marca ni modelo en Strava
    ]) == 3
    assert filas(con) == [
        ("b1", USUARIO, "Cannondale Slate Naranjita", "Cannondale", "Slate", None, 1),
        ("b2", USUARIO, "Canyon Nerve 7.9 2016", "Canyon", "Nerve 7.9", 2016, 1),
        ("b3", USUARIO, "La de paseo", None, "La de paseo", None, 1),
    ]


def test_bici_que_ya_no_viene_de_strava_queda_no_activa(app):
    con = app.sqliteConnection
    guardarBicicletas(con, USUARIO, [bici("b1", "A"), bici("b2", "B")])
    guardarBicicletas(con, USUARIO, [bici("b1", "A")])
    assert [(f[0], f[6]) for f in filas(con)] == [("b1", 1), ("b2", 0)]
    guardarBicicletas(con, USUARIO, [])                      # el usuario las ha retirado todas
    assert [f[6] for f in filas(con)] == [0, 0]
    guardarBicicletas(con, USUARIO, [bici("b2", "B")])       # vuelve a estar en uso
    assert [(f[0], f[6]) for f in filas(con)] == [("b1", 0), ("b2", 1)]


def test_resincronizar_no_duplica_y_respeta_el_anio_puesto_a_mano(app):
    con = app.sqliteConnection
    guardarBicicletas(con, USUARIO, [bici("b1", "Slate", "Cannondale", "Slate")])
    con.execute("UPDATE Bicicletas SET anio = 2019 WHERE id = 'b1'")
    guardarBicicletas(con, USUARIO, [bici("b1", "Slate nueva", "Cannondale", "Slate SE")])
    assert filas(con) == [("b1", USUARIO, "Slate nueva", "Cannondale", "Slate SE", 2019, 1)]


def test_las_bicis_de_otro_usuario_no_se_tocan(app):
    con = app.sqliteConnection
    guardarBicicletas(con, "otro", [bici("b9", "Suya")])
    guardarBicicletas(con, USUARIO, [bici("b1", "Mía")])
    assert filas(con, "otro") == [("b9", "otro", "Suya", None, "Suya", None, 1)]


def test_bicicletas_de_usuario_primero_las_activas(app):
    guardarBicicletas(app.sqliteConnection, USUARIO, [bici("b1", "x", "Zeta", "Z"), bici("b2", "y", "Alfa", "A")])
    guardarBicicletas(app.sqliteConnection, USUARIO, [bici("b1", "x", "Zeta", "Z"), bici("b3", "z", "Beta", "B")])
    assert app.db.bicicletasDeUsuario(USUARIO) == [
        ("b3", "Beta", "B", None, None, 1), ("b1", "Zeta", "Z", None, None, 1), ("b2", "Alfa", "A", None, None, 0)]


def test_bicicletas_de_usuario_sin_tabla_devuelve_vacio(app):
    app.sqliteConnection.execute("DROP TABLE Bicicletas")
    assert app.db.bicicletasDeUsuario(USUARIO) == []


# ---- Descarga de Strava ----

@pytest.fixture
def strava(app):
    datos = StravaData(app)
    detalles = {"b1": SimpleNamespace(name="Slate", brand_name="Cannondale", model_name="Slate", frame_type=5),
                "b2": SimpleNamespace(name="Nerve", brand_name="Canyon", model_name="Nerve 7.9", frame_type=1),
                "b4": SimpleNamespace(name="Tarmac", brand_name="Specialized", model_name="Tarmac", frame_type=None)}
    pedidos = []

    def get_gear(gid):
        pedidos.append(gid)
        if gid not in detalles:
            raise RuntimeError("no existe")
        return detalles[gid]

    datos.client = SimpleNamespace(
        get_athlete=lambda: SimpleNamespace(bikes=[
            SimpleNamespace(id="b1", name="Cannondale Slate Naranjita", primary=True),
            SimpleNamespace(id="b2", name="Canyon Nerve 7.9 2016", primary=False),
            SimpleNamespace(id="b3", name="Sin detalle", primary=False)]),
        get_gear=get_gear)
    datos.pedidos = pedidos
    return datos


def test_bicicletas_de_strava(strava):
    assert strava.bicicletas() == [
        bici("b1", "Cannondale Slate Naranjita", "Cannondale", "Slate", True, "Gravel"),
        bici("b2", "Canyon Nerve 7.9 2016", "Canyon", "Nerve 7.9", modalidad="MTB"),
        bici("b3", "Sin detalle"),                                    # get_gear falló: sin marca ni modelo
    ]
    assert strava.bicis_del_perfil is True
    assert strava.nombreEquipo("b1") == "Cannondale Slate Naranjita"
    assert strava.pedidos == ["b1", "b2", "b3"], "nombreEquipo reutiliza lo ya descargado"


def test_si_strava_no_da_el_atleta_devuelve_none(strava):
    def falla():
        raise RuntimeError("401 Unauthorized")
    strava.client.get_athlete = falla
    assert strava.bicicletas() is None


def test_atleta_sin_bicis_ni_actividades(strava):
    strava.client.get_athlete = lambda: SimpleNamespace(bikes=None)
    assert strava.bicicletas() == []
    assert strava.bicis_del_perfil is False


def test_sin_permiso_de_perfil_las_bicis_salen_de_las_actividades(strava):
    """Con el token antiguo (activity:read) /athlete no trae bicis: se toman del gear_id de las actividades."""
    strava.client.get_athlete = lambda: SimpleNamespace(bikes=[])
    strava.actividades = [actividad("b1", "GravelRide"), actividad("b2", "MountainBikeRide"),
                          actividad("g9198428", "Run"), actividad(None, "Walk"), actividad("b1", "GravelRide")]
    assert strava.bicicletas() == [
        bici("b1", "Slate", "Cannondale", "Slate", modalidad="Gravel"),
        bici("b2", "Nerve", "Canyon", "Nerve 7.9", modalidad="MTB"),
    ]
    assert strava.bicis_del_perfil is False, "Lista incompleta: no se marcan las demás como retiradas"
    assert "g9198428" not in strava.pedidos, "Las zapatillas (g...) no se consultan"


def test_bicis_del_perfil_y_de_las_actividades_se_juntan(strava):
    strava.actividades = [actividad("b4", "Ride"), actividad("b1", "GravelRide")]
    assert [b["id"] for b in strava.bicicletas()] == ["b1", "b2", "b3", "b4"]


@pytest.mark.parametrize("frame_type, modalidad", [(1, "MTB"), (2, "Gravel"), (3, "Road"), (4, "Road"), (5, "Gravel")])
def test_modalidad_segun_frame_type(strava, frame_type, modalidad):
    strava.client.get_athlete = lambda: SimpleNamespace(bikes=[SimpleNamespace(id="b9", name="X", primary=True)])
    strava.client.get_gear = lambda gid: SimpleNamespace(name="X", brand_name="M", model_name="X", frame_type=frame_type)
    assert strava.bicicletas()[0]["modalidad"] == modalidad


def test_sin_frame_type_la_modalidad_es_la_mas_usada_en_sus_actividades(strava):
    strava.client.get_athlete = lambda: SimpleNamespace(bikes=[])
    strava.actividades = [actividad("b4", "Ride"), actividad("b4", "GravelRide"), actividad("b4", "GravelRide"),
                          actividad("b4", "VirtualRide")]
    assert strava.bicicletas() == [bici("b4", "Tarmac", "Specialized", "Tarmac", modalidad="Gravel")]


def test_bici_sin_frame_type_ni_actividades_queda_sin_modalidad(strava):
    strava.client.get_athlete = lambda: SimpleNamespace(bikes=[SimpleNamespace(id="b4", name="Tarmac", primary=False)])
    assert strava.bicicletas()[0]["modalidad"] is None


def test_las_bicis_de_las_actividades_no_se_vuelven_a_pedir(strava):
    strava.client.get_athlete = lambda: SimpleNamespace(bikes=[])
    strava.actividades = [actividad("b1")]
    strava.nombreEquipo("b1")                 # lo hace guardarActividadesBDD antes
    strava.bicicletas()
    assert strava.pedidos == ["b1"]


def test_la_autorizacion_pide_el_permiso_del_perfil():
    from bikecompfollowapp import stravaConnect
    assert set(stravaConnect.SCOPE_STRAVA.split(",")) >= {"read", "activity:read_all", "profile:read_all"}
    codigo = Path(stravaConnect.__file__).read_text(encoding="utf-8")
    assert "&scope={SCOPE_STRAVA}" in codigo and "&scope=activity:read\"" not in codigo


def test_lista_incompleta_no_marca_retiradas(app):
    con = app.sqliteConnection
    guardarBicicletas(con, USUARIO, [bici("b1", "A"), bici("b2", "B")])
    guardarBicicletas(con, USUARIO, [bici("b1", "A")], marcar_retiradas=False)
    assert [f[6] for f in filas(con)] == [1, 1]


def test_modalidad_guardada_y_no_se_pierde_si_strava_no_la_da(app):
    con = app.sqliteConnection
    guardarBicicletas(con, USUARIO, [bici("b1", "A", modalidad="MTB")])
    guardarBicicletas(con, USUARIO, [bici("b1", "A", modalidad=None)])
    assert con.execute("SELECT modalidad FROM Bicicletas").fetchall() == [("MTB",)]
    guardarBicicletas(con, USUARIO, [bici("b1", "A", modalidad="Gravel")])
    assert con.execute("SELECT modalidad FROM Bicicletas").fetchall() == [("Gravel",)]


def test_modalidad_solo_admite_los_tres_valores(app):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        app.sqliteConnection.execute("INSERT INTO Bicicletas (id, modalidad) VALUES ('b1', 'Carretera')")


def test_tabla_bicicletas_sin_modalidad_se_migra(app):
    con = app.sqliteConnection
    con.execute("DROP TABLE Bicicletas")
    con.execute("CREATE TABLE Bicicletas (id TEXT PRIMARY KEY, usuario TEXT, nombre TEXT, marca TEXT, modelo TEXT, "
                "anio INTEGER, activa BOOLEAN NOT NULL DEFAULT 1)")
    con.execute("INSERT INTO Bicicletas (id, usuario, nombre) VALUES ('b1', ?, 'A')", (USUARIO,))
    DB_Operations.asegurarTablaBicicletas(con)
    assert con.execute("SELECT id, modalidad FROM Bicicletas").fetchall() == [("b1", None)]


def test_strava_sync_guarda_las_bicis(app, monkeypatch):
    class FakeStrava:
        def __init__(self, *a, **k):
            self.actividades = []
            self.sqliteConnection = app.sqliteConnection
        initConexion = crearObjetoCliente = cerrar = lambda self: None
        extraerDatos = lambda self, *a, **k: None
        guardarDatosBDD = lambda self, fecha: True
        guardarActividadesBDD = lambda self, *a, **k: 0
        quitarActividadesDuplicadas = lambda self: 0
        bicicletas = lambda self: [bici("b1", "Slate", "Cannondale", "Slate")]

    monkeypatch.setattr(modulo_app.stravaConnect, "StravaData", FakeStrava)
    app._sincronizar_strava(date(2024, 1, 1), USUARIO, "Bici Gravel")
    assert app.db.bicicletasDeUsuario(USUARIO) == [("b1", "Cannondale", "Slate", None, None, 1)]


def test_strava_sync_sin_bicis_de_strava_no_toca_las_guardadas(app, monkeypatch):
    guardarBicicletas(app.sqliteConnection, USUARIO, [bici("b1", "Slate")])

    class FakeStrava:
        def __init__(self, *a, **k):
            self.actividades = []
            self.sqliteConnection = app.sqliteConnection
        initConexion = crearObjetoCliente = cerrar = lambda self: None
        extraerDatos = lambda self, *a, **k: None
        guardarDatosBDD = lambda self, fecha: True
        guardarActividadesBDD = lambda self, *a, **k: 0
        quitarActividadesDuplicadas = lambda self: 0
        bicicletas = lambda self: None

    monkeypatch.setattr(modulo_app.stravaConnect, "StravaData", FakeStrava)
    app._sincronizar_strava(date(2024, 1, 1), USUARIO, None)
    assert [f[6] for f in filas(app.sqliteConnection)] == [1]


# ---- Tabla "Mis bicis" en Estadísticas ----

@pytest.fixture
def estadisticas(ui, db):
    db.execute("INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) VALUES ('Jorge', ?, 3, '')", (USUARIO,))
    ui.sqliteConnection.commit()
    guardarBicicletas(ui.sqliteConnection, USUARIO, [
        bici("b2", "Canyon Nerve 7.9 2016", "Canyon", "Nerve 7.9", modalidad="MTB"),
        bici("b1", "Slate", "Cannondale", "Slate", modalidad="Gravel")])
    guardarBicicletas(ui.sqliteConnection, USUARIO, [bici("b1", "Slate", "Cannondale", "Slate", modalidad="Gravel")])
    ui.construir_pantalla_tres(USUARIO)
    return ui


def test_tabla_bicis_justo_antes_de_la_de_limites(estadisticas):
    contenido = estadisticas.tabla.parent
    hijos = contenido.children
    i = hijos.index(estadisticas.tablaBicis)
    assert hijos[i - 1] is estadisticas.Title_tablaBicis
    assert hijos.index(estadisticas.Title_tablaLimites) == i + 2, "Solo el separador entre ambas"
    assert hijos.index(estadisticas.tablaModalidad) < i
    assert estadisticas.Title_tablaBicis.text == "Mis bicis"


def test_tabla_bicis_columnas_y_datos(estadisticas):
    tabla = estadisticas.tablaBicis
    assert isinstance(tabla, toga.Table)
    assert [c.heading for c in tabla.columns] == ["Id", "Marca", "Modelo", "Modalidad", "Año", "Activa"]
    assert [[getattr(f, c.accessor) for c in tabla.columns] for f in tabla.data] == [
        ["b1", "Cannondale", "Slate", "Gravel", "", "Sí"],
        ["b2", "Canyon", "Nerve 7.9", "MTB", "2016", "No"],
    ]
    assert tabla.style.height == 28 + 2 * 22


def test_tabla_bicis_vacia_sin_bicis(ui):
    ui.construir_pantalla_tres("sin_bicis")
    assert list(ui.tablaBicis.data) == []
    assert ui.tablaBicis.style.height == 28 + 22


def test_tabla_bicis_traducida(estadisticas):
    from bikecompfollowapp import translations
    translations.set_language("en")
    estadisticas.construir_pantalla_tres(USUARIO)
    assert estadisticas.Title_tablaBicis.text == "My bikes"
    assert [c.heading for c in estadisticas.tablaBicis.columns] == ["Id", "Brand", "Model", "Type", "Year", "Active"]
    assert [f.activa for f in estadisticas.tablaBicis.data] == ["Yes", "No"]


def test_tabla_bicicletas_se_crea_en_cada_arranque(tmp_path, tablas):
    bd = DB_Operations.BaseDatos.abrir(tmp_path / "x.db")
    try:
        bd.prepararTablas()
        assert "Bicicletas" in tablas(bd.conexion)
    finally:
        bd.cerrarDB()


def test_strava_sync_con_lista_incompleta_no_marca_retiradas(app, monkeypatch):
    guardarBicicletas(app.sqliteConnection, USUARIO, [bici("b1", "A"), bici("b2", "B")])

    class FakeStrava:
        bicis_del_perfil = False
        def __init__(self, *a, **k):
            self.actividades = []
            self.sqliteConnection = app.sqliteConnection
        initConexion = crearObjetoCliente = cerrar = lambda self: None
        extraerDatos = lambda self, *a, **k: None
        guardarDatosBDD = lambda self, fecha: True
        guardarActividadesBDD = lambda self, *a, **k: 0
        quitarActividadesDuplicadas = lambda self: 0
        bicicletas = lambda self: [bici("b1", "A", modalidad="Road")]

    monkeypatch.setattr(modulo_app.stravaConnect, "StravaData", FakeStrava)
    app._sincronizar_strava(date(2024, 1, 1), USUARIO, None)
    assert [(f[0], f[6]) for f in filas(app.sqliteConnection)] == [("b1", 1), ("b2", 1)]
