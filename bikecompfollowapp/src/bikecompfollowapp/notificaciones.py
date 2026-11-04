"""Notificaciones del sistema para el usuario.

En macOS se usa ``osascript`` (``display notification``), que funciona tanto con ``briefcase dev``
como con la app empaquetada. plyer no sirve en macOS: necesita ``pyobjus`` y, sin él, lanza
``NotImplementedError("No usable implementation found!")``. En el resto de plataformas se intenta
plyer. Si no hay forma de notificar se registra en el log y se devuelve False, sin romper la app.
"""

import logging
import subprocess
import sys

log = logging.getLogger(__name__)


def _cadena_applescript(texto: str) -> str:
    return '"' + str(texto).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _notificar_macos(titulo: str, mensaje: str) -> None:
    script = f"display notification {_cadena_applescript(mensaje)} with title {_cadena_applescript(titulo)}"
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=10)


def _notificar_plyer(titulo: str, mensaje: str, app_name: str) -> None:
    from plyer import notification
    notification.notify(title=titulo, message=mensaje, app_name=app_name)


def notificar(titulo: str, mensaje: str, app_name: str = "BikeCompFollowApp") -> bool:
    """Muestra una notificación del sistema. Devuelve True si se ha podido lanzar."""
    try:
        if sys.platform == "darwin":
            _notificar_macos(titulo, mensaje)
        else:
            _notificar_plyer(titulo, mensaje, app_name)
    except (NotImplementedError, ImportError, OSError, subprocess.SubprocessError) as error:
        log.warning("No se pudo lanzar la notificación %r (%s): %s", titulo, sys.platform, error)
        return False
    log.info("Notificación lanzada: %s - %s", titulo, mensaje)
    return True
