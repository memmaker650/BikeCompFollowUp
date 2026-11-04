"""Pantalla Strava Sync: selector de fecha, barra de progreso y notificación al terminar."""

import asyncio
import threading
from datetime import date, datetime
from types import SimpleNamespace

import pytest
import toga
from stravalib.model import SummaryActivity

from bikecompfollowapp import notificaciones
from bikecompfollowapp.app import FECHA_INICIO_STRAVA
from bikecompfollowapp.stravaConnect import StravaData
from bikecompfollowapp.translations import t


def actividad(id_, tipo="Ride", gear="b1"):
    return SummaryActivity(id=id_, type=tipo, distance=10_000.0, moving_time=1800,
                           total_elevation_gain=100.0, average_speed=5.5, gear_id=gear)


@pytest.fixture
def pantalla(ui, db):
    db.execute("INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) VALUES ('N', 'DaMario', 'Bici Gravel', '')")
    ui.sqliteConnection.commit()      # la descarga usa su propia conexión desde otro hilo
    ui.usuarioSeleccionado = "DaMario"
    ui.ir_a_pantalla_recoleccionDatos()
    return ui


@pytest.fixture
def strava_falso(monkeypatch):
    """Strava simulado: registra la fecha pedida, el hilo usado y los avisos."""
    registro = SimpleNamespace(after=None, hilos=set(), avisos=[], actividades=[actividad(1), actividad(2, "Run"), actividad(3)])
    monkeypatch.setattr(StravaData, "initConexion", lambda self: None)

    def cliente(self):
        registro.hilos.add(threading.current_thread().name)

        def get_activities(after, before):
            registro.after = after
            yield from registro.actividades

        self.client = SimpleNamespace(get_activities=get_activities,
                                      get_gear=lambda gid: SimpleNamespace(name="Canyon"))

    monkeypatch.setattr(StravaData, "crearObjetoCliente", cliente)
    monkeypatch.setattr(notificaciones, "notificar", lambda titulo, mensaje: registro.avisos.append((titulo, mensaje)) or True)
    return registro


def test_selector_de_fecha_por_defecto_1_enero_2026(pantalla):
    assert FECHA_INICIO_STRAVA == date(2026, 1, 1)
    assert isinstance(pantalla.fecha_desde, toga.DateInput)
    assert pantalla.fecha_desde.value == date(2026, 1, 1)
    assert pantalla.fecha_desde.max == date.today()


def test_descarga_desde_la_fecha_elegida(pantalla, strava_falso):
    pantalla.fecha_desde.value = date(2026, 3, 15)
    asyncio.run(pantalla.recolectarDatosStrava())
    assert strava_falso.after == datetime(2026, 3, 15, 0, 0)


def test_descarga_por_defecto_desde_1_enero_2026(pantalla, strava_falso):
    asyncio.run(pantalla.recolectarDatosStrava())
    assert strava_falso.after == datetime(2026, 1, 1, 0, 0)


def test_descarga_en_otro_hilo_y_guarda_en_bd(pantalla, strava_falso, db):
    asyncio.run(pantalla.recolectarDatosStrava())
    assert threading.current_thread().name not in strava_falso.hilos, "La ventana no debe congelarse"
    assert db.execute("SELECT StravaID, tipo_vehiculo FROM ActividadesStrava ORDER BY StravaID").fetchall() == [
        (1, "Bici Gravel"), (2, None), (3, "Bici Gravel")
    ]


def test_al_terminar_notifica_y_barra_completa(pantalla, strava_falso):
    asyncio.run(pantalla.recolectarDatosStrava())
    mensaje = t("strava.fin", total=3)
    assert strava_falso.avisos == [(t("notificacion.strava_titulo"), mensaje)]
    assert pantalla.label.text == mensaje
    assert pantalla.progress.value == pantalla.progress.max
    assert not pantalla.progress.is_running
    assert pantalla.boton_extraer.enabled and pantalla.fecha_desde.enabled


def test_barra_avanza_con_cada_actividad(pantalla, strava_falso, monkeypatch):
    pasos = []
    original = pantalla._progreso_strava

    def registrar(fase, actual, total=None):
        original(fase, actual, total)
        pasos.append((fase, actual, total, pantalla.progress.value if fase == "guardando" else None))

    monkeypatch.setattr(pantalla, "_progreso_strava", registrar)
    asyncio.run(pantalla.recolectarDatosStrava())
    assert pasos == [
        ("descargando", 0, None, None),
        ("descargando", 1, None, None), ("descargando", 2, None, None), ("descargando", 3, None, None),
        ("guardando", 1, 3, 1.0), ("guardando", 2, 3, 2.0), ("guardando", 3, 3, 3.0),
    ]


def test_mientras_descarga_barra_indeterminada_y_contador(pantalla):
    pantalla._progreso_strava("descargando", 7)
    assert pantalla.progress.max is None and pantalla.progress.is_running
    assert pantalla.label.text == t("strava.descargando", actual=7)
    pantalla._progreso_strava("guardando", 2, 4)
    assert (pantalla.progress.max, pantalla.progress.value, pantalla.progress.is_running) == (4, 2, False)


def test_error_se_notifica_y_no_se_queda_bloqueada(pantalla, strava_falso, monkeypatch):
    def sin_red(self):
        raise ConnectionError("sin conexión")

    monkeypatch.setattr(StravaData, "crearObjetoCliente", sin_red)
    asyncio.run(pantalla.recolectarDatosStrava())
    mensaje = t("strava.error", error="sin conexión")
    assert strava_falso.avisos == [(t("notificacion.strava_titulo"), mensaje)]
    assert pantalla.label.text == mensaje
    assert pantalla.boton_extraer.enabled and not pantalla.sync_strava_en_curso


def test_sin_actividades_tambien_notifica(pantalla, strava_falso):
    strava_falso.actividades = []
    asyncio.run(pantalla.recolectarDatosStrava())
    assert strava_falso.avisos == [(t("notificacion.strava_titulo"), t("strava.fin", total=0))]


def test_no_se_lanzan_dos_descargas_a_la_vez(pantalla, strava_falso):
    pantalla.sync_strava_en_curso = True
    asyncio.run(pantalla.recolectarDatosStrava())
    assert strava_falso.avisos == [] and strava_falso.after is None


def test_textos_en_ingles(pantalla, strava_falso):
    from bikecompfollowapp import translations
    translations.set_language("en")
    asyncio.run(pantalla.recolectarDatosStrava())
    assert strava_falso.avisos == [("Strava Sync", "Download finished: 3 activities saved.")]
