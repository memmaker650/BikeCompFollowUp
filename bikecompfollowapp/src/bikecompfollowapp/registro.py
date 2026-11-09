"""
Fichero de log de BikeCompFollowApp: uno por día, con el nombre bikecfu_YYYYMMDD.log.

Cada mensaje va al fichero del día en que se registra. Si la app sigue abierta al pasar la medianoche, el
siguiente mensaje ya se escribe en el fichero del nuevo día (no hace falta reiniciarla).
"""

import logging
import os
import re
from datetime import date, datetime
from pathlib import Path

PREFIJO_LOG = "bikecfu"
FORMATO_LOG = "%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s"
FORMATO_FECHA_LOG = "%Y-%m-%d %H:%M:%S"
DIAS_CONSERVAR_LOG = 10     # al arrancar se borran los logs de más de 10 días


def nombre_log(dia, prefijo=PREFIJO_LOG):
    """date(2026, 11, 9) -> 'bikecfu_20261109.log'"""
    return f"{prefijo}_{dia:%Y%m%d}.log"


class ManejadorLogDiario(logging.FileHandler):
    """FileHandler que escribe cada mensaje en <carpeta>/<prefijo>_YYYYMMDD.log según el día del mensaje."""

    def __init__(self, carpeta, prefijo=PREFIJO_LOG, encoding="utf-8"):
        self.carpeta = Path(carpeta)
        self.prefijo = prefijo
        self.dia = date.today()
        self.carpeta.mkdir(parents=True, exist_ok=True)
        # delay=True: el fichero se crea con el primer mensaje, no al configurar el log
        super().__init__(self.ruta(self.dia), encoding=encoding, delay=True)

    def ruta(self, dia):
        return self.carpeta / nombre_log(dia, self.prefijo)

    def emit(self, record):
        dia = date.fromtimestamp(record.created)
        if dia != self.dia:            # ha cambiado el día: se cierra el fichero anterior y se pasa al nuevo
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            self.dia = dia
            self.baseFilename = os.path.abspath(self.ruta(dia))
        super().emit(record)


def configurar_log(carpeta, nivel=logging.DEBUG):
    """Envía el log de toda la app a ficheros diarios en `carpeta`. Si ya estaba configurado, lo sustituye
    (no se duplican los mensajes). Devuelve el manejador; su `baseFilename` es el fichero de hoy."""
    raiz = logging.getLogger()
    for anterior in [h for h in raiz.handlers if isinstance(h, ManejadorLogDiario)]:
        raiz.removeHandler(anterior)
        anterior.close()
    manejador = ManejadorLogDiario(carpeta)
    manejador.setFormatter(logging.Formatter(FORMATO_LOG, datefmt=FORMATO_FECHA_LOG))
    raiz.addHandler(manejador)
    raiz.setLevel(nivel)
    return manejador


def limpiar_logs_antiguos(carpeta, dias=DIAS_CONSERVAR_LOG, hoy=None, prefijo=PREFIJO_LOG):
    """Borra de `carpeta` los ficheros <prefijo>_YYYYMMDD.log de hace más de `dias` días (según la fecha de su
    nombre). Se conservan el de hoy y los de los `dias` días anteriores; no toca ningún otro fichero.
    Devuelve los nombres borrados."""
    hoy = hoy or date.today()
    patron = re.compile(rf"^{re.escape(prefijo)}_(\d{{8}})\.log$")
    borrados = []
    for fichero in sorted(Path(carpeta).glob(f"{prefijo}_*.log")):
        encontrado = patron.match(fichero.name)
        if not encontrado:
            continue
        try:
            dia = datetime.strptime(encontrado.group(1), "%Y%m%d").date()
        except ValueError:         # p. ej. bikecfu_20261340.log: no es una fecha, no se toca
            continue
        if (hoy - dia).days > dias:
            try:
                fichero.unlink()
                borrados.append(fichero.name)
            except OSError as error:
                logging.warning("No se pudo borrar el log antiguo %s: %s", fichero.name, error)
    if borrados:
        logging.info("Borrados %d logs de más de %d días: %s", len(borrados), dias, ", ".join(borrados))
    return borrados
