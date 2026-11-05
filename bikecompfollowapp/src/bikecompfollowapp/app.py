""""""""""
App to follow up bike comp, sneakers and car comp to avoid breaks.
"""""""""""

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW, LEFT
from toga.colors import Color, rgb
from toga.sources import AccessorColumn

from pathlib import Path
import sys
import sqlite3
import unicodedata
import logging
from datetime import date, datetime, time

if __name__ == "__main__" or __package__ is None:
    import notificaciones
    import stravaConnect
    import translations
else:
    from . import notificaciones, stravaConnect, translations
t = translations.t
import asyncio
from contextlib import contextmanager

# ---- Medidas de interfaz (Toga trabaja en píxeles; 1 cm ≈ 38 px a 96 ppp) ----
ANCHO_CAMPO = 250
ANCHO_BOTONES_MENU = 320
ALTO_ESTADISTICAS = 130      # ≈ 3,5 cm
ALTO_MANTENIMIENTO = 260     # el doble ≈ 7 cm
ESPACIO = 10                 # separación entre botones

DISTANCIA_LIMITE_DEFECTO = 5000
TIEMPO_LIMITE_DEFECTO = 500
AZUL = rgb(0, 102, 204)
COLOR_ESTADISTICAS = "#FF8C00"
# Espera ante una BD bloqueada por otro programa: la de sqlite3 por defecto y la corta de Estadísticas
ESPERA_BD_MS = 5000
ESPERA_CORTA_BD_MS = 500
# Ventana de Alerta (componentes a cambiar de manera urgente)
ROJO_ALERTA = rgb(220, 0, 0)
TAMANO_TITULO_ALERTA = 24
TAMANO_VENTANA_ALERTA = (420, 260)

# Tabla "Tiempo y Kms por Modalidad" de Estadísticas: filas y nº de años (el actual y los anteriores)
MODALIDADES_ESTADISTICAS = ("Road", "MTB", "Gravel")
ANIOS_ESTADISTICAS = 3
COLOR_MANTENIMIENTO = "#1E64C8"

# Componentes de prueba para la ventana de Alerta del menú del usuario (ver componentesUrgentes)
COMPONENTES_URGENTES_PRUEBA = ["Cadena", "Pastillas de Freno"]

# Límites por defecto de cada componente: (palabras que debe contener el nombre, sin acentos ni mayúsculas)
# -> (km, horas, meses). El primero que coincide gana; si ninguno coincide, LIMITES_GENERICOS.
LIMITES_GENERICOS = (DISTANCIA_LIMITE_DEFECTO, TIEMPO_LIMITE_DEFECTO, None)
LIMITES_POR_COMPONENTE = [
    (("liquido", "freno"), (None, None, 12)),     # líquido de frenos: 1 año
    (("purgado", "freno"), (None, None, 12)),     # purgado de frenos = cambio de líquido
    (("cubierta",), (4000, TIEMPO_LIMITE_DEFECTO, None)),
    (("cadena",), (2000, TIEMPO_LIMITE_DEFECTO, None)),
    (("pastilla",), (4000, TIEMPO_LIMITE_DEFECTO, None)),   # frenos
]      # texto "Usuario:" de la pantalla de alta de componente
ELEMENTOS_POR_DEFECTO = ["Cadena", "Pastillas Freno", "Cubiertas"]

# Columnas de las tablas de la pantalla Estadísticas: (clave de traducción de la cabecera, atributo de la fila)
COLUMNAS_COMPONENTES = [
    ("col.componente", "elemento"), ("col.descripcion", "descripcion"), ("col.fecha", "fechaInsercion"),
    ("col.km_max", "distanciaLimite"), ("col.km_desde_alta", "distanciaDesdeInsercion"),
    ("col.horas_max", "tiempoLimite"), ("col.horas_desde_alta", "horasDesdeInsercion"),
    ("col.meses_max", "mesesLimite"), ("col.meses_desde_alta", "mesesDesdeInsercion"), ("col.activo", "activo"),
]
COLUMNAS_LIMITES = [("col.componente", "componente"), ("col.tipo_limite", "tipo_limite"), ("col.valor", "valor")]

# Tipos de límite tal y como se guardan en LimitesAlerta -> clave del texto que se muestra
TIPOS_LIMITE = {"superior": "alerta.superior", "inferior": "alerta.inferior"}


def orden_alfabetico(texto):
    """Clave para ordenar sin distinguir mayúsculas ni acentos ('Cámara' va antes que 'Cubierta')."""
    sin_acentos = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sin_acentos if not unicodedata.combining(c)).casefold()


def limitesPorDefecto(componente):
    """(km, horas, meses) por defecto para un componente (ver LIMITES_POR_COMPONENTE)."""
    nombre = orden_alfabetico(componente)
    for palabras, limites in LIMITES_POR_COMPONENTE:
        if all(palabra in nombre for palabra in palabras):
            return limites
    return LIMITES_GENERICOS


# ---- Límites por tipo de bici guardados en la tabla Componente ----
# Componente.tipo<Bici> = unidad del límite ('km', 'horas' o 'meses'), Componente.limite<Bici> = valor.
TIPOS_BICI = ("Road", "Gravel", "MTB")
UNIDADES_LIMITE = ("km", "horas", "meses")
COLUMNAS_LIMITES_COMPONENTE = {f"{prefijo}{bici}": tipo for bici in TIPOS_BICI
                               for prefijo, tipo in (("tipo", "TEXT"), ("limite", "FLOAT"))}


def tipoBici(vehiculo):
    """'Bici Gravel' -> 'Gravel', 'Bici MTB'/'Montaña' -> 'MTB'; cualquier otro (o None) -> 'Road'."""
    nombre = orden_alfabetico(vehiculo)
    if "gravel" in nombre:
        return "Gravel"
    if "mtb" in nombre or "montana" in nombre:
        return "MTB"
    return "Road"


def limiteUnicoPorDefecto(componente):
    """(unidad, valor) del límite principal por defecto de un componente: meses si tiene, si no km, si no horas."""
    km, horas, meses = limitesPorDefecto(componente)
    if meses is not None:
        return "meses", meses
    if km is not None:
        return "km", km
    return ("horas", horas) if horas is not None else (None, None)


def _entero(valor):
    return int(valor) if isinstance(valor, float) and valor.is_integer() else valor


def limitesDesdeUnidad(unidad, limite):
    """('km', 4000) -> (4000, 500, None): el límite va a su cuadro; con km se mantienen las horas genéricas."""
    limite = _entero(limite)
    unidad = (unidad or "").strip().lower()
    return (
        limite if unidad == "km" else None,
        limite if unidad == "horas" else (TIEMPO_LIMITE_DEFECTO if unidad == "km" else None),
        limite if unidad == "meses" else None,
    )


def asegurarColumnasComponente(conexion) -> None:
    """Añade a Componente tipo/limite para Road, Gravel y MTB y rellena las filas que no tengan ninguno
    con el límite por defecto del componente (el mismo para los tres tipos de bici)."""
    columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(Componente)")}
    if not columnas:
        return
    for columna, tipo in COLUMNAS_LIMITES_COMPONENTE.items():
        if columna not in columnas:
            logging.info("Migrando Componente: se añade la columna %s", columna)
            conexion.execute(f"ALTER TABLE Componente ADD COLUMN {columna} {tipo}")
    sin_limites = conexion.execute(
        "SELECT id, nombre FROM Componente WHERE "
        + " AND ".join(f"tipo{bici} IS NULL" for bici in TIPOS_BICI)).fetchall()
    asignaciones = ", ".join(f"tipo{bici} = :tipo, limite{bici} = :limite" for bici in TIPOS_BICI)
    for id_, nombre in sin_limites:
        unidad, limite = limiteUnicoPorDefecto(nombre)
        conexion.execute(f"UPDATE Componente SET {asignaciones} WHERE id = :id",
                         {"tipo": unidad, "limite": limite, "id": id_})
    conexion.commit()


def vehiculoDeUsuario(conexion, usuario):
    """Vehículo del usuario (EntradasUsers.tipov guarda el nombre o el id de tipo_vehiculo)."""
    fila = conexion.execute(
        """SELECT COALESCE(tv.vehiculo, eu.tipov) FROM EntradasUsers eu
           LEFT JOIN tipo_vehiculo tv ON tv.id = eu.tipov
           WHERE eu.usuario = ? ORDER BY eu.id DESC LIMIT 1""",
        (usuario,),
    ).fetchone()
    return None if fila is None or fila[0] is None else str(fila[0])


def _regla_limites(nombre):
    """Índice de la regla de LIMITES_POR_COMPONENTE que corresponde al nombre, o None."""
    normalizado = orden_alfabetico(nombre)
    return next((i for i, (palabras, _) in enumerate(LIMITES_POR_COMPONENTE)
                 if all(palabra in normalizado for palabra in palabras)), None)


def limitesComponente(conexion, componente, usuario=None):
    """(km, horas, meses) por defecto de un componente para la bici del usuario, leídos de la tabla Componente.

    El componente se busca por nombre (sin mayúsculas ni acentos) o, si no está tal cual, por la misma regla de
    LIMITES_POR_COMPONENTE ('Cubiertas' -> 'Cubierta', 'PASTILLA/S FRENO' -> 'pastillas freno'). Si no está en
    la tabla o no tiene límite para esa bici, se usan los valores del código (limitesPorDefecto)."""
    if not componente:
        return limitesPorDefecto(componente)
    try:
        bici = tipoBici(vehiculoDeUsuario(conexion, usuario)) if usuario else "Road"
        filas = conexion.execute(f"SELECT nombre, tipo{bici}, limite{bici} FROM Componente").fetchall()
    except sqlite3.Error as error:
        logging.warning("No se pudieron leer los límites de Componente: %s", error)
        return limitesPorDefecto(componente)
    buscado = orden_alfabetico(componente)
    fila = next((f for f in filas if orden_alfabetico(f[0]) == buscado), None)
    regla = _regla_limites(componente)
    if fila is None and regla is not None:
        fila = next((f for f in filas if _regla_limites(f[0]) == regla), None)
    if fila is None or not fila[1]:
        return limitesPorDefecto(componente)
    return limitesDesdeUnidad(fila[1], fila[2])


def aniosEstadisticas(hoy=None):
    """Los AÑOS_ESTADISTICAS últimos años, el actual incluido: en 2026 -> [2024, 2025, 2026]."""
    anio = (hoy or date.today()).year
    return list(range(anio - ANIOS_ESTADISTICAS + 1, anio + 1))


def kmsHorasPorModalidad(conexion, usuario, anios):
    """Acumulados de ActividadesStrava del usuario por modalidad (Road, MTB, Gravel) y año.

    Devuelve (filas, anios_sin_datos). Cada fila es (modalidad, desde, km_año1, horas_año1, km_año2, ...):
    'desde' es el día de su primera actividad (None si no tiene ninguna) y los acumulados son 0 si no hay
    datos ese año. anios_sin_datos son los años sin ninguna actividad de las tres modalidades."""
    marcas = ", ".join("?" for _ in MODALIDADES_ESTADISTICAS)
    desde = dict(conexion.execute(
        f"""SELECT Modalidad, MIN(fecha) FROM ActividadesStrava
            WHERE user = ? AND Modalidad IN ({marcas}) AND fecha IS NOT NULL GROUP BY Modalidad""",
        (usuario, *MODALIDADES_ESTADISTICAS)).fetchall())
    acumulados = {(modalidad, int(anio)): (km, horas) for modalidad, anio, km, horas in conexion.execute(
        f"""SELECT Modalidad, strftime('%Y', fecha), ROUND(COALESCE(SUM(distancia), 0), 1),
                   ROUND(COALESCE(SUM(duracion), 0), 1)
            FROM ActividadesStrava
            WHERE user = ? AND Modalidad IN ({marcas}) AND fecha IS NOT NULL
            GROUP BY Modalidad, strftime('%Y', fecha)""",
        (usuario, *MODALIDADES_ESTADISTICAS))}
    filas = []
    for modalidad in MODALIDADES_ESTADISTICAS:
        fila = [modalidad, desde.get(modalidad)]
        for anio in anios:
            fila.extend(acumulados.get((modalidad, anio), (0.0, 0.0)))
        filas.append(tuple(fila))
    con_datos = {anio for (_, anio) in acumulados}
    return filas, [anio for anio in anios if anio not in con_datos]


def texto_numero(valor):
    """12.0 -> '12', 1959.45 -> '1959.5'; None -> ''."""
    if valor is None:
        return ""
    valor = round(float(valor), 1)
    return str(int(valor)) if valor.is_integer() else f"{valor:.1f}"


def texto_activo(valor):
    """Valor de la columna activo (1/0, True/False...) -> 'Sí' / 'No' en el idioma activo; vacío si no hay."""
    if valor is None or valor == "":
        return ""
    if isinstance(valor, str):
        valor = valor.strip().lower() not in ("0", "false", "no")
    return t("comun.si") if valor else t("comun.no")


def pintar_fondo_boton(boton, color_hex):
    """En macOS, Toga colorea los botones con bezelColor, que macOS solo pinta mientras la app es la activa
    (si el foco está en otra app, p. ej. PyCharm, salen blancos). Se pinta el fondo en la capa del botón,
    que se ve siempre. En el resto de backends no hace nada: basta con background_color de Pack."""
    nativo = getattr(getattr(boton, "_impl", None), "native", None)
    if nativo is None or not type(boton._impl).__module__.startswith("toga_cocoa"):
        return False
    try:
        from toga_cocoa.libs import NSColor
        c = Color.parse(color_hex)
        nativo.bordered = False
        nativo.wantsLayer = True
        nativo.layer.backgroundColor = NSColor.colorWithRed(
            c.r / 255, green=c.g / 255, blue=c.b / 255, alpha=c.a).CGColor
        nativo.layer.cornerRadius = 8
    except Exception as error:   # no debe impedir mostrar la pantalla
        logging.warning("No se pudo pintar el fondo del botón %r: %s", boton.text, error)
        return False
    return True


def _columnas(definicion):
    return [AccessorColumn(t(clave), atributo) for clave, atributo in definicion]


# Datos con los que se siembra una BD nueva
VEHICULOS_INICIALES = ["Coche", "Bici Carretera", "Bici Gravel", "Bici MTB", "Tractor"]
ELEMENTOS_INICIALES = [
    "cadena", "pastillas freno", "Cubierta", "Cinta Manillar", "Piñonera",
    "Plato", "Cambio Trasero", "Líquido Frenos", "Maneta Cambio", "Cámara",
]

# Tablas renombradas: nombre antiguo -> nombre nuevo. Al arrancar se renombran conservando sus filas.
TABLAS_RENOMBRADAS = {"datos": "datosComponente", "Elemento": "Componente"}

# Km acumulados por cada alta de componente (una fila por fila de archivoscomponentes).
SQL_CREAR_DATOS_COMPONENTE = """CREATE TABLE IF NOT EXISTS datosComponente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idComponente INTEGER NOT NULL UNIQUE,
    usuario TEXT,
    componente TEXT,
    fecha TEXT,
    km FLOAT NOT NULL DEFAULT 0,
    horas FLOAT NOT NULL DEFAULT 0,
    num_actividades INTEGER NOT NULL DEFAULT 0,
    activo BOOLEAN,
    FOREIGN KEY (idComponente) REFERENCES archivoscomponentes(id))"""
COLUMNAS_DATOS_COMPONENTE = {"id", "idComponente", "usuario", "componente", "fecha", "km", "horas",
                             "num_actividades", "activo"}
# Columnas añadidas después de crear la tabla: se añaden con ALTER TABLE conservando las filas
COLUMNAS_NUEVAS_DATOS_COMPONENTE = {"horas": "FLOAT NOT NULL DEFAULT 0"}

# Solo cuentan las salidas en bici (ni rodillo, ni carrera, ni caminatas...)
TIPOS_KM_COMPONENTE = ("Ride",)

# Suma, para cada alta de componente, los km y las horas de uso (duracion) de las actividades del mismo usuario desde su fecha de alta
# (incluido ese día). fecha = día del cálculo. Las actividades sin fecha no cuentan.
SQL_CALCULAR_KM_COMPONENTES = """
INSERT INTO datosComponente (idComponente, usuario, componente, fecha, km, horas, num_actividades, activo)
SELECT ac.id, ac.usuario, ac.elemento, date('now', 'localtime'),
       ROUND(COALESCE(SUM(a.distancia), 0), 2), ROUND(COALESCE(SUM(a.duracion), 0), 2), COUNT(a.id), ac.activo
FROM archivoscomponentes ac
LEFT JOIN ActividadesStrava a
       ON a.user = ac.usuario
      AND a.tipo IN ({tipos})
      AND a.fecha IS NOT NULL
      AND a.fecha >= date(ac.fechaInsercion)
WHERE (:usuario IS NULL OR ac.usuario = :usuario)
GROUP BY ac.id
ON CONFLICT(idComponente) DO UPDATE SET
    usuario = excluded.usuario, componente = excluded.componente, fecha = excluded.fecha,
    km = excluded.km, horas = excluded.horas, num_actividades = excluded.num_actividades, activo = excluded.activo
""".format(tipos=", ".join(f"'{tipo}'" for tipo in TIPOS_KM_COMPONENTE))


def asegurarTablaDatosComponente(conexion) -> None:
    """Crea datosComponente. Si existe con otra estructura (la antigua tabla 'datos'): vacía se recrea;
    con filas se guarda como datosComponente_antigua para no perderlas."""
    columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(datosComponente)")}
    if columnas and columnas | COLUMNAS_NUEVAS_DATOS_COMPONENTE.keys() == COLUMNAS_DATOS_COMPONENTE:
        for columna, definicion in COLUMNAS_NUEVAS_DATOS_COMPONENTE.items():
            if columna not in columnas:
                logging.info("Migrando datosComponente: se añade la columna %s", columna)
                conexion.execute(f"ALTER TABLE datosComponente ADD COLUMN {columna} {definicion}")
        columnas = COLUMNAS_DATOS_COMPONENTE
    if columnas and columnas != COLUMNAS_DATOS_COMPONENTE:
        if conexion.execute("SELECT COUNT(*) FROM datosComponente").fetchone()[0]:
            logging.warning("datosComponente tenía otra estructura y datos: se guarda como datosComponente_antigua")
            conexion.execute("ALTER TABLE datosComponente RENAME TO datosComponente_antigua")
        else:
            logging.info("datosComponente tenía otra estructura y estaba vacía: se recrea")
            conexion.execute("DROP TABLE datosComponente")
    conexion.execute(SQL_CREAR_DATOS_COMPONENTE)
    conexion.commit()


# Componentes del catálogo que el usuario aún no ha definido: se crean con esta descripción para que
# vayan sumando km. Cuando el usuario da de alta ese componente se actualiza esa misma fila.
DESCRIPCION_POR_DEFECTO = "POR DEFECTO"


def asegurarColumnasArchivosComponentes(conexion) -> None:
    """Añade a archivoscomponentes las columnas nuevas (mesesLimite) conservando las filas."""
    columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(archivoscomponentes)")}
    if columnas and "mesesLimite" not in columnas:
        logging.info("Migrando archivoscomponentes: se añade la columna mesesLimite")
        conexion.execute("ALTER TABLE archivoscomponentes ADD COLUMN mesesLimite integer")
        conexion.commit()


def usuariosConNombre(conexion):
    return [fila[0] for fila in conexion.execute(
        "SELECT DISTINCT usuario FROM EntradasUsers WHERE trim(COALESCE(usuario, '')) <> '' ORDER BY usuario")]


def crearComponentesPorDefecto(conexion, usuario=None) -> int:
    """Para cada componente de la tabla Componente que el usuario no tenga en archivoscomponentes
    (sin distinguir mayúsculas), crea uno con descripción POR DEFECTO, fecha de alta FECHA_ALTA_POR_DEFECTO
    y los límites por defecto de ese componente (limitesPorDefecto); a los POR DEFECTO que ya existían les
    actualiza esos límites. usuario=None lo hace para todos los usuarios. Devuelve cuántos ha creado."""
    asegurarColumnasArchivosComponentes(conexion)
    asegurarColumnasComponente(conexion)
    usuarios = [usuario] if usuario else usuariosConNombre(conexion)
    creados = 0
    try:
        for nombre_usuario in usuarios:
            faltan = [fila[0] for fila in conexion.execute(
                """SELECT MIN(c.nombre) FROM Componente c
                   WHERE trim(COALESCE(c.nombre, '')) <> ''
                     AND NOT EXISTS (SELECT 1 FROM archivoscomponentes ac
                                     WHERE ac.usuario = ? AND lower(ac.elemento) = lower(c.nombre))
                   GROUP BY lower(c.nombre)""", (nombre_usuario,))]
            conexion.executemany(
                """INSERT INTO archivoscomponentes (usuario, elemento, descripcion, fechaInsercion,
                       distanciaLimite, tiempoLimite, mesesLimite, activo) VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                [(nombre_usuario, nombre, DESCRIPCION_POR_DEFECTO, FECHA_ALTA_POR_DEFECTO.isoformat(),
                  *limitesComponente(conexion, nombre, nombre_usuario)) for nombre in faltan],
            )
            creados += len(faltan)
            # Los POR DEFECTO aún no los ha definido el usuario: se les ponen los límites por defecto actuales
            existentes = conexion.execute(
                "SELECT id, elemento FROM archivoscomponentes WHERE usuario = ? AND descripcion = ?",
                (nombre_usuario, DESCRIPCION_POR_DEFECTO)).fetchall()
            conexion.executemany(
                "UPDATE archivoscomponentes SET distanciaLimite = ?, tiempoLimite = ?, mesesLimite = ? WHERE id = ?",
                [(*limitesComponente(conexion, elemento, nombre_usuario), id_) for id_, elemento in existentes],
            )
        conexion.commit()
    except sqlite3.Error:
        conexion.rollback()
        raise
    if creados:
        logging.info("Creados %d componentes POR DEFECTO (%s)", creados, usuario or "todos")
    return creados


@contextmanager
def espera_corta(conexion, milisegundos=ESPERA_CORTA_BD_MS):
    """Mientras dura, una escritura bloqueada por otro programa falla en `milisegundos` en vez de esperar 5 s."""
    conexion.execute(f"PRAGMA busy_timeout = {int(milisegundos)}")
    try:
        yield conexion
    finally:
        conexion.execute(f"PRAGMA busy_timeout = {ESPERA_BD_MS}")


def calcularKmComponentes(conexion, usuario=None) -> int:
    """Suma los km de las actividades Strava (tipo Ride, desde la fecha de alta) a cada componente y lo
    guarda en datosComponente. usuario=None calcula todos. Devuelve cuántos componentes se han actualizado."""
    asegurarTablaDatosComponente(conexion)
    stravaConnect.asegurarTablaActividades(conexion)
    crearComponentesPorDefecto(conexion, usuario)
    try:
        conexion.execute(
            "DELETE FROM datosComponente WHERE idComponente NOT IN (SELECT id FROM archivoscomponentes)")
        cursor = conexion.execute(SQL_CALCULAR_KM_COMPONENTES, {"usuario": usuario})
        conexion.commit()
    except sqlite3.Error:
        conexion.rollback()
        raise
    logging.info("Km de componentes calculados (%s): %d componentes", usuario or "todos", cursor.rowcount)
    return cursor.rowcount


# Tabla 1 de Estadísticas: todos los componentes del catálogo (tabla Componente), uno por línea, más los
# que el usuario haya dado de alta con otro nombre. Si el usuario tiene varias altas de un componente se
# muestra la activa más reciente; si no tiene ninguna, el resto de columnas sale vacío.
SQL_COMPONENTES_ESTADISTICAS = """
WITH del_usuario AS (
    SELECT ac.*, ROW_NUMBER() OVER (
               PARTITION BY lower(ac.elemento)
               ORDER BY ac.activo DESC, ac.fechaInsercion DESC, ac.id DESC) AS orden
    FROM archivoscomponentes ac
    WHERE ac.usuario = ?
),
ultimo AS (SELECT * FROM del_usuario WHERE orden = 1),
catalogo AS (
    SELECT nombre FROM Componente WHERE trim(COALESCE(nombre, '')) <> ''
    UNION
    SELECT elemento FROM ultimo
    WHERE lower(elemento) NOT IN (SELECT lower(nombre) FROM Componente WHERE nombre IS NOT NULL)
)
SELECT COALESCE(u.elemento, c.nombre), u.descripcion, u.fechaInsercion, u.distanciaLimite,
       dc.km, u.tiempoLimite, dc.horas, {meses_limite},
       -- meses completos desde el alta hasta hoy
       CASE WHEN date(u.fechaInsercion) IS NOT NULL THEN
           (CAST(strftime('%Y', 'now', 'localtime') AS INTEGER) - CAST(strftime('%Y', u.fechaInsercion) AS INTEGER)) * 12
         + (CAST(strftime('%m', 'now', 'localtime') AS INTEGER) - CAST(strftime('%m', u.fechaInsercion) AS INTEGER))
         - (CAST(strftime('%d', 'now', 'localtime') AS INTEGER) < CAST(strftime('%d', u.fechaInsercion) AS INTEGER))
       END,
       u.activo
FROM catalogo c
LEFT JOIN ultimo u ON lower(u.elemento) = lower(c.nombre)
LEFT JOIN datosComponente dc ON dc.idComponente = u.id
"""

# ---- Pantallas de mantenimiento ----
PANTALLA_MANTENIMIENTO = "mantenimiento"

# Todos los textos son claves de translations_data.xml. El componente se guarda en la BD con el
# texto del idioma por defecto (castellano), sea cual sea el idioma de la pantalla.
# clave -> (título, filas de botones, alto de botón o None, pantalla anterior o None = menú usuario)
PANTALLAS_MANTENIMIENTO = {
    PANTALLA_MANTENIMIENTO: (
        "menu.mantenimiento",
        [
            ["taller.cadena", "taller.pastillas", "taller.cubiertas", "taller.tubeless"],
            ["taller.cinta", "taller.disco", "taller.rodamientos", "taller.otros"],
        ],
        None,
        None,
    ),
    "componentes": (
        "mant.componentes",
        [
            ["pieza.cadena", "pieza.pastillas", "pieza.cubierta", "pieza.tubeless"],
            ["pieza.cinta", "pieza.disco", "pieza.rodamientos"],
            ["pieza.horquilla", "pieza.suspension", "pieza.otros"],
        ],
        150,
        PANTALLA_MANTENIMIENTO,
    ),
    "otros": (
        "mant.otros",
        [
            ["pieza.pedalier", "pieza.bielas", "pieza.purgado", "pieza.cambio"],
            ["pieza.pinonera", "pieza.platos", "pieza.manetas", "pieza.pedales"],
            ["pieza.engrase", "pieza.tija", "pieza.sillin", "pieza.pedales", "pieza.engrase_ejes"],
        ],
        150,
        "componentes",
    ),
    "rodamientos": (
        "mant.rodamientos",
        [
            ["pieza.direccion_sup", "pieza.direccion_inf", "pieza.rueda_del_int", "pieza.rueda_del_ext"],
            ["pieza.rueda_tra_int", "pieza.rueda_tra_ext"],
        ],
        150,
        "componentes",
    ),
    "tubeless": (
        "mant.tubeless",
        [
            ["pieza.liquido", "pieza.pinchazo"],
            ["pieza.cinta_tubeless", "pieza.anadido"],
        ],
        150,
        "componentes",
    ),
}

# (pantalla, clave del botón) -> subpantalla que abre. El resto de botones abren el alta de componente.
SUBPANTALLAS_MANTENIMIENTO = {
    (PANTALLA_MANTENIMIENTO, "taller.otros"): "componentes",
    ("componentes", "pieza.otros"): "otros",
    ("componentes", "pieza.rodamientos"): "rodamientos",
    ("componentes", "pieza.tubeless"): "tubeless",
}


class AppPaths:
    app = None

    @classmethod
    def init(cls, app):
        cls.app = app

    @classmethod
    def base_dir(cls, kind="data"):
        """
        kind: data | cache
        """

        # 🟢 Caso 1: Toga (Briefcase dev / iOS / macOS app)
        if cls.app and hasattr(cls.app, "paths"):
            return getattr(cls.app.paths, kind)

        # 🟡 Caso 2: desarrollo local (Cursor, PyCharm, python directo)
        project_root = Path(__file__).resolve().parent.parent.parent

        if kind == "data":
            base = project_root / "data"
        elif kind == "cache":
            base = project_root / "cache"
        else:
            base = project_root / kind

        base.mkdir(parents=True, exist_ok=True)
        return base

    @classmethod
    def get(cls, kind="data", *parts):
        base = cls.base_dir(kind)

        if not parts:
            return base

        path = base.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

# Fecha por defecto del selector «Desde» de Strava Sync
FECHA_INICIO_STRAVA = date(2024, 1, 1)       # fecha por defecto del selector de Strava Sync
FECHA_ALTA_POR_DEFECTO = date(2026, 1, 1)    # fecha de alta de los componentes POR DEFECTO


class BikeCompFollowApp(toga.App):
    label_estado = ""
    cursor = None
    sqliteConnection = 0
    index_entrada = 0
    db_path = None
    log_path = None
    usuarioSeleccionado = None
    sync_strava_en_curso = False

    def startup(self):
        # ✅ AQUÍ sí existe self
        AppPaths.init(self)
        print("APP ID:", self.app_id)

        self.main_window = toga.MainWindow(title=self.formal_name)
        
        # Obtener la ruta del directorio actual del script
        self.log_path = AppPaths.get("data", "BikeCFU", "bikecfu.log")
        print("DATA DIR:", self.paths.data)
        print("Log DIR:", self.log_path)
        
        logging.basicConfig(filename=str(self.log_path), level=logging.DEBUG,
        format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',datefmt='%Y-%m-%d %H:%M:%S')
        logging.info("Inicio BikeCompFollowApp iOS App!!!")
        print("Inicio BikeCompFollowApp iOS App!!!")

        self.arrancarDB()
        self.crearTablaAlertThresholds()
        self.crearTablaAjustes()
        self.crearTablaActividadesStrava()
        self.crearTablaDatosComponente()
        self.limpiarDuplicadosStrava()
        self.cargarIdioma()

        # Pantalla inicial al arrancar
        self.main_window.content = self.construir_pantalla_inicial()
        self.main_window.show()

    def chequearIntegrarDB(self):
        self.cursor.execute("PRAGMA integrity_check;")
        result = self.cursor.fetchone()

        if result[0] == "ok":
            print("✅ DB íntegra")
        else:
            print("❌ DB corrupta")

    # Método para borrar datos en cascada.
    def borrarDatosDB(self):
        logging.info("Dentro borrar Datos")

    # Método para lanzar Notificaciones
    def lanzarNotificacion(self, titulo, mensaje) -> bool:
        return notificaciones.notificar(titulo, mensaje)

    def crearDBBasica(self):
        try:
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS Componente (id INTEGER PRIMARY KEY,nombre TEXT)""")
            asegurarTablaDatosComponente(self.sqliteConnection)
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS stravaValores  (id integer PRIMARY KEY,  fecha date not NULL, valor INTEGER not NULL,  ascenso INTEGER, tipo TEXT not null, num_actividades INTEGER, horas INTEGER)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS EntradasUsers (id integer PRIMARY KEY,  fecha Date,  nombre text NOT NULL,  usuario text,  tipov integer NOT NULL, descripcion  TEXT NOT NULL, FOREIGN KEY (tipov) REFERENCES tipo_vehiculo(id))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS linked_elements (id integer PRIMARY KEY, fecha Date, Entrada_num integer, num_elemento, FOREIGN KEY (Entrada_num) REFERENCES EntradasUsers(id), FOREIGN KEY (num_Elemento) REFERENCES Componente(id))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS tipo_vehiculo (id	INTEGER PRIMARY KEY,vehiculo TEXT)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS archivoscomponentes (id INTEGER PRIMARY KEY, usuario NOT NULL, elemento TEXT NOT NULL, descripcion TEXT, marca TEXT, fechaInsercion Date NOT NULL, distanciaLimite integer, tiempoLimite integer, activo BOOLEAN DEFAULT True, mesesLimite integer)""")
        except sqlite3.Error as error:
            logging.error("Error al crear Tablas en SQLite: %s", error)
            logging.error("Tablas ya existen en SQLite")
        finally:
            logging.info('Tablas DB creadas')
            self.sqliteConnection.commit()

        # Carga de los datos básicos
        try:
            self.cursor.executemany("INSERT INTO tipo_vehiculo (vehiculo) VALUES (?)", [(v,) for v in VEHICULOS_INICIALES])
            self.cursor.executemany("INSERT INTO Componente (nombre) VALUES (?)", [(e,) for e in ELEMENTOS_INICIALES])
            self.sqliteConnection.commit()
            asegurarColumnasComponente(self.sqliteConnection)
            logging.info('Carga de datos básicos (tipo_vehiculo, Componente) correcta.')
        except sqlite3.Error as error:
            logging.error("Error al cargar datos de las Tablas Básicas en SQLite: %s", error)

    def renombrarTablasAntiguas(self) -> bool:
        """Renombra datos -> datosComponente y Elemento -> Componente en una BD existente, sin perder filas.

        SQLite actualiza solo las FOREIGN KEY de otras tablas (linked_elements) que apuntaban al nombre antiguo.
        """
        try:
            # En SQLite los nombres de tabla no distinguen mayúsculas
            existentes = {fila[0].casefold() for fila in self.sqliteConnection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for antigua, nueva in TABLAS_RENOMBRADAS.items():
                if antigua.casefold() not in existentes:
                    continue
                if nueva.casefold() in existentes:
                    if self.sqliteConnection.execute(f'SELECT COUNT(*) FROM "{nueva}"').fetchone()[0]:
                        logging.warning("Existen %s y %s con datos: no se renombra %s", antigua, nueva, antigua)
                        continue
                    self.sqliteConnection.execute(f'DROP TABLE "{nueva}"')   # la nueva estaba vacía
                self.sqliteConnection.execute(f'ALTER TABLE "{antigua}" RENAME TO "{nueva}"')
                logging.info("Tabla %s renombrada a %s", antigua, nueva)
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            self.sqliteConnection.rollback()
            logging.error("Error al renombrar tablas antiguas: %s", error)
            return False
        return True

    def arrancarDB(self):
        # Obtener la ruta del directorio actual del script
        
        self.db_path = AppPaths.get("data", "BikeCFU", "dbbcfu.db")

        # Esto crea el fichero si no existe
        self.sqliteConnection = sqlite3.connect(self.db_path)
        self.cursor = self.sqliteConnection.cursor()

        print("DB DIR:", self.db_path)
        self.renombrarTablasAntiguas()
        
        self.sqliteConnection.commit()
        print("Base de datos lista")

        logging.info('Creación Base de Datos y Tablas principales.')
        try:
            self.cursor.execute("""SELECT name FROM sqlite_master WHERE type='table' AND name='EntradasUsers'""")
            if self.cursor.fetchone() is None:
                print("⚠️ Base de datos vacía o incorrecta")
                self.crearDBBasica()
                logging.info('Ejecución SQL creación tablas Básicas.')
                return

            logging.info('Ejecución SQL creación tablas.')
        except sqlite3.Error as error:
            logging.error("Error al crear Tablas en SQLite: %s", error)
            logging.error("Tablas ya existen en SQLite")
        finally:
            logging.info('Tablas DB creadas')

        # Crear tabla de tipos de vehículo si no existe
        try:
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS tipo_vehiculo (
                    id integer PRIMARY KEY,
                    vehiculo TEXT
                )"""
            )

            # Valores por defecto si la tabla está vacía
            self.cursor.execute("SELECT COUNT(*) FROM tipo_vehiculo")
            count = self.cursor.fetchone()[0]
            if count == 0:
                self.cursor.executemany(
                    "INSERT INTO tipo_vehiculo (vehiculo) VALUES (?)",
                    [("Carretera",), ("Montaña",), ("Híbrida",)]
                )
                self.sqliteConnection.commit()
                logging.info("Tabla tipo_vehiculo creada y rellenada con valores por defecto.")
        except sqlite3.Error as error:
            logging.error("Error al crear/rellenar tabla tipo_vehiculo en SQLite %s", error)

        logging.info('Fin acciones Base de Datos')

    # -------- Ajustes (clave/valor) e idioma --------
    def crearTablaAjustes(self) -> bool:
        try:
            self.sqliteConnection.execute("CREATE TABLE IF NOT EXISTS ajustes (clave TEXT PRIMARY KEY, valor TEXT)")
            self.sqliteConnection.commit()
            return True
        except sqlite3.Error as error:
            logging.error("Error al crear la tabla ajustes: %s", error)
            return False

    def leerAjuste(self, clave, por_defecto=None):
        try:
            fila = self.sqliteConnection.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
        except sqlite3.Error as error:
            logging.error("Error al leer el ajuste %s: %s", clave, error)
            return por_defecto
        return fila[0] if fila else por_defecto

    def guardarAjuste(self, clave, valor) -> bool:
        try:
            self.sqliteConnection.execute(
                "INSERT INTO ajustes (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (clave, valor),
            )
            self.sqliteConnection.commit()
            return True
        except sqlite3.Error as error:
            logging.error("Error al guardar el ajuste %s: %s", clave, error)
            return False

    def cargarIdioma(self):
        """Carga el XML de textos y aplica el idioma guardado (castellano si no hay ninguno)."""
        translations.load()
        translations.set_language(self.leerAjuste("idioma", translations.current().code))

    def cambiarIdioma(self, widget=None):
        """Botón de la bandera: pasa al siguiente idioma, lo guarda y redibuja la pantalla."""
        idioma = translations.next_language()
        translations.set_language(idioma.code)
        if not self.guardarAjuste("idioma", idioma.code):
            logging.error("No se pudo guardar el idioma %s; solo se aplica a esta sesión", idioma.code)
        self.volver_pantalla_inicial()

    def cerrarDB(self):
        #Cerramos base de datos
        self.sqliteConnection.close()
        logging.info("The SQLite connection is closed")

    # -------- Utilidades comunes de interfaz y BD --------
    def _mostrar(self, contenido):
        self.main_window.content = contenido

    def _leer_lista(self, sql, params=(), por_defecto=()):
        """Devuelve la primera columna de una SELECT, o `por_defecto` si falla o está vacía."""
        try:
            valores = [fila[0] for fila in self.sqliteConnection.execute(sql, params)]
        except sqlite3.Error as error:
            logging.error("Error en la consulta '%s': %s", sql, error)
            valores = []
        return valores or list(por_defecto)

    @staticmethod
    def _campo(texto, widget):
        """Fila de formulario: etiqueta a la izquierda y widget a la derecha."""
        caja = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))
        caja.add(toga.Label(texto, style=Pack(margin_right=10)))
        caja.add(widget)
        return caja

    @staticmethod
    def _texto(placeholder=None, **kwargs):
        if placeholder is None:
            placeholder = t("comun.placeholder")
        return toga.TextInput(placeholder=placeholder, style=Pack(width=ANCHO_CAMPO), **kwargs)

    @staticmethod
    def _boton(texto, accion):
        return toga.Button(texto, on_press=accion, style=Pack(margin=10))

    def _boton_volver(self, accion):
        return self._boton(t("comun.volver"), lambda widget: accion())

    @staticmethod
    def _barra_inferior(izquierda=None, derecha=None):
        """Barra inferior con un widget a la izquierda y otro a la derecha."""
        barra = toga.Box(style=Pack(direction=ROW))
        if izquierda is not None:
            barra.add(izquierda)
        barra.add(toga.Box(style=Pack(flex=1)))
        if derecha is not None:
            barra.add(derecha)
        return barra

    @staticmethod
    def _pantalla(contenido, barra_inferior, margen=20):
        """Pantalla estándar: contenido arriba y barra inferior empujada abajo."""
        main_box = toga.Box(style=Pack(direction=COLUMN, margin=margen))
        main_box.add(contenido)
        main_box.add(toga.Box(style=Pack(flex=1)))
        main_box.add(barra_inferior)
        return main_box

    @staticmethod
    def _formulario():
        return toga.Box(style=Pack(direction=COLUMN, margin_left=40, align_items='start'))

    # -------- Pantalla 1 (inicial) --------
    def construir_pantalla_inicial(self):
        self.usuarioSeleccionado = ""

        contenido_box = toga.Box(
            style=Pack(direction=COLUMN, align_items=CENTER, gap=15)
        )

        self.label = toga.Label(
            t("inicio.titulo"),
            style=Pack(margin_bottom=20, text_align=CENTER)
        )
        contenido_box.add(self.label)

        try:
            filas = self.sqliteConnection.execute("SELECT nombre, usuario FROM EntradasUsers").fetchall()
        except sqlite3.Error as error:
            logging.error("Error al leer la tabla EntradasUsers: %s", error)
            filas = []

        for nombre, usuario in filas:
            contenido_box.add(toga.Button(
                f"{usuario or ''}-{nombre or ''}",
                on_press=lambda widget, valor=usuario: self.ir_a_menu_usuario(widget, valor),
                style=Pack(width=140, height=60, margin=0),
            ))

        self.boton_idioma = toga.Button(
            translations.current().flag,
            on_press=self.cambiarIdioma,
            style=Pack(margin=10, font_size=22),
        )
        barra_inferior = self._barra_inferior(
            derecha=toga.Box(
                children=[self._boton(t("inicio.nuevo_usuario"), self.ir_a_pantalla_dos), self.boton_idioma],
                style=Pack(direction=ROW, align_items=CENTER),
            ),
        )
        return self._pantalla(contenido_box, barra_inferior)

    def volver_pantalla_inicial(self, widget=None):
        self._mostrar(self.construir_pantalla_inicial())

    # -------- Menú del usuario: Estadísticas / Mantenimiento --------
    def construir_menu_usuario(self, usuario):
        self.usuarioSeleccionado = usuario

        estilo_comun = dict(
            width=ANCHO_BOTONES_MENU, color="#FFFFFF", font_size=16, font_weight="bold",
        )
        self.boton_estadisticas = toga.Button(
            t("menu.estadisticas"),
            on_press=lambda widget: self.ir_a_pantalla_tres(widget, usuario),
            style=Pack(height=ALTO_ESTADISTICAS, background_color=COLOR_ESTADISTICAS, **estilo_comun),
        )
        self.boton_mantenimiento = toga.Button(
            t("menu.mantenimiento"),
            on_press=lambda widget: self.ir_a_mantenimiento(PANTALLA_MANTENIMIENTO),
            style=Pack(height=ALTO_MANTENIMIENTO, background_color=COLOR_MANTENIMIENTO, **estilo_comun),
        )
        pintar_fondo_boton(self.boton_estadisticas, COLOR_ESTADISTICAS)
        pintar_fondo_boton(self.boton_mantenimiento, COLOR_MANTENIMIENTO)

        contenido = toga.Box(
            children=[
                toga.Label(t("menu.usuario", usuario=usuario), style=Pack(margin_bottom=20, font_size=16)),
                self.boton_estadisticas,
                toga.Box(style=Pack(height=ESPACIO)),
                self.boton_mantenimiento,
            ],
            # Sin flex: el espaciador de _pantalla ya empuja la barra inferior hacia abajo.
            # Con flex=1 en ambos, Toga daba a este bloque su alto mínimo más la mitad del hueco
            # y la barra (Volver / Strava Sync) quedaba fuera de la ventana.
            style=Pack(direction=COLUMN, align_items=CENTER),
        )

        barra_inferior = self._barra_inferior(
            izquierda=self._boton_volver(self.volver_pantalla_inicial),
            derecha=self._boton(t("menu.strava"), self.ir_a_pantalla_recoleccionDatos),
        )
        return self._pantalla(contenido, barra_inferior)

    def ir_a_menu_usuario(self, widget=None, usuario=None):
        if usuario is None:
            usuario = self.usuarioSeleccionado
        self._mostrar(self.construir_menu_usuario(usuario))
        self.mostrarAlertaComponentes(usuario)

    # -------- Ventana de Alerta: componentes a cambiar de manera urgente --------
    def componentesUrgentes(self, usuario):
        """Componentes que el usuario debe cambiar ya. De momento, lista de prueba fija."""
        return list(COMPONENTES_URGENTES_PRUEBA)

    @staticmethod
    def textoAlertaComponentes(componentes):
        return "\n".join([t("aviso.urgentes"), ""] + [f"• {componente}" for componente in componentes])

    def mostrarAlertaComponentes(self, usuario):
        """Abre la ventana de Alerta si hay componentes urgentes. Devuelve su contenido (o None si no hay).

        Es una ventana propia y no un toga.InfoDialog porque el diálogo nativo (NSAlert en macOS) no deja
        cambiar el color ni el tamaño del título."""
        componentes = self.componentesUrgentes(usuario)
        if not componentes:
            return None
        logging.info("Alerta de componentes urgentes (%s): %s", usuario, ", ".join(componentes))
        contenido = self.construirVentanaAlerta(componentes)
        self._abrir_ventana_alerta(contenido, t("aviso.titulo"))
        return contenido

    def construirVentanaAlerta(self, componentes):
        """Contenido de la ventana de Alerta de componentes urgentes."""
        caja = self.construirVentanaAviso(t("aviso.titulo"), self.textoAlertaComponentes(componentes))
        self.label_titulo_alerta, self.label_mensaje_alerta = caja.label_titulo, caja.label_mensaje
        self.boton_aceptar_alerta = caja.boton_aceptar
        return caja

    def construirVentanaAviso(self, titulo, mensaje):
        """Contenido de una ventana de aviso: título en rojo y tamaño 24, el mensaje y el botón Aceptar,
        que cierra la ventana en la que se abra (ver _abrir_ventana_alerta)."""
        caja = toga.Box(style=Pack(direction=COLUMN, margin=20))
        caja.ventana = None
        caja.label_titulo = toga.Label(
            titulo, style=Pack(color=ROJO_ALERTA, font_size=TAMANO_TITULO_ALERTA, font_weight="bold", margin_bottom=10))
        caja.label_mensaje = toga.Label(mensaje, style=Pack(font_size=14))
        caja.boton_aceptar = toga.Button(
            t("aviso.aceptar"), on_press=lambda widget: self.cerrarVentanaAviso(caja), style=Pack(width=120, margin_top=20))
        for hijo in (caja.label_titulo, caja.label_mensaje, toga.Box(style=Pack(flex=1)),
                     toga.Box(children=[toga.Box(style=Pack(flex=1)), caja.boton_aceptar], style=Pack(direction=ROW))):
            caja.add(hijo)
        return caja

    def _abrir_ventana_alerta(self, contenido, titulo_ventana):
        """Abre `contenido` en una ventana propia (no bloquea la principal). Devuelve la ventana."""
        if toga.App.app is None:     # sin app de Toga (tests sin GUI): no se puede crear la ventana
            logging.warning("Sin app de Toga: no se abre la ventana %r", titulo_ventana)
            return None
        ventana = toga.Window(title=titulo_ventana, size=TAMANO_VENTANA_ALERTA, resizable=False,
                              minimizable=False, content=contenido)
        contenido.ventana = ventana
        ventana.show()
        return ventana

    def cerrarVentanaAviso(self, contenido):
        ventana = getattr(contenido, "ventana", None)
        if ventana is not None:
            ventana.close()
        contenido.ventana = None

    # -------- Pantallas de mantenimiento (cuadrículas de componentes) --------
    def construir_pantalla_mantenimiento(self, clave):
        titulo, filas, alto_boton, _anterior = PANTALLAS_MANTENIMIENTO[clave]
        estilo_boton = dict(flex=1, font_size=14)
        if alto_boton:
            estilo_boton["height"] = alto_boton

        rejilla = toga.Box(style=Pack(direction=COLUMN, flex=1))
        for n, textos in enumerate(filas):
            if n:
                rejilla.add(toga.Box(style=Pack(height=ESPACIO)))
            fila = toga.Box(style=Pack(direction=ROW, flex=1))
            for i, boton in enumerate(textos):
                if i:
                    fila.add(toga.Box(style=Pack(width=ESPACIO)))
                fila.add(toga.Button(
                    t(boton),
                    on_press=lambda widget, b=boton: self.pulsar_boton_mantenimiento(clave, b),
                    style=Pack(**estilo_boton),
                ))
            rejilla.add(fila)

        contenido = toga.Box(style=Pack(direction=COLUMN, flex=1))
        contenido.add(toga.Label(t(titulo), style=Pack(margin_bottom=ESPACIO, font_size=16)))
        contenido.add(rejilla)

        main_box = toga.Box(style=Pack(direction=COLUMN, margin=10))
        main_box.add(contenido)
        main_box.add(self._barra_inferior(
            izquierda=self._boton_volver(lambda: self.volver_desde_mantenimiento(clave)),
        ))
        return main_box

    def ir_a_mantenimiento(self, clave):
        self._mostrar(self.construir_pantalla_mantenimiento(clave))

    def volver_desde_mantenimiento(self, clave):
        anterior = PANTALLAS_MANTENIMIENTO[clave][3]
        if anterior is None:
            self.ir_a_menu_usuario()
        else:
            self.ir_a_mantenimiento(anterior)

    def pulsar_boton_mantenimiento(self, clave, boton):
        """Un botón abre una subpantalla si la tiene; si no, el alta del componente."""
        destino = SUBPANTALLAS_MANTENIMIENTO.get((clave, boton))
        if destino:
            self.ir_a_mantenimiento(destino)
        else:
            self._mostrar(self.construir_pantalla_cinco(
                self.usuarioSeleccionado,
                elemento=translations.default_text(boton),
                volver=lambda: self.ir_a_mantenimiento(clave),
            ))

    # -------- Pantalla 2 (alta de usuario / vehículo) --------
    def ir_a_pantalla_dos(self, widget=None):
        self._mostrar(self.construir_pantalla_dos())

    def construir_pantalla_dos(self):
        tipos_vehiculo = self._leer_lista(
            "SELECT vehiculo FROM tipo_vehiculo ORDER BY vehiculo",
            por_defecto=["Carretera", "Montaña", "Híbrida"],
        )
        tipos_elemento = self._leer_lista(
            "SELECT nombre FROM Componente ORDER BY nombre",
            por_defecto=ELEMENTOS_POR_DEFECTO,
        )

        self.label_pantalla_dos = toga.Label(
            t("alta.titulo"),
            style=Pack(margin_bottom=20, text_align=CENTER)
        )
        self.entrada_texto = self._texto()
        self.usuario_texto = self._texto()
        self.descripcion_texto = self._texto()
        self.selection_tipo_vehiculo = toga.Selection(items=tipos_vehiculo, style=Pack(width=ANCHO_CAMPO))
        self.selection_elemento = toga.Selection(items=tipos_elemento, style=Pack(width=ANCHO_CAMPO))
        self.entrada_fecha = self._texto(t("campo.fecha_placeholder"), value=datetime.today().strftime("%Y-%m-%d"))
        boton_cargar = self._boton(t("comun.cargar"), self.cargar_entrada)
        boton_volver = self._boton_volver(self.volver_pantalla_inicial)

        contenido_box = self._formulario()
        contenido_box.add(self.label_pantalla_dos)
        contenido_box.add(self._campo(t("campo.nombre"), self.entrada_texto))
        contenido_box.add(self._campo(t("campo.usuario"), self.usuario_texto))
        contenido_box.add(self._campo(t("campo.descripcion"), self.descripcion_texto))
        contenido_box.add(self._campo(t("campo.tipo_vehiculo"), self.selection_tipo_vehiculo))
        contenido_box.add(self._campo(t("campo.elemento"), self.selection_elemento))
        contenido_box.add(self._campo(t("campo.fecha"), self.entrada_fecha))
        contenido_box.add(boton_cargar)

        # Orden de tabulación (Tab) entre campos
        orden_foco = [
            self.entrada_texto, self.usuario_texto, self.descripcion_texto,
            self.selection_tipo_vehiculo, self.selection_elemento, self.entrada_fecha,
            boton_cargar, boton_volver,
        ]
        # En macOS (Cocoa) tab_index no está implementado; enlazar cadena de foco a mano
        if sys.platform == "darwin":
            try:
                for actual, siguiente in zip(orden_foco, orden_foco[1:] + orden_foco[:1]):
                    actual._impl.native.nextKeyView = siguiente._impl.native
            except Exception as e:
                logging.debug("No se pudo configurar cadena Tab en Cocoa: %s", e)
        else:
            for i, widget in enumerate(orden_foco):
                widget.tab_index = i

        return self._pantalla(contenido_box, self._barra_inferior(izquierda=boton_volver))

    def cargar_entrada(self, widget):
        texto1 = (self.entrada_texto.value or "").strip()
        textoUser = (self.usuario_texto.value or "").strip()
        texto2 = (self.descripcion_texto.value or "").strip()
        tipov = (self.selection_tipo_vehiculo.value or "").strip()
        f = (self.entrada_fecha.value or "").strip() or datetime.today().strftime("%Y-%m-%d")

        try:
            self.sqliteConnection.execute(
                "INSERT INTO EntradasUsers (fecha, nombre, usuario, tipov, descripcion) VALUES (?, ?, ?, ?, ?)",
                (f, texto1, textoUser, tipov, texto2)
            )
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            logging.error("Error al insertar en EntradasUsers: %s", error)
            self._mostrar_estado(self.label_pantalla_dos, t("estado.entrada_error"), ok=False)
            return
        self._mostrar_estado(self.label_pantalla_dos, t("estado.entrada_ok"))
        logging.info("Datos de Entrada cargados correctamente.")

    @staticmethod
    def _mostrar_estado(label, texto, ok=True):
        label.text = texto
        label.style.color = rgb(0, 255, 0) if ok else rgb(255, 0, 0)

    # -------- Pantalla 3 (Estadísticas: componentes del usuario) --------
    def construir_pantalla_tres(self, valor):
        self.usuarioSeleccionado = valor

        # "Usuario:" en azul a la izquierda y el usuario; a la derecha, mensajes de estado (errores)
        self.label_usuario_estadisticas = toga.Label(t("componente.usuario"), style=Pack(color=AZUL))
        self.label_usuario_seleccionado_est = toga.Label(valor or "")
        self.label_pantalla_dos = toga.Label("")
        linea_usuario = toga.Box(
            children=[self.label_usuario_estadisticas, self.label_usuario_seleccionado_est,
                      toga.Box(style=Pack(flex=1)), self.label_pantalla_dos],
            style=Pack(direction=ROW, margin_bottom=20),
        )

        try:
            data = [(*fila[:-1], texto_activo(fila[-1])) for fila in self.componentesEstadisticas(valor)]
            logging.info("Datos de TABLA LEÍDOS correctamente.")
        except sqlite3.Error as error:
            logging.error("Error en el SELECT de la TABLA Comp: %s", error)
            self._mostrar_estado(self.label_pantalla_dos, t("estado.lectura_error"), ok=False)
            data = []

        self.componentes_disponibles = [fila[0] for fila in data if fila and fila[0] is not None]
        # Altura según nº de filas (Toga no la calcula sola). Tope para listas largas → scroll dentro de la tabla.
        _h_cabecera, _h_fila, _h_max = 28, 22, 520
        _altura_tabla = min(_h_cabecera + max(len(data), 1) * _h_fila, _h_max)

        self.tabla = toga.Table(
            columns=_columnas(COLUMNAS_COMPONENTES),
            data=data,
            on_select=self.actualizar_limites_componente_seleccionado,
            style=Pack(height=_altura_tabla, flex=1),
        )

        # Tabla "Tiempo y Kms por Modalidad" (Road, MTB, Gravel x los 3 últimos años)
        self.anios_estadisticas = aniosEstadisticas()
        try:
            self.filas_modalidad, self.anios_sin_datos = kmsHorasPorModalidad(
                self.sqliteConnection, valor, self.anios_estadisticas)
        except sqlite3.Error as error:
            logging.error("Error al leer los km y horas por modalidad: %s", error)
            self.filas_modalidad = [(m, None) + (0.0, 0.0) * len(self.anios_estadisticas)
                                    for m in MODALIDADES_ESTADISTICAS]
            self.anios_sin_datos = list(self.anios_estadisticas)
        self.Title_tablaModalidad = toga.Label(
            t("estadisticas.modalidad_titulo"), style=Pack(text_align=LEFT, font_size=16, margin_bottom=5))
        self.tablaModalidad = self.construirTablaModalidad(self.filas_modalidad, self.anios_estadisticas)

        self.Title_tablaLimites = toga.Label(
            t("estadisticas.limites"),
            style=Pack(text_align=LEFT, font_size=16)
        )

        # Tabla de detalle: se rellena al seleccionar una fila de la tabla principal.
        self.tablaLimites = toga.Table(
            columns=_columnas(COLUMNAS_LIMITES),
            data=[],
            style=Pack(height=_altura_tabla, flex=1),
        )

        contenido_box = toga.Box(
            children=[
                linea_usuario,
                self.tabla,
                toga.Box(style=Pack(height=20)),
                self.Title_tablaModalidad,
                self.tablaModalidad,
                toga.Box(style=Pack(height=20)),
                self.Title_tablaLimites,
                self.tablaLimites,
            ],
            style=Pack(direction=COLUMN, flex=1),
        )

        botones_derecha = toga.Box(
            children=[
                self._boton(t("estadisticas.nuevo_componente"), lambda widget: self.ir_a_pantalla_cinco(widget, valor)),
                self._boton(t("estadisticas.nuevo_limite"), lambda widget: self.PantallaNuevaAlerta(
                    self.obtener_componente_seleccionado(),
                    self.componentes_disponibles,
                )),
            ],
            style=Pack(direction=COLUMN),
        )

        main_box = toga.Box(style=Pack(direction=COLUMN, margin=10))
        main_box.add(contenido_box)
        main_box.add(self._barra_inferior(
            izquierda=self._boton_volver(self.ir_a_menu_usuario),
            derecha=botones_derecha,
        ))
        return main_box

    def crearTablaDatosComponente(self) -> bool:
        try:
            asegurarColumnasArchivosComponentes(self.sqliteConnection)
            asegurarColumnasComponente(self.sqliteConnection)
            asegurarTablaDatosComponente(self.sqliteConnection)
        except sqlite3.Error as error:
            logging.error("Error al crear la tabla datosComponente: %s", error)
            return False
        return True

    def calcularKmComponentes(self, usuario=None) -> int:
        """Recalcula los km de cada componente (ver calcularKmComponentes). -1 si hay error."""
        try:
            return calcularKmComponentes(self.sqliteConnection, usuario)
        except sqlite3.Error as error:
            logging.error("Error al calcular los km de los componentes: %s", error)
            return -1

    def componentesEstadisticas(self, usuario):
        """Filas de la tabla 1 de Estadísticas: un componente por línea (ver SQL_COMPONENTES_ESTADISTICAS).

        Lo único imprescindible son los nombres de la tabla Componente. Migraciones, componentes POR DEFECTO
        y cálculo de km son extras: si fallan (p. ej. 'database is locked' porque otro programa tiene la BD
        abierta con cambios sin guardar) se registra en el log y la tabla se pinta igualmente."""
        conexion = self.sqliteConnection
        with espera_corta(conexion):     # no congelar la pantalla 5 s por cada escritura bloqueada
            try:
                asegurarColumnasArchivosComponentes(conexion)
            except sqlite3.Error as error:
                logging.warning("No se pudo actualizar archivoscomponentes antes de Estadísticas: %s", error)
            self.calcularKmComponentes(usuario)   # km al día con las actividades y altas actuales
        try:
            columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(archivoscomponentes)")}
            sql = SQL_COMPONENTES_ESTADISTICAS.format(
                meses_limite="u.mesesLimite" if "mesesLimite" in columnas else "NULL")
            filas = conexion.execute(sql, (usuario,)).fetchall()
        except sqlite3.Error as error:
            logging.error("Error al leer los datos de los componentes; se muestran solo los nombres: %s", error)
            vacias = (None,) * (len(COLUMNAS_COMPONENTES) - 1)
            filas = [(nombre, *vacias) for (nombre,) in conexion.execute(
                "SELECT DISTINCT nombre FROM Componente WHERE trim(COALESCE(nombre, '')) <> ''")]
        return sorted(filas, key=lambda fila: orden_alfabetico(fila[0]))

    def ir_a_pantalla_tres(self, widget, valor):
        self._mostrar(self.construir_pantalla_tres(valor))
        self.mostrarAdvertenciaSinDatos(valor, self.anios_sin_datos)

    def construirTablaModalidad(self, filas, anios):
        """Tabla Tiempo y Kms por Modalidad, con el mismo estilo (toga.Table) que las otras dos de la pantalla.

        toga.Table no admite cabeceras agrupadas, así que cada año tiene dos columnas: '2024 KMs' y '2024 Horas'."""
        columnas = [AccessorColumn(t("col.modalidad"), "modalidad"), AccessorColumn(t("col.desde"), "desde")]
        for anio in anios:
            columnas += [AccessorColumn(f"{anio} {t('col.kms')}", f"kms_{anio}"),
                         AccessorColumn(f"{anio} {t('col.horas')}", f"horas_{anio}")]
        datos = [(modalidad, desde or "—", *(texto_numero(valor) for valor in acumulados))
                 for modalidad, desde, *acumulados in filas]
        _h_cabecera, _h_fila = 28, 22
        return toga.Table(columns=columnas, data=datos,
                          style=Pack(height=_h_cabecera + max(len(datos), 1) * _h_fila, flex=1))

    def mostrarAdvertenciaSinDatos(self, usuario, anios_sin_datos):
        """Ventana 'Advertencia !!!' con una línea 'No hay datos del año X' por cada año sin actividades."""
        if not anios_sin_datos:
            return None
        logging.info("Sin datos de Strava (%s) en los años %s", usuario, anios_sin_datos)
        mensaje = "\n".join(t("aviso.sin_datos_anio", anio=anio) for anio in anios_sin_datos)
        self.contenido_advertencia = self.construirVentanaAviso(t("aviso.advertencia"), mensaje)
        self._abrir_ventana_alerta(self.contenido_advertencia, t("aviso.advertencia"))
        return self.contenido_advertencia

    # Marcar componente seleccionado.
    def obtener_componente_seleccionado(self):
        seleccion = getattr(getattr(self, "tabla", None), "selection", None)
        if isinstance(seleccion, list):
            seleccion = seleccion[0] if seleccion else None
        return getattr(seleccion, "elemento", None)

    # Buscar límite según Componente seleccionado.
    def actualizar_limites_componente_seleccionado(self, widget=None):
        if getattr(self, "tablaLimites", None) is None:
            return
        componente = self.obtener_componente_seleccionado()
        self.tablaLimites.data = self.seleccionarLimitesComponente(componente) if componente else []

    def desactivarComponente(self, componente, usuario):
        try:
            self.sqliteConnection.execute(
                "UPDATE archivoscomponentes SET activo = False WHERE usuario = ? AND elemento = ?", (usuario, componente)
            )
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            logging.error("Error al DESACTIVAR el Componente: %s", error)
            return False
        logging.info("UPDATE hecho para DESACTIVAR Componente.")
        return True

    # CREATE TABLE IF NOT EXISTS archivoscomponentes (id INTEGER PRIMARY KEY, usuario NOT NULL, elemento TEXT NOT NULL, descripcion TEXT, marca TEXT, fechaInsercion Date NOT NULL, distanciaLimite integer, tiempoLimite integer, activo BOOLEAN DEFAULT True)
    def anadirComponente(self, valor1, user, valor2, valor3, valor4, valor5=None, valor6=None, valor7=None):
        """valor5/6/7: km, horas y meses límite. Si se dejan vacíos se usan los del componente."""
        logging.info("Dentro añadir Componente.")

        km_defecto, horas_defecto, meses_defecto = limitesComponente(self.sqliteConnection, valor2.value, user)
        distancia = (getattr(valor5, "value", None) or "").strip() or km_defecto
        tiempo = (getattr(valor6, "value", None) or "").strip() or horas_defecto
        meses = (getattr(valor7, "value", None) or "").strip() or meses_defecto
        f = (valor1.value or "").strip() or datetime.today().strftime("%Y-%m-%d")
        asegurarColumnasArchivosComponentes(self.sqliteConnection)

        try:
            # Si el componente existía POR DEFECTO, se le ponen los datos del usuario en vez de duplicarlo
            por_defecto = self.sqliteConnection.execute(
                "SELECT id FROM archivoscomponentes WHERE usuario = ? AND lower(elemento) = lower(?) "
                "AND descripcion = ? ORDER BY id LIMIT 1",
                (user, valor2.value, DESCRIPCION_POR_DEFECTO),
            ).fetchone()
            if por_defecto:
                self.sqliteConnection.execute(
                    "UPDATE archivoscomponentes SET fechaInsercion = ?, elemento = ?, descripcion = ?, marca = ?, "
                    "distanciaLimite = ?, tiempoLimite = ?, mesesLimite = ?, activo = True WHERE id = ?",
                    (f, valor2.value, valor3.value, valor4.value, distancia, tiempo, meses, por_defecto[0])
                )
            else:
                self.sqliteConnection.execute(
                    "INSERT INTO archivoscomponentes (fechaInsercion, usuario, elemento, descripcion, marca, "
                    "distanciaLimite, tiempoLimite, mesesLimite) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (f, user, valor2.value, valor3.value, valor4.value, distancia, tiempo, meses)
                )
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            logging.error("Error al insertar en archivoscomponentes: %s", error)
            self._mostrar_estado(self.label_pantalla_dos, t("estado.componente_error"), ok=False)
            return False
        self._mostrar_estado(self.label_pantalla_dos, t("estado.entrada_ok"))
        logging.info("Componente cargado correctamente.")
        return True

    def cargar_componente(self, entrada_fecha, usuarioSeleccionado, selection_elemento, descripcion_texto, marca_texto, distancialim_texto, tiempolim_texto, meseslim_texto=None) -> bool:
        return self.anadirComponente(entrada_fecha, usuarioSeleccionado, selection_elemento, descripcion_texto, marca_texto, distancialim_texto, tiempolim_texto, meseslim_texto)

    # -------- Pantalla 5 (alta de componente) --------
    def construir_pantalla_cinco(self, valor, elemento=None, volver=None):
        """Alta de componente. `elemento` lo preselecciona; `volver` es la pantalla de retorno."""
        tipos_elemento = self._leer_lista(
            "SELECT nombre FROM Componente ORDER BY nombre",
            por_defecto=ELEMENTOS_POR_DEFECTO,
        )
        if elemento:
            coincidencia = next((e for e in tipos_elemento if e.casefold() == elemento.casefold()), None)
            if coincidencia is None:
                tipos_elemento.insert(0, elemento)
                coincidencia = elemento
            elemento = coincidencia

        self.label_pantalla_dos = toga.Label(
            t("componente.titulo"),
            style=Pack(margin_bottom=10, text_align=CENTER)
        )
        # Línea siguiente al título: "Usuario:" en azul y a continuación el usuario seleccionado
        self.label_usuario_componente = toga.Label(t("componente.usuario"), style=Pack(color=AZUL))
        self.label_usuario_seleccionado = toga.Label(valor or "")
        linea_usuario = toga.Box(
            children=[self.label_usuario_componente, self.label_usuario_seleccionado],
            style=Pack(direction=ROW, margin_bottom=20),
        )
        self.entrada_fecha = self._texto(t("campo.fecha_placeholder"), value=datetime.today().strftime("%Y-%m-%d"))
        self.selection_elemento = toga.Selection(items=tipos_elemento, style=Pack(width=ANCHO_CAMPO))
        if elemento:
            self.selection_elemento.value = elemento
        self.descripcion_texto = self._texto()
        self.marca_texto = self._texto()
        self.distancialim_texto = self._texto()
        self.tiempolim_texto = self._texto()
        self.meseslim_texto = self._texto()
        self.usuario_alta_componente = valor
        # Límites por defecto del componente elegido; se rellenan de nuevo al cambiar de componente
        self.rellenar_limites_por_defecto()
        self.selection_elemento.on_change = self.rellenar_limites_por_defecto

        contenido_box = self._formulario()
        contenido_box.add(self.label_pantalla_dos)
        contenido_box.add(linea_usuario)
        contenido_box.add(self._campo(t("campo.fecha"), self.entrada_fecha))
        contenido_box.add(self._campo(t("campo.elemento"), self.selection_elemento))
        contenido_box.add(self._campo(t("campo.descripcion"), self.descripcion_texto))
        contenido_box.add(self._campo(t("campo.marca"), self.marca_texto))
        contenido_box.add(self._campo(t("campo.distancia_limite"), self.distancialim_texto))
        contenido_box.add(self._campo(t("campo.tiempo_limite"), self.tiempolim_texto))
        contenido_box.add(self._campo(t("campo.meses_limite"), self.meseslim_texto))
        contenido_box.add(self._boton(t("comun.cargar"), lambda widget: self.cargar_componente(
            self.entrada_fecha, self.usuarioSeleccionado, self.selection_elemento, self.descripcion_texto,
            self.marca_texto, self.distancialim_texto, self.tiempolim_texto, self.meseslim_texto,
        )))

        volver = volver or (lambda: self.ir_a_pantalla_tres(None, valor))
        return self._pantalla(contenido_box, self._barra_inferior(izquierda=self._boton_volver(volver)))

    def rellenar_limites_por_defecto(self, widget=None):
        """Pone en los cuadros de km, horas y meses límite los valores por defecto del componente elegido."""
        km, horas, meses = limitesComponente(
            self.sqliteConnection, self.selection_elemento.value, getattr(self, "usuario_alta_componente", None))
        self.distancialim_texto.value = "" if km is None else str(km)
        self.tiempolim_texto.value = "" if horas is None else str(horas)
        self.meseslim_texto.value = "" if meses is None else str(meses)

    def ir_a_pantalla_cinco(self, widget, valor):
        self._mostrar(self.construir_pantalla_cinco(valor))

    # -------- Pantalla Nueva Límite Alerta --------
    def construir_pantalla_nuevoLimiteAlerta(self, item, componentes=None):
        # Tipos ya usados en LimitesAlerta ('superior'/'inferior'), mostrados en el idioma activo
        tipoAlerta = [
            t(TIPOS_LIMITE[tipo]) if tipo in TIPOS_LIMITE else tipo
            for tipo in self._leer_lista(
                "SELECT DISTINCT tipo_limite FROM LimitesAlerta WHERE tipo_limite IS NOT NULL ORDER BY tipo_limite",
                por_defecto=list(TIPOS_LIMITE),
            )
        ]

        componentes_disponibles = list(componentes or [])
        if not componentes_disponibles and self.usuarioSeleccionado is not None:
            componentes_disponibles = self._leer_lista(
                "SELECT elemento FROM archivoscomponentes WHERE usuario = ? ORDER BY elemento",
                (self.usuarioSeleccionado,),
            )
        if item and item not in componentes_disponibles:
            componentes_disponibles.insert(0, item)

        self.tituloPantallaAlerta = t("alerta.titulo") + self.label_estado
        self.label_pantalla_LimiteNuevaAlerta = toga.Label(
            self.tituloPantallaAlerta,
            style=Pack(margin_bottom=20, text_align=CENTER)
        )
        self.tipo_limite = toga.Selection(items=tipoAlerta, style=Pack(width=ANCHO_CAMPO))
        self.valor_limite = self._texto(t("alerta.valor_placeholder"))
        self.componente_dropdown = toga.Selection(items=componentes_disponibles, style=Pack(width=ANCHO_CAMPO))
        if item in componentes_disponibles:
            self.componente_dropdown.value = item

        contenido_box = self._formulario()
        contenido_box.add(self.label_pantalla_LimiteNuevaAlerta)
        contenido_box.add(self._campo(t("alerta.tipo"), self.tipo_limite))
        contenido_box.add(self._campo(t("alerta.valor"), self.valor_limite))
        contenido_box.add(self._campo(t("alerta.componente"), self.componente_dropdown))
        contenido_box.add(self._boton(t("comun.anadir"), self.cargar_limiteAlerta))

        volver = self._boton_volver(lambda: self.ir_a_pantalla_tres(None, self.usuarioSeleccionado))
        return self._pantalla(contenido_box, self._barra_inferior(izquierda=volver))

    def PantallaNuevaAlerta(self, item, componentes=None):
        self._mostrar(self.construir_pantalla_nuevoLimiteAlerta(item, componentes))

    def seleccionarLimitesComponente(self, comp):
        try:
            return self.sqliteConnection.execute(
                "SELECT componente, tipo_limite, valor FROM LimitesAlerta WHERE componente = ?",
                (comp,),
            ).fetchall()
        except sqlite3.Error as error:
            logging.error("Error al leer límites del Componente %s: %s", comp, error)
            return []

    def cargar_limiteAlerta(self, widget=None):
        ok = False
        if not getattr(self.tipo_limite, "value", None):
            logging.warning("Falta el TIPO DE ALERTA")
        else:
            # El desplegable muestra el texto traducido; en la BD se guarda 'superior' o 'inferior'
            superiores = {'superior', t(TIPOS_LIMITE['superior']), translations.default_text(TIPOS_LIMITE['superior'])}
            tipo_alerta = 'superior' if self.tipo_limite.value in superiores else 'inferior'
            valor_limite = (self.valor_limite.value or "").strip()
            compo = (self.componente_dropdown.value or "").strip()
            try:
                self.sqliteConnection.execute("""
                    INSERT INTO LimitesAlerta (tipo_limite, valor, componente)
                    VALUES (?, ?, ?) ON CONFLICT(tipo_limite, componente) DO NOTHING
                """, (tipo_alerta, valor_limite, compo))
                self.sqliteConnection.commit()
                ok = True
            except sqlite3.Error as error:
                logging.error("Error al guardar Límite Alerta: %s", error)

        self.label_estado = "✅" if ok else "❌"
        self.label_pantalla_LimiteNuevaAlerta.text += self.label_estado
        return ok

    def crearTablaActividadesStrava(self) -> bool:
        try:
            stravaConnect.asegurarTablaActividades(self.sqliteConnection)
            return True
        except sqlite3.Error as error:
            logging.error("Error al crear la tabla ActividadesStrava: %s", error)
            return False

    def limpiarDuplicadosStrava(self) -> bool:
        try:
            stravaConnect.asegurarStravaValoresSinDuplicados(self.sqliteConnection)
            return True
        except sqlite3.Error as error:
            self.sqliteConnection.rollback()
            logging.error("Error al quitar duplicados de stravaValores: %s", error)
            return False

    def vehiculoDelUsuario(self, usuario):
        """Vehículo del usuario (EntradasUsers.tipov guarda el nombre o el id de tipo_vehiculo)."""
        return vehiculoDeUsuario(self.sqliteConnection, usuario)

    def crearTablaAlertThresholds(self) -> bool:
        try:
            self.sqliteConnection.execute("""CREATE TABLE IF NOT EXISTS LimitesAlerta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            componente TEXT,
            tipo_limite TEXT,
            valor INTEGER,
            usuario TEXT REFERENCES EntradasUsers(usuario),
            vehiculo TEXT NOT NULL DEFAULT '',
            UNIQUE(tipo_limite, componente)
            )""")
            self.sqliteConnection.commit()
            return True
        except sqlite3.Error as error:
            logging.error("Error en el CREAR la TABLA LimitesAlerta: %s", error)
            return False

    # -------- Pantalla de sincronización con Strava --------
    def _sincronizar_strava(self, fecha_desde, usuario, vehiculo, progreso=None, conexion_propia=False):
        """Descarga las actividades desde fecha_desde y las guarda. Devuelve cuántas se guardaron.

        progreso(fase, actual, total): fase "descargando" (total desconocido) o "guardando".
        Se ejecuta en un hilo aparte (conexion_propia=True) para no congelar la ventana."""
        avisar = progreso or (lambda *a: None)
        datos = stravaConnect.StravaData(self, conexion_propia=conexion_propia)
        try:
            datos.initConexion()
            datos.crearObjetoCliente()
            hasta = datetime.now()
            datos.extraerDatos(datetime.combine(fecha_desde, time.min), hasta,
                               progreso=lambda n: avisar("descargando", n, None))
            datos.guardarDatosBDD(hasta)
            guardadas = datos.guardarActividadesBDD(usuario, vehiculo,
                                                    progreso=lambda i, n: avisar("guardando", i, n))
            if datos.actividades and guardadas == 0:
                raise RuntimeError("No se pudieron guardar las actividades en la base de datos")
            datos.quitarActividadesDuplicadas()   # tras la carga: mismo StravaID y usuario -> se queda el id menor
            try:
                calcularKmComponentes(datos.sqliteConnection, usuario)
            except sqlite3.Error as error:   # los km se recalculan también al abrir Estadísticas
                logging.error("Error al calcular los km de los componentes tras Strava Sync: %s", error)
            return guardadas
        finally:
            datos.cerrar()

    def _progreso_strava(self, fase, actual, total=None):
        if fase == "descargando":
            # Strava no dice cuántas actividades hay: barra en movimiento + contador
            if self.progress.max is not None:
                self.progress.max = None
                self.progress.start()
            self.label.text = t("strava.descargando", actual=actual)
        else:
            self.progress.stop()
            self.progress.max = max(total or 0, 1)
            self.progress.value = actual
            self.label.text = t("strava.guardando", actual=actual, total=total)

    def _fin_sync_strava(self, texto, completa):
        self.progress.stop()
        self.progress.max = 1
        self.progress.value = 1 if completa else 0
        self.label.text = texto
        self.lanzarNotificacion(t("notificacion.strava_titulo"), texto)

    async def recolectarDatosStrava(self, widget=None):
        if self.sync_strava_en_curso:
            return
        self.sync_strava_en_curso = True
        self.boton_extraer.enabled = False
        self.fecha_desde.enabled = False
        usuario = self.usuarioSeleccionado
        vehiculo = self.vehiculoDelUsuario(usuario)
        fecha = self.fecha_desde.value or FECHA_INICIO_STRAVA
        loop = asyncio.get_running_loop()

        def progreso(fase, actual, total):   # llamado desde el hilo de descarga
            loop.call_soon_threadsafe(self._progreso_strava, fase, actual, total)

        self._progreso_strava("descargando", 0)
        try:
            total = await loop.run_in_executor(
                None, self._sincronizar_strava, fecha, usuario, vehiculo, progreso, True)
        except Exception as error:   # red, tokens, BD...: se avisa al usuario en vez de fallar en silencio
            logging.exception("Error en Strava Sync")
            await asyncio.sleep(0)   # que se apliquen antes los avisos de progreso pendientes
            self._fin_sync_strava(t("strava.error", error=error), completa=False)
        else:
            await asyncio.sleep(0)
            self._fin_sync_strava(t("strava.fin", total=total), completa=True)
        finally:
            self.boton_extraer.enabled = True
            self.fecha_desde.enabled = True
            self.sync_strava_en_curso = False

    def ir_a_pantalla_recoleccionDatos(self, widget=None):
        self._mostrar(self.barraProgresoCargaDatos())

    def barraProgresoCargaDatos(self):
        self.label = toga.Label(t("strava.pulsa_extraer"), style=Pack(margin=10))
        self.fecha_desde = toga.DateInput(value=FECHA_INICIO_STRAVA, max=date.today(), style=Pack(margin=10))
        self.progress = toga.ProgressBar(max=1, value=0, style=Pack(margin=10))
        self.boton_extraer = self._boton(t("strava.extraer"), self.recolectarDatosStrava)

        fila_fecha = toga.Box(style=Pack(direction=ROW, align_items=CENTER))
        fila_fecha.add(toga.Label(t("strava.desde"), style=Pack(margin=10)))
        fila_fecha.add(self.fecha_desde)

        box = toga.Box(style=Pack(direction=COLUMN, margin=20))
        box.add(fila_fecha)
        box.add(self.label)
        box.add(self.progress)
        box.add(self.boton_extraer)
        box.add(self._barra_inferior(izquierda=self._boton_volver(self.ir_a_menu_usuario)))
        return box

def main():
    # Nombre visible y ID de la app (ajústalo a tu dominio)
    return BikeCompFollowApp("Bike Comp Follow App", "com.SkullWithGasMask", icon="resources/icon.png")

if __name__ == "__main__":
    app = main()
    app.main_loop()
