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


# ---- Fallos conocidos (se marcan como xfail para que aparezcan en el informe) ----

@pytest.mark.xfail(strict=True, reason="chequearDatosBDD abre './DB/dbbcfu.db' (ruta relativa fija) "
                   "en vez de la BD de la app y pasa (fecha) en vez de (fecha,)")
def test_chequear_datos_bdd_usa_bd_de_la_app(strava, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    strava.cursor.execute("INSERT INTO stravaValores (fecha, valor, tipo) VALUES ('2026-09-01', 1, 'bike')")
    strava.sqliteConnection.commit()
    assert strava.chequearDatosBDD("2026-09-01") is True


@pytest.mark.xfail(strict=True, reason="guardarTokenBDD tiene SQL inválido y usa una variable 'fecha' no definida")
def test_guardar_token_bdd(strava):
    strava.cursor.execute("CREATE TABLE token (refresh_token TEXT)")
    assert strava.guardarTokenBDD() is True


@pytest.mark.xfail(strict=True, reason="actualizarTokenBDD pasa (toek) en vez de (toek,) y no devuelve True")
def test_actualizar_token_bdd(strava):
    strava.cursor.execute("CREATE TABLE token (refresh_token TEXT)")
    strava.cursor.execute("INSERT INTO token VALUES ('viejo')")
    assert strava.actualizarTokenBDD("nuevo") is True
    assert strava.recuperarTokenBDD() == "nuevo"
