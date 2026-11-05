"""Tests de stravaConnect.StravaData sin conectarse a Strava (red y cliente simulados)."""

import sqlite3
import time
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from bikecompfollowapp import stravaConnect
from bikecompfollowapp.stravaConnect import SQL_CREAR_ACTIVIDADES, StravaData, asegurarTablaActividades


@pytest.fixture
def strava(tmp_path):
    fake_app = SimpleNamespace(paths=SimpleNamespace(data=tmp_path))
    datos = StravaData(fake_app)
    datos.cursor.execute(
        "CREATE TABLE stravaValores (id integer PRIMARY KEY, fecha date not NULL, valor INTEGER not NULL, "
        "ascenso INTEGER, tipo TEXT not null, num_actividades INTEGER, horas INTEGER)"
    )
    yield datos
    datos.sqliteConnection.close()


def actividad(tipo="Ride", distancia=10_000, tiempo=3600, desnivel=100):
    return SimpleNamespace(type=tipo, distance=distancia, moving_time=tiempo, total_elevation_gain=desnivel)


# ---- Tokens ----

def test_guardar_y_cargar_tokens(strava, tmp_path):
    tokens = {"access_token": "a", "refresh_token": "r", "expires_at": 123}
    strava.save_tokens(tokens)
    assert (tmp_path / "strava_tokens.json").exists()
    assert strava.load_tokens() == tokens


def test_cargar_tokens_sin_fichero(strava):
    assert strava.load_tokens() is None


def test_cargar_tokens_fichero_corrupto(strava, tmp_path):
    (tmp_path / "strava_tokens.json").write_text("{no es json")
    assert strava.load_tokens() is None


def test_token_caducado(strava):
    assert strava.token_expired({"expires_at": time.time() - 10}) is True
    assert strava.token_expired({"expires_at": time.time() + 3600}) is False


def test_token_valido_no_refresca(strava, monkeypatch):
    strava.save_tokens({"access_token": "vigente", "refresh_token": "r", "expires_at": time.time() + 3600})
    monkeypatch.setattr(strava, "refresh_token", lambda *a: pytest.fail("No debería refrescar"))
    assert strava.get_valid_token() == "vigente"


def test_token_caducado_se_refresca_y_guarda(strava, monkeypatch):
    strava.save_tokens({"access_token": "viejo", "refresh_token": "r1", "expires_at": time.time() - 10})
    nuevos = {"access_token": "nuevo", "refresh_token": "r2", "expires_at": time.time() + 3600}
    llamadas = []

    def refresh(client_id, client_secret, refresh_token):
        llamadas.append(refresh_token)
        return nuevos

    monkeypatch.setattr(strava, "refresh_token", refresh)

    assert strava.get_valid_token() == "nuevo"
    assert llamadas == ["r1"]
    assert strava.load_tokens() == nuevos


def test_refresh_token_llama_a_strava(strava, monkeypatch):
    enviado = {}

    def fake_post(url, data):
        enviado.update(url=url, data=data)
        return SimpleNamespace(json=lambda: {"access_token": "x"})

    monkeypatch.setattr(stravaConnect.requests, "post", fake_post)

    assert strava.refresh_token("id", "secret", "rt") == {"access_token": "x"}
    assert enviado["url"] == "https://www.strava.com/oauth/token"
    assert enviado["data"]["grant_type"] == "refresh_token"
    assert enviado["data"]["refresh_token"] == "rt"


def test_token_en_bdd(strava):
    strava.cursor.execute("CREATE TABLE token (refresh_token TEXT)")
    assert strava.checkearTokenBDD() is False

    strava.cursor.execute("INSERT INTO token VALUES ('abc')")
    assert strava.checkearTokenBDD() is True
    assert strava.recuperarTokenBDD() == "abc"


def test_recuperar_token_sin_tabla(strava):
    assert strava.recuperarTokenBDD() == "Error"


# ---- Extracción y guardado de actividades ----

def test_extraer_datos_suma_solo_el_tipo_pedido(strava):
    strava.client = SimpleNamespace(
        get_activities=lambda after, before: [
            actividad("Ride", 20_000, 3600, 300),
            actividad("Run", 5_000, 1800, 50),
            actividad("Ride", 30_500, 5400, 450),
        ]
    )
    strava.extraerDatos(datetime(2026, 9, 1), datetime(2026, 10, 1))

    assert strava.contador == 2
    assert strava.total_actividades == 2
    assert strava.total_distancia == 50_500
    assert strava.total_tiempo == 9000
    assert strava.total_desnivel == 750


def test_extraer_datos_reinicia_totales(strava):
    strava.client = SimpleNamespace(get_activities=lambda after, before: [actividad()])
    strava.extraerDatos(datetime(2026, 9, 1), datetime(2026, 10, 1))
    strava.extraerDatos(datetime(2026, 9, 1), datetime(2026, 10, 1))
    assert strava.contador == 1
    assert strava.total_distancia == 10_000


def test_guardar_datos_bdd(strava):
    strava.total_distancia = 50_500
    strava.total_desnivel = 750.7
    strava.total_tiempo = 9000
    strava.total_actividades = 2

    strava.guardarDatosBDD("2026-09-01")

    fila = strava.cursor.execute(
        "SELECT fecha, valor, ascenso, tipo, num_actividades, horas FROM stravaValores"
    ).fetchone()
    assert fila == ("2026-09-01", 50, 750, "bike", 2, 2)


def test_imprimir_datos(strava, capsys):
    strava.contador = 3
    strava.total_distancia = 42_195
    strava.total_tiempo = 7200
    strava.total_desnivel = 321.9
    strava.imprimirDatos()

    salida = capsys.readouterr().out
    assert "Actividades: 3" in salida
    assert "Distancia (km): 42" in salida
    assert "Tiempo (horas): 2" in salida
    assert "Desnivel (m): 321" in salida


def test_chequear_datos_bdd_usa_bd_de_la_app(strava, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert strava.chequearDatosBDD("2026-09-01") is False
    strava.cursor.execute("INSERT INTO stravaValores (fecha, valor, tipo) VALUES ('2026-09-01', 1, 'bike')")
    strava.sqliteConnection.commit()
    assert strava.chequearDatosBDD("2026-09-01") is True


# ---- Misma BD que la app ----

def test_strava_usa_la_misma_bd_que_la_app(app, db):
    """Regresión: StravaData abría paths.data/dbbcfu.db en vez de BikeCFU/dbbcfu.db -> 'no such table'."""
    datos = StravaData(app)
    assert datos.sqliteConnection is app.sqliteConnection
    datos.total_distancia, datos.total_desnivel, datos.total_tiempo, datos.total_actividades = 12_000, 200, 3600, 1
    datos.guardarDatosBDD("2026-10-01")
    assert db.execute("SELECT fecha, valor FROM stravaValores").fetchall() == [("2026-10-01", 12)]
    assert datos.chequearDatosBDD("2026-10-01") is True


def test_strava_sin_db_path_usa_carpeta_bikecfu(tmp_path):
    datos = StravaData(SimpleNamespace(paths=SimpleNamespace(data=tmp_path)))
    datos.sqliteConnection.close()
    assert (tmp_path / "BikeCFU" / "dbbcfu.db").exists()
    assert not (tmp_path / "dbbcfu.db").exists()


# ---- Token en la BD ----

def test_guardar_token_bdd(strava):
    assert strava.guardarTokenBDD("abc") is True
    assert strava.guardarTokenBDD("def") is True          # sustituye, no acumula
    assert strava.cursor.execute("SELECT refresh_token FROM token").fetchall() == [("def",)]
    assert strava.checkearTokenBDD() is True


def test_guardar_token_bdd_desde_fichero(strava):
    strava.save_tokens({"access_token": "a", "refresh_token": "del_json", "expires_at": 1})
    assert strava.guardarTokenBDD() is True
    assert strava.recuperarTokenBDD() == "del_json"


def test_guardar_token_bdd_sin_token(strava):
    assert strava.guardarTokenBDD() is False
    assert strava.checkearTokenBDD() is False


def test_actualizar_token_bdd(strava):
    strava.cursor.execute("CREATE TABLE token (refresh_token TEXT)")
    strava.cursor.execute("INSERT INTO token VALUES ('viejo')")
    assert strava.actualizarTokenBDD("nuevo") is True
    assert strava.recuperarTokenBDD() == "nuevo"


def test_actualizar_token_bdd_sin_tabla_lo_inserta(strava):
    assert strava.actualizarTokenBDD("primero") is True
    assert strava.recuperarTokenBDD() == "primero"


def test_recuperar_token_tabla_vacia(strava):
    strava.crearTablaToken()
    assert strava.recuperarTokenBDD() == "Error"


# ---- Strava Sync guarda el token en la BD ----

def test_save_tokens_guarda_refresh_token_en_bdd(strava):
    strava.save_tokens({"access_token": "a", "refresh_token": "r1", "expires_at": 1})
    assert strava.recuperarTokenBDD() == "r1"


def test_refrescar_token_actualiza_la_bdd(strava, monkeypatch):
    strava.save_tokens({"access_token": "viejo", "refresh_token": "r1", "expires_at": time.time() - 10})
    monkeypatch.setattr(strava, "refresh_token", lambda *a: {
        "access_token": "nuevo", "refresh_token": "r2", "expires_at": time.time() + 3600})
    assert strava.get_valid_token() == "nuevo"
    assert strava.cursor.execute("SELECT refresh_token FROM token").fetchall() == [("r2",)]


def test_respuesta_erronea_de_strava_no_sobrescribe_tokens(strava, monkeypatch):
    buenos = {"access_token": "viejo", "refresh_token": "r1", "expires_at": time.time() - 10}
    strava.save_tokens(buenos)
    monkeypatch.setattr(strava, "refresh_token", lambda *a: {"message": "Bad Request", "errors": []})
    with pytest.raises(RuntimeError):
        strava.get_valid_token()
    assert strava.load_tokens() == buenos
    assert strava.recuperarTokenBDD() == "r1"


def test_sin_fichero_se_recupera_con_el_token_de_la_bdd(strava, monkeypatch):
    strava.guardarTokenBDD("de_la_bd")
    pedidos = []

    def refresh(client_id, client_secret, refresh_token):
        pedidos.append(refresh_token)
        return {"access_token": "acc", "refresh_token": "rotado", "expires_at": time.time() + 3600}

    monkeypatch.setattr(strava, "refresh_token", refresh)
    tokens = strava.tokens_desde_bdd()
    assert pedidos == ["de_la_bd"]
    assert tokens["access_token"] == "acc"
    assert strava.load_tokens() == tokens            # se regenera strava_tokens.json
    assert strava.recuperarTokenBDD() == "rotado"


def test_sin_fichero_ni_bdd_no_hay_tokens(strava):
    assert strava.tokens_desde_bdd() is None


def test_crear_cliente_usa_bdd_sin_pedir_oauth(strava, monkeypatch):
    strava.guardarTokenBDD("de_la_bd")
    monkeypatch.setattr(strava, "refresh_token", lambda *a: {
        "access_token": "acc", "refresh_token": "r2", "expires_at": time.time() + 3600})
    monkeypatch.setattr(strava, "get_strava_code", lambda *a: pytest.fail("No debería pedir OAuth"))
    usados = []

    class FakeClient:
        def __init__(self, access_token=None):
            usados.append(access_token)
        def authorization_url(self, **kw):
            return "url"
        def get_athlete(self):
            return SimpleNamespace(firstname="Test")

    monkeypatch.setattr(stravaConnect, "Client", FakeClient)
    strava.crearObjetoCliente()
    assert usados[-1] == "acc"


def test_oauth_inicial_guarda_token_en_bdd(strava, monkeypatch):
    monkeypatch.setattr(strava, "get_strava_code", lambda *a: "code")
    monkeypatch.setattr(strava, "get_tokens", lambda *a: {
        "access_token": "acc", "refresh_token": "inicial", "expires_at": time.time() + 3600})

    class FakeClient:
        def __init__(self, access_token=None):
            pass
        def authorization_url(self, **kw):
            return "url"
        def get_athlete(self):
            return SimpleNamespace(firstname="Test")

    monkeypatch.setattr(stravaConnect, "Client", FakeClient)
    strava.crearObjetoCliente()
    assert strava.recuperarTokenBDD() == "inicial"


def test_token_vigente_se_copia_a_la_bdd_si_falta(strava, monkeypatch, tmp_path):
    import json
    (tmp_path / "strava_tokens.json").write_text(json.dumps(
        {"access_token": "a", "refresh_token": "vigente", "expires_at": time.time() + 3600}))
    monkeypatch.setattr(strava, "refresh_token", lambda *a: pytest.fail("No debería refrescar"))
    assert strava.get_valid_token() == "a"
    assert strava.recuperarTokenBDD() == "vigente"


# ---- Tabla ActividadesStrava ----

from stravalib.model import SummaryActivity  # noqa: E402


def actividad_strava(id_, tipo="Ride", metros=42_195.0, segundos=5400, desnivel=512.3, ms=7.8, gear="b1",
                     fecha="2026-03-15T23:30:00", deporte=None):
    """deporte = sport_type de Strava; si no se indica, el mismo que tipo."""
    return SummaryActivity(id=id_, type=tipo, sport_type=deporte or tipo, distance=metros, moving_time=segundos,
                           total_elevation_gain=desnivel, average_speed=ms, gear_id=gear,
                           start_date_local=fecha)


@pytest.fixture
def strava_app(app):
    datos = StravaData(app)
    datos.client = SimpleNamespace(get_gear=lambda gid: SimpleNamespace(name=f"Bici {gid}"))
    return datos   # comparte la conexión de la app; la cierra el fixture app


def test_tabla_actividades_strava_columnas(app, tablas):
    assert "ActividadesStrava" in tablas(app.sqliteConnection)
    columnas = {fila[1]: fila[2] for fila in app.sqliteConnection.execute("PRAGMA table_info(ActividadesStrava)")}
    assert columnas == {
        "id": "INTEGER", "StravaID": "INTEGER", "tipo": "TEXT", "Modalidad": "TEXT", "distancia": "FLOAT", "altimetria": "FLOAT", "duracion": "FLOAT",
        "velocidad_media": "FLOAT", "tipo_vehiculo": "TEXT", "elemento": "TEXT", "user": "TEXT",
        "fecha": "TEXT",
    }


def test_guardar_actividades_con_unidades(strava_app, db):
    assert strava_app.guardarActividadesBDD("DaMario", "Bici Gravel", [actividad_strava(111)]) == 1
    assert db.execute("SELECT * FROM ActividadesStrava").fetchall() == [
        (1, 111, "Ride", "Road", "2026-03-15", 42.2, 512.3, 1.5, 28.08, "Bici Gravel", "Bici b1", "DaMario")
    ]


def test_sincronizar_otra_vez_no_duplica_y_actualiza(strava_app, db):
    strava_app.guardarActividadesBDD("DaMario", "Bici Gravel", [actividad_strava(111), actividad_strava(222, "Run")])
    strava_app.guardarActividadesBDD("DaMario", "Bici Gravel", [actividad_strava(111, metros=50_000.0)])
    assert db.execute("SELECT StravaID, tipo, distancia FROM ActividadesStrava ORDER BY StravaID").fetchall() == [
        (111, "Ride", 50.0), (222, "Run", 42.2)
    ]


def test_equipo_se_consulta_una_vez_y_falla_sin_romper(strava_app, db):
    pedidos = []

    def get_gear(gid):
        pedidos.append(gid)
        if gid == "roto":
            raise RuntimeError("404")
        return SimpleNamespace(name="Canyon")

    strava_app.client = SimpleNamespace(get_gear=get_gear)
    strava_app.guardarActividadesBDD("u", None, [actividad_strava(1), actividad_strava(2), actividad_strava(3, gear="roto"),
                                                 actividad_strava(4, gear=None)])
    assert pedidos == ["b1", "roto"]
    assert db.execute("SELECT StravaID, elemento FROM ActividadesStrava ORDER BY StravaID").fetchall() == [
        (1, "Canyon"), (2, "Canyon"), (3, "roto"), (4, None)
    ]


def test_extraer_datos_guarda_todas_las_actividades_y_totaliza_solo_ride(strava_app, db):
    acts = [actividad_strava(1, "Ride", 20_000.0), actividad_strava(2, "Run", 5_000.0)]
    strava_app.client.get_activities = lambda after, before: acts
    strava_app.extraerDatos(datetime(2026, 9, 1), datetime(2026, 10, 1))
    assert strava_app.total_distancia == 20_000
    assert strava_app.guardarActividadesBDD("u") == 2
    assert db.execute("SELECT COUNT(*) FROM ActividadesStrava").fetchone() == (2,)


@pytest.mark.parametrize("tipov, esperado", [("Bici Gravel", "Bici Gravel"), (4, "Bici MTB")])
def test_vehiculo_del_usuario(app, db, tipov, esperado):
    db.execute("INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) VALUES ('N', 'DaMario', ?, '')", (tipov,))
    assert app.vehiculoDelUsuario("DaMario") == esperado
    assert app.vehiculoDelUsuario("nadie") is None


def test_strava_sync_guarda_actividades_del_usuario(app, db, monkeypatch):
    db.execute("INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) VALUES ('N', 'DaMario', 'Bici Carretera', '')")
    app.usuarioSeleccionado = "DaMario"
    monkeypatch.setattr(StravaData, "initConexion", lambda self: None)

    def cliente(self):
        self.client = SimpleNamespace(get_activities=lambda after, before: [actividad_strava(7)],
                                      get_gear=lambda gid: SimpleNamespace(name="Specialized"))

    monkeypatch.setattr(StravaData, "crearObjetoCliente", cliente)
    app._sincronizar_strava(date(2026, 1, 1), "DaMario", app.vehiculoDelUsuario("DaMario"))
    assert db.execute("SELECT StravaID, tipo_vehiculo, elemento, user FROM ActividadesStrava").fetchall() == [
        (7, "Bici Carretera", "Specialized", "DaMario")
    ]


@pytest.mark.parametrize("tipo, vehiculo", [
    ("Ride", "Bici Gravel"),
    ("VirtualRide", "Bici Gravel"),
    ("Run", None),
    ("Walk", None),
])
def test_run_y_walk_sin_tipo_vehiculo(strava_app, db, tipo, vehiculo):
    strava_app.guardarActividadesBDD("DaMario", "Bici Gravel", [actividad_strava(1, tipo)])
    assert db.execute("SELECT tipo, tipo_vehiculo FROM ActividadesStrava").fetchone() == (tipo, vehiculo)


def test_resincronizar_run_pone_tipo_vehiculo_a_null(strava_app, db):
    """Si ya había una carrera guardada con vehículo (carga anterior), al sincronizar queda en NULL."""
    db.execute("INSERT INTO ActividadesStrava (StravaID, tipo, tipo_vehiculo) VALUES (1, 'Run', 'Bici Gravel')")
    strava_app.guardarActividadesBDD("DaMario", "Bici Gravel", [actividad_strava(1, "Run")])
    assert db.execute("SELECT tipo_vehiculo FROM ActividadesStrava").fetchone() == (None,)


# ---- Sin duplicados al sincronizar otra vez ----

def _resumen(strava, km=1959, actividades=62):
    strava.total_distancia, strava.total_desnivel = km * 1000, 21484
    strava.total_tiempo, strava.total_actividades = 107 * 3600, actividades


def test_resumen_dos_veces_el_mismo_dia_no_duplica(strava):
    _resumen(strava, 1959, 62)
    assert strava.guardarDatosBDD(datetime(2026, 11, 4, 12, 46)) is True
    _resumen(strava, 2000, 63)
    assert strava.guardarDatosBDD(datetime(2026, 11, 4, 13, 59)) is True
    assert strava.cursor.execute("SELECT fecha, valor, num_actividades FROM stravaValores").fetchall() == [
        ("2026-11-04", 2000, 63)                       # una sola fila, con los datos más recientes
    ]


def test_resumen_otro_dia_es_otra_fila(strava):
    _resumen(strava)
    strava.guardarDatosBDD(datetime(2026, 11, 3, 10))
    strava.guardarDatosBDD(datetime(2026, 11, 4, 10))
    assert strava.cursor.execute("SELECT COUNT(*) FROM stravaValores").fetchone() == (2,)


def test_limpieza_de_duplicados_existentes(app, db):
    """Los datos reales tenían 3 filas iguales del mismo día (ids 3, 4, 5): se queda la última."""
    db.executemany("INSERT INTO stravaValores (id, fecha, valor, ascenso, tipo, num_actividades, horas) "
                   "VALUES (?, ?, ?, 0, 'bike', ?, 0)", [
                       (1, "2026-04-08 16:11:17.573605", 630, 21),
                       (2, "2026-06-12 15:19:45.962987", 1122, 36),
                       (3, "2026-11-04 12:46:32.730802", 1959, 62),
                       (4, "2026-11-04 12:47:16.578879", 1959, 62),
                       (5, "2026-11-04 13:59:58.149971", 1959, 62),
                   ])
    assert app.limpiarDuplicadosStrava() is True
    assert app.limpiarDuplicadosStrava() is True       # idempotente
    assert db.execute("SELECT id, fecha, valor FROM stravaValores ORDER BY id").fetchall() == [
        (1, "2026-04-08", 630), (2, "2026-06-12", 1122), (5, "2026-11-04", 1959)
    ]
    with pytest.raises(sqlite3.IntegrityError):         # la BD ya no admite duplicados
        db.execute("INSERT INTO stravaValores (fecha, valor, tipo) VALUES ('2026-11-04', 1, 'bike')")


def test_chequear_datos_acepta_datetime(strava):
    _resumen(strava)
    strava.guardarDatosBDD(datetime(2026, 11, 4, 12, 46))
    assert strava.chequearDatosBDD(datetime(2026, 11, 4, 20, 0)) is True


def test_sincronizar_dos_veces_completo_no_duplica_nada(app, db, monkeypatch):
    db.execute("INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) VALUES ('N', 'DaMario', 'Bici Gravel', '')")
    app.usuarioSeleccionado = "DaMario"
    monkeypatch.setattr(StravaData, "initConexion", lambda self: None)

    def cliente(self):
        self.client = SimpleNamespace(
            get_activities=lambda after, before: [actividad_strava(1), actividad_strava(2, "Run"), actividad_strava(1)],
            get_gear=lambda gid: SimpleNamespace(name="Canyon"))

    monkeypatch.setattr(StravaData, "crearObjetoCliente", cliente)
    app._sincronizar_strava(date(2026, 1, 1), "DaMario", "Bici Gravel")
    app._sincronizar_strava(date(2026, 1, 1), "DaMario", "Bici Gravel")
    assert db.execute("SELECT COUNT(*) FROM ActividadesStrava").fetchone() == (2,)
    assert db.execute("SELECT COUNT(*) FROM stravaValores").fetchone() == (1,)


# ---- Columna StravaID ----

def test_stravaid_es_el_id_de_strava_e_id_es_interno(strava_app, db):
    strava_app.guardarActividadesBDD("u", None, [actividad_strava(16_000_000_001), actividad_strava(16_000_000_002)])
    strava_app.guardarActividadesBDD("u", None, [actividad_strava(16_000_000_001, metros=1000.0)])
    assert db.execute("SELECT id, StravaID, distancia FROM ActividadesStrava ORDER BY id").fetchall() == [
        (1, 16_000_000_001, 1.0), (2, 16_000_000_002, 42.2)      # actualizada, no duplicada, mismo id
    ]


def test_stravaid_unico_y_obligatorio(app, db):
    db.execute("INSERT INTO ActividadesStrava (StravaID, tipo) VALUES (5, 'Ride')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO ActividadesStrava (StravaID, tipo) VALUES (5, 'Ride')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO ActividadesStrava (tipo) VALUES ('Ride')")


def test_migracion_tabla_antigua_sin_stravaid(tmp_path):
    conexion = sqlite3.connect(tmp_path / "antigua.db")
    conexion.execute("""CREATE TABLE ActividadesStrava (id INTEGER PRIMARY KEY, tipo TEXT, distancia FLOAT,
        altimetria FLOAT, duracion FLOAT, velocidad_media FLOAT, tipo_vehiculo TEXT, elemento TEXT, user TEXT)""")
    conexion.executemany("INSERT INTO ActividadesStrava VALUES (?, ?, ?, 0, 0, 0, ?, 'Canyon', 'DaMario')", [
        (17_200_000_002, "Run", 10.0, None), (17_100_000_001, "Ride", 50.0, "Bici Gravel")])
    conexion.commit()

    stravaConnect.asegurarTablaActividades(conexion)
    stravaConnect.asegurarTablaActividades(conexion)          # idempotente

    assert conexion.execute("SELECT id, StravaID, tipo, distancia, tipo_vehiculo FROM ActividadesStrava "
                            "ORDER BY id").fetchall() == [
        (1, 17_100_000_001, "Ride", 50.0, "Bici Gravel"),
        (2, 17_200_000_002, "Run", 10.0, None),
    ]
    tablas = {f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "ActividadesStrava_antigua" not in tablas
    conexion.close()


# ---- Quitar actividades duplicadas ----

@pytest.fixture
def tabla_sin_unique(tmp_path):
    """ActividadesStrava sin la restricción UNIQUE, para poder tener duplicados."""
    conexion = sqlite3.connect(tmp_path / "dups.db")
    conexion.execute("CREATE TABLE ActividadesStrava (id INTEGER PRIMARY KEY, StravaID INTEGER, tipo TEXT, user TEXT)")
    yield conexion
    conexion.close()


def test_quita_duplicados_mismo_stravaid_y_usuario_deja_id_menor(tabla_sin_unique):
    tabla_sin_unique.executemany("INSERT INTO ActividadesStrava (id, StravaID, tipo, user) VALUES (?, ?, 'Ride', ?)", [
        (1, 100, "DaMario"),
        (2, 200, "DaMario"),
        (3, 100, "DaMario"),     # duplicada de 1 -> se borra
        (4, 100, "Lucía"),       # mismo StravaID pero otro usuario -> se queda
        (5, 200, "DaMario"),     # duplicada de 2 -> se borra
        (6, 100, "DaMario"),     # duplicada de 1 -> se borra
        (7, 300, None),
        (8, 300, None),          # mismo StravaID, ambos sin usuario -> se borra
    ])
    assert stravaConnect.quitarActividadesDuplicadas(tabla_sin_unique) == 4
    assert tabla_sin_unique.execute("SELECT id, StravaID, user FROM ActividadesStrava ORDER BY id").fetchall() == [
        (1, 100, "DaMario"), (2, 200, "DaMario"), (4, 100, "Lucía"), (7, 300, None)
    ]
    assert stravaConnect.quitarActividadesDuplicadas(tabla_sin_unique) == 0     # idempotente


def test_quitar_duplicados_sin_duplicados_no_borra(strava_app, db):
    strava_app.guardarActividadesBDD("DaMario", None, [actividad_strava(1), actividad_strava(2)])
    assert strava_app.quitarActividadesDuplicadas() == 0
    assert db.execute("SELECT COUNT(*) FROM ActividadesStrava").fetchone() == (2,)


def test_quitar_duplicados_se_ejecuta_tras_la_carga(app, monkeypatch):
    orden = []
    monkeypatch.setattr(StravaData, "initConexion", lambda self: None)
    monkeypatch.setattr(StravaData, "crearObjetoCliente", lambda self: setattr(self, "client", SimpleNamespace(
        get_activities=lambda after, before: [actividad_strava(1)], get_gear=lambda gid: SimpleNamespace(name="x"))))
    original = StravaData.guardarActividadesBDD
    monkeypatch.setattr(StravaData, "guardarActividadesBDD", lambda self, *a, **k: orden.append("carga") or original(self, *a, **k))
    monkeypatch.setattr(StravaData, "quitarActividadesDuplicadas", lambda self: orden.append("duplicados") or 0)
    app._sincronizar_strava(date(2026, 1, 1), "DaMario", None)
    assert orden == ["carga", "duplicados"]


# ---- Columna fecha de ActividadesStrava ----

def test_fecha_es_el_dia_local_de_la_actividad(strava_app, db):
    strava_app.guardarActividadesBDD("DaMario", "Bici Gravel", [actividad_strava(1, fecha="2026-05-02T00:15:00")])
    assert db.execute("SELECT fecha FROM ActividadesStrava").fetchone() == ("2026-05-02",)


def test_actividad_sin_fecha_no_borra_la_guardada(strava_app, db):
    strava_app.guardarActividadesBDD("DaMario", None, [actividad_strava(1)])
    strava_app.guardarActividadesBDD("DaMario", None, [actividad_strava(1, fecha=None)])
    assert db.execute("SELECT fecha FROM ActividadesStrava").fetchone() == ("2026-03-15",)


def test_tabla_sin_fecha_se_migra_y_resincronizar_la_rellena(strava_app, db):
    conexion = strava_app.sqliteConnection
    conexion.execute("DROP TABLE ActividadesStrava")
    conexion.execute(SQL_CREAR_ACTIVIDADES.replace(",\n    fecha TEXT", ""))
    conexion.execute("INSERT INTO ActividadesStrava (StravaID, tipo, distancia, user) VALUES (7, 'Ride', 10, 'DaMario')")
    conexion.commit()
    asegurarTablaActividades(conexion)
    assert db.execute("SELECT StravaID, distancia, fecha FROM ActividadesStrava").fetchall() == [(7, 10.0, None)]
    strava_app.guardarActividadesBDD("DaMario", None, [actividad_strava(7, metros=10_000.0)])
    assert db.execute("SELECT StravaID, fecha FROM ActividadesStrava").fetchall() == [(7, "2026-03-15")]


# ---- Columna Modalidad (MTB / Gravel / Road / NULL) ----

def test_modalidad_va_justo_despues_de_tipo(app):
    columnas = [f[1] for f in app.sqliteConnection.execute("PRAGMA table_info(ActividadesStrava)")]
    assert columnas[columnas.index("tipo") + 1] == "Modalidad"


@pytest.mark.parametrize("tipo, deporte, modalidad", [
    ("Ride", "MountainBikeRide", "MTB"),      # Bicicleta de montaña
    ("EBikeRide", "EMountainBikeRide", "MTB"),
    ("Ride", "GravelRide", "Gravel"),         # Bicicleta de gravilla
    ("Ride", "Ride", "Road"),                 # Bicicleta de carretera
    ("EBikeRide", "EBikeRide", "Road"),
    ("Run", "Run", None), ("Run", "TrailRun", None), ("Walk", "Walk", None), ("Hike", "Hike", None),
    ("Workout", "Workout", None), ("WeightTraining", "WeightTraining", None), ("VirtualRide", "VirtualRide", None),
])
def test_modalidad_segun_el_deporte_de_strava(strava_app, db, tipo, deporte, modalidad):
    strava_app.guardarActividadesBDD("DaMario", "Bici Gravel", [actividad_strava(1, tipo, deporte=deporte)])
    assert db.execute("SELECT tipo, Modalidad FROM ActividadesStrava").fetchone() == (tipo, modalidad)


def test_modalidad_sin_sport_type_usa_type(strava_app, db):
    actividad = SummaryActivity(id=5, type="Ride", distance=1000.0, moving_time=60, start_date_local="2026-03-01T10:00:00")
    strava_app.guardarActividadesBDD("DaMario", None, [actividad])
    assert db.execute("SELECT Modalidad FROM ActividadesStrava").fetchone() == ("Road",)


def test_modalidad_solo_admite_los_tres_valores_o_null(app):
    con = app.sqliteConnection
    con.execute("INSERT INTO ActividadesStrava (StravaID, Modalidad) VALUES (1, NULL)")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO ActividadesStrava (StravaID, Modalidad) VALUES (2, 'Carretera')")


def test_resincronizar_actualiza_la_modalidad(strava_app, db):
    strava_app.guardarActividadesBDD("DaMario", None, [actividad_strava(1, deporte="Ride")])
    strava_app.guardarActividadesBDD("DaMario", None, [actividad_strava(1, deporte="GravelRide")])
    assert db.execute("SELECT Modalidad FROM ActividadesStrava").fetchall() == [("Gravel",)]


def test_tabla_sin_modalidad_se_rehace_conservando_filas(strava_app, db):
    conexion = strava_app.sqliteConnection
    conexion.execute("DROP TABLE ActividadesStrava")
    conexion.execute(SQL_CREAR_ACTIVIDADES.replace(
        "    Modalidad TEXT CHECK (Modalidad IN ('MTB', 'Gravel', 'Road')),\n", ""))
    conexion.execute("INSERT INTO ActividadesStrava (id, StravaID, tipo, distancia, user, fecha) "
                     "VALUES (4, 77, 'Ride', 33.3, 'DaMario', '2026-02-02')")
    conexion.commit()
    asegurarTablaActividades(conexion)
    asegurarTablaActividades(conexion)                       # idempotente
    columnas = [f[1] for f in conexion.execute("PRAGMA table_info(ActividadesStrava)")]
    assert columnas[columnas.index("tipo") + 1] == "Modalidad"
    assert db.execute("SELECT id, StravaID, tipo, Modalidad, distancia, user, fecha FROM ActividadesStrava").fetchall() == [
        (4, 77, "Ride", None, 33.3, "DaMario", "2026-02-02")]
    assert "ActividadesStrava_antigua" not in {f[0] for f in conexion.execute("SELECT name FROM sqlite_master")}


# ---- tipo_vehiculo según la modalidad ----

@pytest.mark.parametrize("tipo, deporte, vehiculo", [
    ("Ride", "MountainBikeRide", "Bici MTB"),     # MTB: siempre Bici MTB
    ("EBikeRide", "EMountainBikeRide", "Bici MTB"),
    ("Ride", "GravelRide", "Bici Gravel"),        # resto: el vehículo del usuario
    ("Ride", "Ride", "Bici Gravel"),
    ("Workout", "Workout", "Bici Gravel"),
    ("Run", "Run", None),                         # sin vehículo
    ("Walk", "Walk", None),
])
def test_tipo_vehiculo_segun_modalidad(strava_app, db, tipo, deporte, vehiculo):
    strava_app.guardarActividadesBDD("DaMario", "Bici Gravel", [actividad_strava(1, tipo, deporte=deporte)])
    assert db.execute("SELECT tipo_vehiculo FROM ActividadesStrava").fetchone() == (vehiculo,)


def test_mtb_es_bici_mtb_aunque_el_usuario_no_tenga_vehiculo(strava_app, db):
    strava_app.guardarActividadesBDD("DaMario", None, [actividad_strava(1, deporte="MountainBikeRide")])
    assert db.execute("SELECT Modalidad, tipo_vehiculo FROM ActividadesStrava").fetchone() == ("MTB", "Bici MTB")


def test_bici_mtb_existe_en_tipo_vehiculo(db):
    assert db.execute("SELECT COUNT(*) FROM tipo_vehiculo WHERE vehiculo = 'Bici MTB'").fetchone() == (1,)


# ---- Columna fecha tras Modalidad ----

def test_fecha_va_justo_despues_de_modalidad(app):
    columnas = [f[1] for f in app.sqliteConnection.execute("PRAGMA table_info(ActividadesStrava)")]
    assert columnas[columnas.index("Modalidad") + 1] == "fecha"
    assert columnas[:5] == ["id", "StravaID", "tipo", "Modalidad", "fecha"]


def test_fecha_al_final_se_mueve_tras_modalidad_conservando_filas(strava_app, db):
    conexion = strava_app.sqliteConnection
    conexion.execute("DROP TABLE ActividadesStrava")
    conexion.execute("""CREATE TABLE ActividadesStrava (id INTEGER PRIMARY KEY AUTOINCREMENT,
        StravaID INTEGER NOT NULL UNIQUE, tipo TEXT, Modalidad TEXT, distancia FLOAT, altimetria FLOAT,
        duracion FLOAT, velocidad_media FLOAT, tipo_vehiculo TEXT, elemento TEXT, user TEXT, fecha TEXT)""")
    conexion.executemany("INSERT INTO ActividadesStrava (id, StravaID, tipo, Modalidad, distancia, user, fecha) "
                         "VALUES (?, ?, 'Ride', ?, ?, 'DaMario', ?)",
                         [(3, 30, "MTB", 10.5, "2025-01-01"), (9, 90, "Road", 20.0, "2026-02-02")])
    conexion.commit()
    asegurarTablaActividades(conexion)
    asegurarTablaActividades(conexion)
    columnas = [f[1] for f in conexion.execute("PRAGMA table_info(ActividadesStrava)")]
    assert columnas[:5] == ["id", "StravaID", "tipo", "Modalidad", "fecha"]
    assert db.execute("SELECT id, StravaID, Modalidad, fecha, distancia FROM ActividadesStrava ORDER BY id").fetchall() == [
        (3, 30, "MTB", "2025-01-01", 10.5), (9, 90, "Road", "2026-02-02", 20.0)]
    # el autoincremento sigue después del id mayor
    strava_app.guardarActividadesBDD("DaMario", None, [actividad_strava(100)])
    assert db.execute("SELECT id FROM ActividadesStrava WHERE StravaID = 100").fetchone() == (10,)


def test_columna_propia_no_se_pierde(strava_app, db):
    conexion = strava_app.sqliteConnection
    conexion.execute("ALTER TABLE ActividadesStrava ADD COLUMN notas TEXT")
    conexion.execute("INSERT INTO ActividadesStrava (StravaID, notas) VALUES (1, 'mía')")
    conexion.commit()
    asegurarTablaActividades(conexion)
    assert db.execute("SELECT notas FROM ActividadesStrava").fetchone() == ("mía",)


def test_fecha_viene_de_strava_start_date_local(strava_app, db):
    strava_app.guardarActividadesBDD("DaMario", None, [actividad_strava(1, fecha="2024-07-21T07:45:00")])
    assert db.execute("SELECT fecha FROM ActividadesStrava").fetchone() == ("2024-07-21",)
