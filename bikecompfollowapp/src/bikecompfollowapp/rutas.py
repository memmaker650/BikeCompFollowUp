"""
Carpetas de datos de BikeCompFollowApp.

Todo (BD, log, tokens y secretos de Strava) va en <carpeta de datos de la app>/BikeCFU. En macOS la carpeta de
datos es ~/Library/Application Support/com.SkullWithGasMask.

Desde Toga 0.5.7, en macOS `app.paths.data` añade al final una subcarpeta "Data" (para separarla de "Config"):
…/com.SkullWithGasMask/Data. La app no la usa: se quita, para seguir usando …/com.SkullWithGasMask/BikeCFU
con cualquier versión de Toga y no empezar con una BD vacía al actualizar.
"""

from pathlib import Path

CARPETA_APP = "BikeCFU"
SUBCARPETA_DATOS_TOGA = "Data"     # la que añade Toga >= 0.5.7 en macOS


def raiz_datos(paths_data):
    """Carpeta de datos de la app a partir de `app.paths.data`, sin la subcarpeta "Data" de Toga 0.5.7."""
    ruta = Path(paths_data)
    return ruta.parent if ruta.name == SUBCARPETA_DATOS_TOGA else ruta


def carpeta_app(paths_data):
    """<carpeta de datos de la app>/BikeCFU"""
    return raiz_datos(paths_data) / CARPETA_APP
