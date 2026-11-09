"""Log diario: bikecfu_YYYYMMDD.log, cambio de fichero al pasar la medianoche."""

import logging
import time
from datetime import date, datetime

import pytest

from bikecompfollowapp import registro
from bikecompfollowapp.registro import ManejadorLogDiario, configurar_log, limpiar_logs_antiguos, nombre_log


@pytest.fixture(autouse=True)
def raiz_limpia():
    """Deja el logger raíz como estaba: los tests no deben tocar el log real de la app."""
    raiz = logging.getLogger()
    handlers, nivel = list(raiz.handlers), raiz.level
    yield
    for h in raiz.handlers:
        if h not in handlers:
            raiz.removeHandler(h)
            h.close()
    raiz.setLevel(nivel)


def registro_en(fecha_hora, mensaje="hola"):
    r = logging.LogRecord("prueba", logging.INFO, __file__, 1, mensaje, None, None)
    r.created = time.mktime(fecha_hora.timetuple())
    r.msecs = 0
    return r


@pytest.mark.parametrize("dia, nombre", [
    (date(2026, 11, 9), "bikecfu_20261109.log"), (date(2026, 1, 5), "bikecfu_20260105.log"),
    (date(2027, 12, 31), "bikecfu_20271231.log"),
])
def test_nombre_del_fichero(dia, nombre):
    assert nombre_log(dia) == nombre


def test_configurar_escribe_en_el_fichero_de_hoy(tmp_path):
    manejador = configurar_log(tmp_path / "BikeCFU")
    logging.getLogger("bikecompfollowapp.prueba").info("Inicio de la app")
    manejador.flush()
    hoy = tmp_path / "BikeCFU" / nombre_log(date.today())
    assert manejador.baseFilename == str(hoy)
    contenido = hoy.read_text(encoding="utf-8")
    assert "INFO" in contenido and "Inicio de la app" in contenido
    assert [f.name for f in (tmp_path / "BikeCFU").iterdir()] == [hoy.name]


def test_formato_de_las_lineas(tmp_path):
    manejador = configurar_log(tmp_path)
    logging.getLogger("x").warning("cuidado %s", "ñandú")
    manejador.flush()
    linea = (tmp_path / nombre_log(date.today())).read_text(encoding="utf-8").strip()
    fecha, hora, nivel, modulo, guion, funcion, *mensaje = linea.split(" ")
    datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M:%S.%f")
    assert (nivel, modulo, guion, funcion) == ("WARNING", "test_registro", "-", "test_formato_de_las_lineas:")
    assert " ".join(mensaje) == "cuidado ñandú"


def test_al_pasar_la_medianoche_cambia_de_fichero(tmp_path):
    manejador = ManejadorLogDiario(tmp_path)
    manejador.setFormatter(logging.Formatter("%(message)s"))
    manejador.dia = date(2026, 11, 9)
    manejador.baseFilename = str(manejador.ruta(manejador.dia))
    manejador.handle(registro_en(datetime(2026, 11, 9, 23, 59, 59), "antes"))
    manejador.handle(registro_en(datetime(2026, 11, 10, 0, 0, 1), "después"))
    manejador.handle(registro_en(datetime(2026, 11, 10, 8, 0, 0), "mañana"))
    manejador.close()
    assert (tmp_path / "bikecfu_20261109.log").read_text(encoding="utf-8") == "antes\n"
    assert (tmp_path / "bikecfu_20261110.log").read_text(encoding="utf-8") == "después\nmañana\n"
    assert manejador.dia == date(2026, 11, 10)


def test_mismo_dia_se_anade_al_mismo_fichero(tmp_path):
    for texto in ("primera ejecución", "segunda ejecución"):     # dos arranques de la app el mismo día
        manejador = configurar_log(tmp_path)
        logging.getLogger("x").info(texto)
        manejador.flush()
    lineas = (tmp_path / nombre_log(date.today())).read_text(encoding="utf-8").splitlines()
    assert [l.split(": ", 1)[1] for l in lineas] == ["primera ejecución", "segunda ejecución"]


def test_configurar_dos_veces_no_duplica_mensajes(tmp_path):
    configurar_log(tmp_path)
    manejador = configurar_log(tmp_path)
    assert [h for h in logging.getLogger().handlers if isinstance(h, ManejadorLogDiario)] == [manejador]
    logging.getLogger("x").info("una vez")
    manejador.flush()
    assert (tmp_path / nombre_log(date.today())).read_text(encoding="utf-8").count("una vez") == 1


def test_crea_la_carpeta_y_no_crea_fichero_hasta_el_primer_mensaje(tmp_path):
    carpeta = tmp_path / "no" / "existe"
    configurar_log(carpeta)
    assert carpeta.is_dir() and list(carpeta.iterdir()) == []


def test_nivel_debug_por_defecto(tmp_path):
    configurar_log(tmp_path)
    assert logging.getLogger().level == logging.DEBUG


def test_app_usa_el_log_diario():
    from pathlib import Path
    codigo = Path(registro.__file__).with_name("app.py").read_text(encoding="utf-8")
    assert "registro.configurar_log(" in codigo
    assert "basicConfig" not in codigo and '"bikecfu.log"' not in codigo


def test_log_path_de_la_app_es_el_fichero_de_hoy(tmp_path):
    from bikecompfollowapp.app import BikeCompFollowApp
    app = object.__new__(BikeCompFollowApp)
    assert app.log_path is None
    app.log_handler = configurar_log(tmp_path)
    assert app.log_path == tmp_path / nombre_log(date.today())


# ---- Borrado de logs de más de 10 días al arrancar ----

HOY = date(2026, 11, 20)


def crear(carpeta, *nombres):
    for nombre in nombres:
        (carpeta / nombre).write_text("x", encoding="utf-8")


def test_borra_los_de_mas_de_10_dias_y_conserva_el_resto(tmp_path):
    crear(tmp_path, "bikecfu_20261120.log",      # hoy
                    "bikecfu_20261110.log",      # hace 10 días: se conserva
                    "bikecfu_20261109.log",      # hace 11 días: se borra
                    "bikecfu_20261001.log", "bikecfu_20251231.log")
    assert limpiar_logs_antiguos(tmp_path, hoy=HOY) == [
        "bikecfu_20251231.log", "bikecfu_20261001.log", "bikecfu_20261109.log"]
    assert sorted(f.name for f in tmp_path.iterdir()) == ["bikecfu_20261110.log", "bikecfu_20261120.log"]


def test_no_toca_otros_ficheros(tmp_path):
    crear(tmp_path, "bikecfu.log",                # el log único antiguo
                    "dbbcfu.db", "bikecfu_2026.log", "bikecfu_20261340.log", "otro_20200101.log",
                    "bikecfu_20200101.log.bak", "bikecfu_20200101.txt")
    assert limpiar_logs_antiguos(tmp_path, hoy=HOY) == []
    assert len(list(tmp_path.iterdir())) == 7


def test_por_defecto_conserva_10_dias():
    assert registro.DIAS_CONSERVAR_LOG == 10


def test_otro_numero_de_dias(tmp_path):
    crear(tmp_path, "bikecfu_20261119.log", "bikecfu_20261117.log")
    assert limpiar_logs_antiguos(tmp_path, dias=2, hoy=HOY) == ["bikecfu_20261117.log"]


def test_carpeta_vacia_o_inexistente(tmp_path):
    assert limpiar_logs_antiguos(tmp_path, hoy=HOY) == []
    assert limpiar_logs_antiguos(tmp_path / "no_existe", hoy=HOY) == []


def test_el_borrado_queda_en_el_log_de_hoy(tmp_path):
    manejador = configurar_log(tmp_path)
    crear(tmp_path, "bikecfu_20200101.log")
    limpiar_logs_antiguos(tmp_path)
    manejador.flush()
    assert "Borrados 1 logs de más de 10 días: bikecfu_20200101.log" in (
        tmp_path / nombre_log(date.today())).read_text(encoding="utf-8")


def test_si_no_se_puede_borrar_sigue_con_los_demas(tmp_path, monkeypatch):
    crear(tmp_path, "bikecfu_20200101.log", "bikecfu_20200102.log")
    original = type(tmp_path).unlink

    def unlink(self, *a, **k):
        if self.name == "bikecfu_20200101.log":
            raise PermissionError("bloqueado")
        return original(self, *a, **k)
    monkeypatch.setattr(type(tmp_path), "unlink", unlink)
    assert limpiar_logs_antiguos(tmp_path, hoy=HOY) == ["bikecfu_20200102.log"]
    assert (tmp_path / "bikecfu_20200101.log").exists()


def test_la_app_limpia_los_logs_al_arrancar():
    from pathlib import Path
    codigo = Path(registro.__file__).with_name("app.py").read_text(encoding="utf-8")
    inicio = codigo.index("    def startup(self):")
    arranque = codigo[inicio:codigo.index("    def ", inicio + 10)]
    assert arranque.index("registro.configurar_log(") < arranque.index("registro.limpiar_logs_antiguos(")
