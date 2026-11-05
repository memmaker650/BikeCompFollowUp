"""
Operaciones con la base de datos de BikeCompFollowApp.

Aquí está todo lo que lee o escribe en SQLite y los cálculos con las actividades de Strava ya guardadas,
para que app.py se quede con las pantallas y la gestión de la aplicación:

- Funciones de módulo con una conexión como primer parámetro: creación y migración de tablas, límites por
  defecto de los componentes, km/horas por componente (datosComponente) y km/horas por modalidad.
- La clase BaseDatos, que envuelve una conexión y agrupa las lecturas y escrituras que usan las pantallas.

La descarga de Strava (API, tokens) sigue en stravaConnect.py.
"""

import logging
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import date

if __package__:
    from . import stravaConnect
else:
    import stravaConnect


# ---- Valores por defecto y configuración de datos ----
DISTANCIA_LIMITE_DEFECTO = 5000
TIEMPO_LIMITE_DEFECTO = 500
FECHA_ALTA_POR_DEFECTO = date(2026, 1, 1)    # fecha de alta de los componentes POR DEFECTO

# Espera ante una BD bloqueada por otro programa: la de sqlite3 por defecto y la corta de Estadísticas
ESPERA_BD_MS = 5000
ESPERA_CORTA_BD_MS = 500

# Tabla "Tiempo y Kms por Modalidad": filas y nº de años (el actual y los anteriores)
MODALIDADES_ESTADISTICAS = ("Road", "MTB", "Gravel")
ANIOS_ESTADISTICAS = 3

# Columnas que devuelve BaseDatos.componentesEstadisticas (las de la tabla 1 de Estadísticas)
NUM_COLUMNAS_ESTADISTICAS = 10


# ---- Límites por defecto de los componentes ----
# Límites por defecto de cada componente: (palabras que debe contener el nombre, sin acentos ni mayúsculas)
# -> (km, horas, meses). El primero que coincide gana; si ninguno coincide, LIMITES_GENERICOS.
LIMITES_GENERICOS = (DISTANCIA_LIMITE_DEFECTO, TIEMPO_LIMITE_DEFECTO, None)
LIMITES_POR_COMPONENTE = [
    (("liquido", "freno"), (None, None, 12)),     # líquido de frenos: 1 año
    (("purgado", "freno"), (None, None, 12)),     # purgado de frenos = cambio de líquido
    (("cubierta",), (4000, TIEMPO_LIMITE_DEFECTO, None)),
    (("cadena",), (2000, TIEMPO_LIMITE_DEFECTO, None)),
    (("pastilla",), (4000, TIEMPO_LIMITE_DEFECTO, None)),   # frenos
]


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


# ---- Acceso a la base de datos desde la aplicación ----
class BaseDatos:
    """Lecturas y escrituras de la aplicación sobre una conexión SQLite.

    Los métodos de lectura devuelven listas vacías (o el valor por defecto) si hay un error de SQLite y los
    de escritura devuelven True/False; en ambos casos el error queda en el log. Así las pantallas solo deciden
    qué mostrar."""

    def __init__(self, conexion):
        self.conexion = conexion
        self.cursor = conexion.cursor()

    @classmethod
    def abrir(cls, ruta):
        """Abre (o crea) la BD de `ruta`, migra las tablas antiguas y siembra una BD nueva."""
        bd = cls(sqlite3.connect(ruta))
        print("DB DIR:", ruta)
        bd.arrancar()
        return bd

    # -------- Creación y migración de tablas --------
    def arrancar(self):
        """Renombra tablas antiguas; en una BD nueva crea las tablas básicas y siembra los datos iniciales."""
        self.renombrarTablasAntiguas()
        self.conexion.commit()
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
                self.conexion.commit()
                logging.info("Tabla tipo_vehiculo creada y rellenada con valores por defecto.")
        except sqlite3.Error as error:
            logging.error("Error al crear/rellenar tabla tipo_vehiculo en SQLite %s", error)

        logging.info('Fin acciones Base de Datos')

    def prepararTablas(self):
        """Tablas y migraciones que se comprueban en cada arranque (además de las de arrancar)."""
        self.crearTablaAlertThresholds()
        self.crearTablaAjustes()
        self.crearTablaActividadesStrava()
        self.crearTablaDatosComponente()
        self.limpiarDuplicadosStrava()

    def crearDBBasica(self):
        try:
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS Componente (id INTEGER PRIMARY KEY,nombre TEXT)""")
            asegurarTablaDatosComponente(self.conexion)
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
            self.conexion.commit()

        # Carga de los datos básicos
        try:
            self.cursor.executemany("INSERT INTO tipo_vehiculo (vehiculo) VALUES (?)", [(v,) for v in VEHICULOS_INICIALES])
            self.cursor.executemany("INSERT INTO Componente (nombre) VALUES (?)", [(e,) for e in ELEMENTOS_INICIALES])
            self.conexion.commit()
            asegurarColumnasComponente(self.conexion)
            logging.info('Carga de datos básicos (tipo_vehiculo, Componente) correcta.')
        except sqlite3.Error as error:
            logging.error("Error al cargar datos de las Tablas Básicas en SQLite: %s", error)

    def renombrarTablasAntiguas(self) -> bool:
        """Renombra datos -> datosComponente y Elemento -> Componente en una BD existente, sin perder filas.

        SQLite actualiza solo las FOREIGN KEY de otras tablas (linked_elements) que apuntaban al nombre antiguo.
        """
        try:
            # En SQLite los nombres de tabla no distinguen mayúsculas
            existentes = {fila[0].casefold() for fila in self.conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for antigua, nueva in TABLAS_RENOMBRADAS.items():
                if antigua.casefold() not in existentes:
                    continue
                if nueva.casefold() in existentes:
                    if self.conexion.execute(f'SELECT COUNT(*) FROM "{nueva}"').fetchone()[0]:
                        logging.warning("Existen %s y %s con datos: no se renombra %s", antigua, nueva, antigua)
                        continue
                    self.conexion.execute(f'DROP TABLE "{nueva}"')   # la nueva estaba vacía
                self.conexion.execute(f'ALTER TABLE "{antigua}" RENAME TO "{nueva}"')
                logging.info("Tabla %s renombrada a %s", antigua, nueva)
            self.conexion.commit()
        except sqlite3.Error as error:
            self.conexion.rollback()
            logging.error("Error al renombrar tablas antiguas: %s", error)
            return False
        return True

    def crearTablaAlertThresholds(self) -> bool:
        try:
            self.conexion.execute("""CREATE TABLE IF NOT EXISTS LimitesAlerta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            componente TEXT,
            tipo_limite TEXT,
            valor INTEGER,
            usuario TEXT REFERENCES EntradasUsers(usuario),
            vehiculo TEXT NOT NULL DEFAULT '',
            UNIQUE(tipo_limite, componente)
            )""")
            self.conexion.commit()
            return True
        except sqlite3.Error as error:
            logging.error("Error en el CREAR la TABLA LimitesAlerta: %s", error)
            return False

    def crearTablaActividadesStrava(self) -> bool:
        try:
            stravaConnect.asegurarTablaActividades(self.conexion)
            return True
        except sqlite3.Error as error:
            logging.error("Error al crear la tabla ActividadesStrava: %s", error)
            return False

    def limpiarDuplicadosStrava(self) -> bool:
        try:
            stravaConnect.asegurarStravaValoresSinDuplicados(self.conexion)
            return True
        except sqlite3.Error as error:
            self.conexion.rollback()
            logging.error("Error al quitar duplicados de stravaValores: %s", error)
            return False

    def crearTablaDatosComponente(self) -> bool:
        try:
            asegurarColumnasArchivosComponentes(self.conexion)
            asegurarColumnasComponente(self.conexion)
            asegurarTablaDatosComponente(self.conexion)
        except sqlite3.Error as error:
            logging.error("Error al crear la tabla datosComponente: %s", error)
            return False
        return True

    def chequearIntegrarDB(self):
        self.cursor.execute("PRAGMA integrity_check;")
        result = self.cursor.fetchone()

        if result[0] == "ok":
            print("✅ DB íntegra")
        else:
            print("❌ DB corrupta")

    def cerrarDB(self):
        self.conexion.close()
        logging.info("The SQLite connection is closed")

    # -------- Ajustes (clave/valor) --------
    def crearTablaAjustes(self) -> bool:
        try:
            self.conexion.execute("CREATE TABLE IF NOT EXISTS ajustes (clave TEXT PRIMARY KEY, valor TEXT)")
            self.conexion.commit()
            return True
        except sqlite3.Error as error:
            logging.error("Error al crear la tabla ajustes: %s", error)
            return False

    def leerAjuste(self, clave, por_defecto=None):
        try:
            fila = self.conexion.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
        except sqlite3.Error as error:
            logging.error("Error al leer el ajuste %s: %s", clave, error)
            return por_defecto
        return fila[0] if fila else por_defecto

    def guardarAjuste(self, clave, valor) -> bool:
        try:
            self.conexion.execute(
                "INSERT INTO ajustes (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (clave, valor),
            )
            self.conexion.commit()
            return True
        except sqlite3.Error as error:
            logging.error("Error al guardar el ajuste %s: %s", clave, error)
            return False

    # -------- Listas para desplegables y botones --------
    def leerLista(self, sql, params=(), por_defecto=()):
        """Devuelve la primera columna de una SELECT, o `por_defecto` si falla o está vacía."""
        try:
            valores = [fila[0] for fila in self.conexion.execute(sql, params)]
        except sqlite3.Error as error:
            logging.error("Error en la consulta '%s': %s", sql, error)
            valores = []
        return valores or list(por_defecto)

    def usuarios(self):
        """[(nombre, usuario)] de EntradasUsers, para los botones de la pantalla inicial."""
        try:
            return self.conexion.execute("SELECT nombre, usuario FROM EntradasUsers").fetchall()
        except sqlite3.Error as error:
            logging.error("Error al leer la tabla EntradasUsers: %s", error)
            return []

    def tiposVehiculo(self, por_defecto=()):
        return self.leerLista("SELECT vehiculo FROM tipo_vehiculo ORDER BY vehiculo", por_defecto=por_defecto)

    def nombresComponentes(self, por_defecto=()):
        return self.leerLista("SELECT nombre FROM Componente ORDER BY nombre", por_defecto=por_defecto)

    def tiposLimiteUsados(self, por_defecto=()):
        """Tipos ya usados en LimitesAlerta ('superior'/'inferior')."""
        return self.leerLista(
            "SELECT DISTINCT tipo_limite FROM LimitesAlerta WHERE tipo_limite IS NOT NULL ORDER BY tipo_limite",
            por_defecto=por_defecto)

    def elementosDeUsuario(self, usuario):
        return self.leerLista("SELECT elemento FROM archivoscomponentes WHERE usuario = ? ORDER BY elemento", (usuario,))

    def vehiculoDelUsuario(self, usuario):
        """Vehículo del usuario (EntradasUsers.tipov guarda el nombre o el id de tipo_vehiculo)."""
        return vehiculoDeUsuario(self.conexion, usuario)

    # -------- Usuarios --------
    def insertarEntrada(self, fecha, nombre, usuario, tipov, descripcion) -> bool:
        try:
            self.conexion.execute(
                "INSERT INTO EntradasUsers (fecha, nombre, usuario, tipov, descripcion) VALUES (?, ?, ?, ?, ?)",
                (fecha, nombre, usuario, tipov, descripcion)
            )
            self.conexion.commit()
        except sqlite3.Error as error:
            logging.error("Error al insertar en EntradasUsers: %s", error)
            return False
        logging.info("Datos de Entrada cargados correctamente.")
        return True

    # -------- Componentes del usuario --------
    def limitesComponente(self, componente, usuario=None):
        """(km, horas, meses) por defecto del componente para la bici del usuario."""
        return limitesComponente(self.conexion, componente, usuario)

    def guardarComponente(self, fecha, usuario, elemento, descripcion, marca, distancia, tiempo, meses) -> bool:
        """Alta de componente. Si existía POR DEFECTO se le ponen estos datos en vez de duplicarlo."""
        try:
            asegurarColumnasArchivosComponentes(self.conexion)
            por_defecto = self.conexion.execute(
                "SELECT id FROM archivoscomponentes WHERE usuario = ? AND lower(elemento) = lower(?) "
                "AND descripcion = ? ORDER BY id LIMIT 1",
                (usuario, elemento, DESCRIPCION_POR_DEFECTO),
            ).fetchone()
            if por_defecto:
                self.conexion.execute(
                    "UPDATE archivoscomponentes SET fechaInsercion = ?, elemento = ?, descripcion = ?, marca = ?, "
                    "distanciaLimite = ?, tiempoLimite = ?, mesesLimite = ?, activo = True WHERE id = ?",
                    (fecha, elemento, descripcion, marca, distancia, tiempo, meses, por_defecto[0])
                )
            else:
                self.conexion.execute(
                    "INSERT INTO archivoscomponentes (fechaInsercion, usuario, elemento, descripcion, marca, "
                    "distanciaLimite, tiempoLimite, mesesLimite) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (fecha, usuario, elemento, descripcion, marca, distancia, tiempo, meses)
                )
            self.conexion.commit()
        except sqlite3.Error as error:
            logging.error("Error al insertar en archivoscomponentes: %s", error)
            return False
        logging.info("Componente cargado correctamente.")
        return True

    def desactivarComponente(self, componente, usuario):
        try:
            self.conexion.execute(
                "UPDATE archivoscomponentes SET activo = False WHERE usuario = ? AND elemento = ?", (usuario, componente)
            )
            self.conexion.commit()
        except sqlite3.Error as error:
            logging.error("Error al DESACTIVAR el Componente: %s", error)
            return False
        logging.info("UPDATE hecho para DESACTIVAR Componente.")
        return True

    # -------- Límites de alerta --------
    def seleccionarLimitesComponente(self, comp):
        try:
            return self.conexion.execute(
                "SELECT componente, tipo_limite, valor FROM LimitesAlerta WHERE componente = ?",
                (comp,),
            ).fetchall()
        except sqlite3.Error as error:
            logging.error("Error al leer límites del Componente %s: %s", comp, error)
            return []

    def insertarLimiteAlerta(self, tipo_limite, valor, componente) -> bool:
        """tipo_limite: 'superior' o 'inferior'. Si ya existe ese tipo para el componente no se toca."""
        try:
            self.conexion.execute("""
                INSERT INTO LimitesAlerta (tipo_limite, valor, componente)
                VALUES (?, ?, ?) ON CONFLICT(tipo_limite, componente) DO NOTHING
            """, (tipo_limite, valor, componente))
            self.conexion.commit()
        except sqlite3.Error as error:
            logging.error("Error al guardar Límite Alerta: %s", error)
            return False
        return True

    # -------- Estadísticas y cálculos con las actividades de Strava --------
    def calcularKmComponentes(self, usuario=None) -> int:
        """Recalcula los km de cada componente (ver calcularKmComponentes). -1 si hay error."""
        try:
            return calcularKmComponentes(self.conexion, usuario)
        except sqlite3.Error as error:
            logging.error("Error al calcular los km de los componentes: %s", error)
            return -1

    def componentesEstadisticas(self, usuario):
        """Filas de la tabla 1 de Estadísticas: un componente por línea (ver SQL_COMPONENTES_ESTADISTICAS).

        Lo único imprescindible son los nombres de la tabla Componente. Migraciones, componentes POR DEFECTO
        y cálculo de km son extras: si fallan (p. ej. 'database is locked' porque otro programa tiene la BD
        abierta con cambios sin guardar) se registra en el log y la tabla se pinta igualmente."""
        conexion = self.conexion
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
            vacias = (None,) * (NUM_COLUMNAS_ESTADISTICAS - 1)
            filas = [(nombre, *vacias) for (nombre,) in conexion.execute(
                "SELECT DISTINCT nombre FROM Componente WHERE trim(COALESCE(nombre, '')) <> ''")]
        return sorted(filas, key=lambda fila: orden_alfabetico(fila[0]))

    def kmsHorasPorModalidad(self, usuario, anios):
        """(filas, anios_sin_datos) de la tabla Tiempo y Kms por Modalidad (ver kmsHorasPorModalidad)."""
        return kmsHorasPorModalidad(self.conexion, usuario, anios)
