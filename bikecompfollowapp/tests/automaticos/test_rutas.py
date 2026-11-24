"""Carpeta de datos: .../com.SkullWithGasMask/BikeCFU aunque Toga >= 0.5.7 añada '/Data' en macOS."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bikecompfollowapp import rutas
from bikecompfollowapp.app import AppPaths
from bikecompfollowapp.stravaConnect import StravaData

MAC = Path("/Users/x/Library/Application Support/com.SkullWithGasMask")


@pytest.mark.parametrize("paths_data, raiz", [
    (MAC / "Data", MAC),                      # Toga 0.5.7 en macOS
    (MAC, MAC),                               # Toga 0.5.6 y anteriores
    (Path("/home/x/.local/share/bikecompfollowapp"), Path("/home/x/.local/share/bikecompfollowapp")),
    (MAC / "data", MAC / "data"),             # solo se quita "Data" tal cual
    (MAC / "Database", MAC / "Database"),
])
def test_raiz_datos(paths_data, raiz):
    assert rutas.raiz_datos(paths_data) == raiz


def test_carpeta_app_sin_data_en_medio():
    assert rutas.carpeta_app(MAC / "Data") == MAC / "BikeCFU"
    assert rutas.carpeta_app(str(MAC / "Data")) == MAC / "BikeCFU"


@pytest.fixture
def app_toga_057(tmp_path):
    """App falsa con los paths de Toga 0.5.7 en macOS: paths.data = <raiz>/Data."""
    raiz = tmp_path / "com.SkullWithGasMask"
    fake = SimpleNamespace(paths=SimpleNamespace(data=raiz / "Data", cache=raiz / "Caches"))
    anterior = AppPaths.app
    AppPaths.init(fake)
    yield fake, raiz
    AppPaths.app = anterior


def test_bd_y_log_en_bikecfu_sin_data(app_toga_057):
    _, raiz = app_toga_057
    assert AppPaths.get("data", "BikeCFU", "dbbcfu.db") == raiz / "BikeCFU" / "dbbcfu.db"
    assert AppPaths.get("data", "BikeCFU") == raiz / "BikeCFU"
    assert not (raiz / "Data").exists(), "No se crea la carpeta Data"


def test_la_cache_no_se_toca(app_toga_057):
    _, raiz = app_toga_057
    assert AppPaths.base_dir("cache") == raiz / "Caches"


def test_strava_usa_bikecfu_sin_data(app_toga_057):
    fake, raiz = app_toga_057
    datos = object.__new__(StravaData)
    datos.app = fake
    assert datos.ruta_fichero("strava_tokens.json") == raiz / "BikeCFU" / "strava_tokens.json"
    assert datos.ruta_fichero("client_secrets.txt") == raiz / "BikeCFU" / "client_secrets.txt"


def test_strava_lee_los_tokens_que_ya_estaban(app_toga_057):
    fake, raiz = app_toga_057
    (raiz / "BikeCFU").mkdir(parents=True)
    tokens = {"access_token": "a", "refresh_token": "r", "expires_at": 1}
    (raiz / "BikeCFU" / "strava_tokens.json").write_text(json.dumps(tokens))
    datos = object.__new__(StravaData)
    datos.app = fake
    assert datos.load_tokens() == tokens


def test_strava_abre_la_misma_bd_de_la_app(app_toga_057):
    fake, raiz = app_toga_057
    datos = StravaData(fake, conexion_propia=True)
    try:
        assert Path(datos.sqliteConnection.execute("PRAGMA database_list").fetchone()[2]) == \
            raiz / "BikeCFU" / "dbbcfu.db"
    finally:
        datos.cerrar()


def test_arrancar_la_app_abre_la_bd_de_siempre(app_toga_057):
    from bikecompfollowapp.app import BikeCompFollowApp
    _, raiz = app_toga_057
    app = object.__new__(BikeCompFollowApp)
    app.arrancarDB()
    try:
        assert app.db_path == raiz / "BikeCFU" / "dbbcfu.db"
        assert app.db_path.exists() and not (raiz / "Data").exists()
    finally:
        app.sqliteConnection.close()
