"""Tests de stravaConnect.StravaData sin conectarse a Strava (red y cliente simulados)."""

import time
from datetime import datetime
from types import SimpleNamespace

import pytest

from bikecompfollowapp import stravaConnect
from bikecompfollowapp.stravaConnect import StravaData


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
    try:
        datos.total_distancia, datos.total_desnivel, datos.total_tiempo, datos.total_actividades = 12_000, 200, 3600, 1
        datos.guardarDatosBDD("2026-10-01")
        assert db.execute("SELECT fecha, valor FROM stravaValores").fetchall() == [("2026-10-01", 12)]
        assert datos.chequearDatosBDD("2026-10-01") is True
    finally:
        datos.sqliteConnection.close()


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
