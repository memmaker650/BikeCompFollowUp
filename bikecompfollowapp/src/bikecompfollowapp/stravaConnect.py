# You will use this to log in to your Strava account
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import json
import sys
import math

from datetime import datetime
from dateutil.relativedelta import relativedelta

import sqlite3
from pathlib import Path
import logging
import threading
import requests
import time

from stravalib.client import Client

class OAuthHandler(BaseHTTPRequestHandler):

    code = None
    server_instance = None

    def do_GET(self):

        query = parse_qs(urlparse(self.path).query)

        if "code" in query:
            OAuthHandler.code = query["code"][0]

            print("Code :", OAuthHandler.code)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorization successful. You can close this window.")

            # avisar al programa principal
            OAuthHandler.event.set()

        else:
            self.send_response(400)
            self.end_headers()

# Una fila por actividad de Strava. id = identificador interno de la tabla; StravaID = id de la
# actividad en Strava (único: al sincronizar otra vez se actualiza la fila en vez de duplicarla).
# Unidades: distancia km, altimetria m, duracion horas (tiempo en movimiento), velocidad_media km/h.
SQL_CREAR_ACTIVIDADES = """CREATE TABLE IF NOT EXISTS ActividadesStrava (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    StravaID INTEGER NOT NULL UNIQUE,
    tipo TEXT,
    distancia FLOAT,
    altimetria FLOAT,
    duracion FLOAT,
    velocidad_media FLOAT,
    tipo_vehiculo TEXT,
    elemento TEXT,
    user TEXT
)"""


COLUMNAS_DATOS_ACTIVIDADES = "tipo, distancia, altimetria, duracion, velocidad_media, tipo_vehiculo, elemento, user"


def asegurarTablaActividades(conexion) -> None:
    """Crea ActividadesStrava o, si es de la versión anterior (sin StravaID, con el id de Strava
    como clave), la migra: el id antiguo pasa a StravaID y id se renumera como id interno."""
    columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(ActividadesStrava)")}
    if columnas and "StravaID" not in columnas:
        logging.info("Migrando ActividadesStrava: se añade la columna StravaID")
        try:
            conexion.execute("ALTER TABLE ActividadesStrava RENAME TO ActividadesStrava_antigua")
            conexion.execute(SQL_CREAR_ACTIVIDADES)
            conexion.execute(f"""INSERT INTO ActividadesStrava (StravaID, {COLUMNAS_DATOS_ACTIVIDADES})
                                 SELECT id, {COLUMNAS_DATOS_ACTIVIDADES} FROM ActividadesStrava_antigua ORDER BY id""")
            conexion.execute("DROP TABLE ActividadesStrava_antigua")
        except sqlite3.Error:
            conexion.rollback()
            raise
    else:
        conexion.execute(SQL_CREAR_ACTIVIDADES)
    conexion.commit()


def quitarActividadesDuplicadas(conexion) -> int:
    """Borra de ActividadesStrava las filas con el mismo StravaID y el mismo usuario, dejando
    solo la de id menor. Devuelve cuántas filas se han borrado."""
    cursor = conexion.execute("""DELETE FROM ActividadesStrava WHERE id NOT IN (
                                     SELECT MIN(id) FROM ActividadesStrava GROUP BY StravaID, user)""")
    conexion.commit()
    borradas = cursor.rowcount
    if borradas:
        logging.warning("Borradas %d actividades duplicadas de ActividadesStrava", borradas)
    else:
        logging.info("ActividadesStrava sin actividades duplicadas")
    return borradas


# Actividades sin bici ni otro vehículo: se guardan con tipo_vehiculo = NULL
TIPOS_SIN_VEHICULO = {"run", "walk"}


def _dia(fecha) -> str:
    """datetime/date/'2026-11-04 12:46:32' -> '2026-11-04' (stravaValores guarda una fila por día)."""
    if isinstance(fecha, datetime):
        return fecha.date().isoformat()
    if hasattr(fecha, "isoformat"):
        return fecha.isoformat()
    return str(fecha)[:10]


def asegurarStravaValoresSinDuplicados(conexion) -> None:
    """Deja stravaValores con una sola fila por (día, tipo) y lo garantiza con un índice único.

    Antes cada sincronización añadía una fila nueva con fecha y hora, y varias sincronizaciones
    el mismo día duplicaban el resumen. Se conserva la fila más reciente de cada día (la de id
    mayor). Es idempotente: se puede llamar en cada arranque.
    """
    conexion.execute("""DELETE FROM stravaValores WHERE id NOT IN (
                            SELECT MAX(id) FROM stravaValores GROUP BY date(fecha), tipo)""")
    conexion.execute("UPDATE stravaValores SET fecha = date(fecha) WHERE fecha <> date(fecha)")
    conexion.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_stravaValores_fecha_tipo ON stravaValores (fecha, tipo)")
    conexion.commit()


def _texto(valor):
    """RelaxedActivityType('Ride') -> 'Ride'; None se mantiene."""
    if valor is None:
        return None
    return str(getattr(valor, "root", valor))


def _numero(valor, factor=1.0, decimales=2):
    return None if valor is None else round(float(valor) * factor, decimales)


class StravaData:
    contador = 0
    contador2 = 0
    client_id = ""
    client_secret = "" 
    code = ""
    client = None
    total_distancia = 0 
    total_distancia2 = 0
    total_desnivel = 0 
    total_desnivel2 = 0
    total_tiempo = 0 
    total_tiempo2 = 0
    total_actividades = 0
    fecha_referencia = datetime 
    fecha_objetivo = datetime

    sqliteConnection = 0
    cursor = 0

    # Constructor: inicializa atributos (características)
    def __init__(self, app, conexion_propia=False):
        """conexion_propia=True abre una conexión nueva a la BD de la app. Es obligatorio cuando
        StravaData se usa en un hilo distinto al de la interfaz (sqlite3 no permite compartir una
        conexión entre hilos)."""
        self.app = app
        self.contador = 0
        self.contador2 = 0
        self.actividades = []
        self._equipos = {}   # gear_id -> nombre, para no consultar Strava en cada actividad

        # Misma BD que la app (BikeCFU/dbbcfu.db). Antes se abría paths.data/dbbcfu.db, otro
        # fichero distinto: SQLite lo creaba vacío y fallaba con "no such table: stravaValores".
        # Si la app ya tiene la BD abierta se reutiliza su conexión: con una segunda conexión al
        # mismo fichero, cualquier cambio sin confirmar de la app provoca "database is locked".
        conexion = getattr(app, "sqliteConnection", None)
        self._conexion_propia = conexion_propia or not isinstance(conexion, sqlite3.Connection)
        if not self._conexion_propia:
            self.sqliteConnection = conexion
        else:
            file_pathDB = getattr(app, "db_path", None) or Path(app.paths.data) / "BikeCFU" / "dbbcfu.db"
            Path(file_pathDB).parent.mkdir(parents=True, exist_ok=True)
            self.sqliteConnection = sqlite3.connect(file_pathDB, timeout=15)
            logging.info("Successfully Connected to SQLite: %s", file_pathDB)
        self.cursor = self.sqliteConnection.cursor()

    def cerrar(self) -> None:
        """Cierra la conexión solo si la abrió StravaData (la de la app la cierra la app)."""
        if self._conexion_propia:
            self.sqliteConnection.close()

    # Open the secrets file and store the client ID and client secret as objects, separated by a comma
    # Read below to learn how to set up the app that provides you with the client ID
    # and the client secret
    def initConexion(self):   
        file_path = self.app.paths.data / "client_secrets.txt" 
        print("Ruta dentro StravaData: ", file_path)
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                lineas = f.readlines()

                # Primera y segunda línea
                linea1 = lineas[0].strip()
                linea2 = lineas[1].strip()
                linea5 = lineas[4].strip()

                # Tomar el texto que hay después de los dos puntos
                # (split en el primer ':' y nos quedamos con la parte derecha)
                valor1 = linea1.split(":", 1)[1].strip()
                valor2 = linea2.split(":", 1)[1].strip()
                valor5 = linea5.split(":", 1)[1].strip()

                print("Valor 1:", valor1)
                print("Valor 2:", valor2)
                print("Valor 5:", valor5)

                self.client_id = valor1
                self.client_secret = valor2
                self.code = valor5
        else:
            print("El fichero no existe, hago otra cosa")
            # Aquí tu lógica alternativa

    def get_strava_code(self, client_id):

        event = threading.Event()
        OAuthHandler.event = event

        server = HTTPServer(("127.0.0.1", 5000), OAuthHandler)

        # servidor en thread
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()

        print("Servidor OAuth escuchando en puerto 5000")

        # URL de autorización Strava
        auth_url = (
            f"https://www.strava.com/oauth/authorize"
            f"?client_id={client_id}"
            f"&response_type=code"
            f"&redirect_uri=http://127.0.0.1:5000"
            f"&scope=activity:read"
        )

        # abrir navegador
        webbrowser.open(auth_url)

        print("Esperando autorización del usuario...")

        # esperar a que llegue el code
        event.wait()

        server.shutdown()
        thread.join()

        return OAuthHandler.code


    def crearObjetoCliente(self):
        #   Create a client object
        self.client = Client()
        # Define your scope (this is read-only - see below for a "write" example which
        # allows you to update activities and publish new activities to your Strava account).
        # read_all allows read access for both private and public activities
        request_scope = ["read_all", "profile:read_all", "activity:read_all"]

        # Create a localhost URL for authorization (for local development)
        redirect_url = "http://127.0.0.1:5000/authorization"

        # Create authorization url; your app client_id required to authorize
        url = self.client.authorization_url(
            client_id=self.client_id,
            redirect_uri=redirect_url,
            scope=request_scope,)  

        tokens = self.load_tokens()
        if tokens is None:
            # Sin strava_tokens.json: se intenta recuperar la sesión con el refresh_token de la BD
            tokens = self.tokens_desde_bdd()

        if tokens is not None:
            access_token = self.get_valid_token()
        else:
            print("No hay tokens guardados. Necesario OAuth.")
            CLIENT_ID = self.client_id

            code = self.get_strava_code(CLIENT_ID)
            print("Code final recibido:", code)   
            tokens = self.get_tokens(self.client_id, self.client_secret, code)
            if not self.save_tokens(tokens):
                raise RuntimeError("Strava no devolvió un token válido tras la autorización")
            print("Token saved - hooray!")
            access_token = tokens["access_token"]
            print("Access Token --> ", access_token)
        
        
        # Access and refresh tokens

        # Example output of token_response
        # {'access_token': 'value-here-123123123', 'refresh_token': # '123123123',
        # 'expires_at': 1673665980}
        self.client = Client(access_token=access_token)
        # Get current athlete details
        athlete = self.client.get_athlete()
        # Print athlete name :) If this works, your connection is successful!
        print(f"Hi, {athlete.firstname} Welcome to stravalib!")

        # You are now successfully authenticated!

    def get_tokens(self, client_id, client_secret, code):
        url = "https://www.strava.com/oauth/token"

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code"
        }

        r = requests.post(url, data=payload)
        tokens = r.json()

        return tokens

    @staticmethod
    def tokens_validos(tokens) -> bool:
        return isinstance(tokens, dict) and bool(tokens.get("access_token")) and bool(tokens.get("refresh_token"))

    def save_tokens(self, tokens) -> bool:
        """Guarda los tokens en strava_tokens.json y el refresh_token en la BD (tabla token).

        Se llama tras la autorización inicial y cada vez que se refresca el token. Si Strava
        devolvió un error en vez de tokens, no se sobrescribe nada y devuelve False.
        """
        if not self.tokens_validos(tokens):
            logging.error("Respuesta de Strava sin tokens válidos; no se guarda: %s",
                          {k: v for k, v in (tokens or {}).items() if "token" not in k})
            return False
        file_path = self.app.paths.data / "strava_tokens.json"
        with open(file_path, "w") as f:
            json.dump(tokens, f)
            f.flush()
        if not self.guardarTokenBDD(tokens["refresh_token"]):
            logging.error("No se pudo guardar el refresh_token de Strava en la BD")
        return True

    def tokens_desde_bdd(self):
        """Recupera la sesión con el refresh_token guardado en la BD. Devuelve los tokens o None."""
        refresh = self.recuperarTokenBDD()
        if refresh == "Error":
            return None
        logging.info("strava_tokens.json no disponible; se refresca con el token de la BD")
        tokens = self.refresh_token(self.client_id, self.client_secret, refresh)
        return tokens if self.save_tokens(tokens) else None

    def load_tokens(self):
        file_path = self.app.paths.data / "strava_tokens.json"
        try:
            with open(file_path) as f:
                return json.load(f)

        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def refresh_token(self, client_id, client_secret, refresh_token):
        url = "https://www.strava.com/oauth/token"

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }

        r = requests.post(url, data=payload)

        return r.json()

    def token_expired(self, tokens):
        return time.time() > tokens["expires_at"]

    def get_valid_token(self):
        tokens = self.load_tokens()
        if self.tokens_validos(tokens) and self.recuperarTokenBDD() != tokens["refresh_token"]:
            self.guardarTokenBDD(tokens["refresh_token"])   # la BD siempre con el token vigente

        if self.token_expired(tokens):
            print("Token caducado, refrescando...")

            tokens = self.refresh_token(
                self.client_id,
                self.client_secret,
                tokens["refresh_token"]
            )

            if not self.save_tokens(tokens):
                raise RuntimeError("Strava no devolvió un token válido al refrescar")

        return tokens["access_token"]

    def primeraEntrada(self, url):
        # Open the URL in a web browser
        webbrowser.open(url)

        print(
            """You will see a url that looks like this. """,
            """http://127.0.0.1:5000/authorization?state=&code=12323423423423423423423550&scope=read,activity:read_all,profile:read_all,read_all")""",
            """Copy the values between code= and & in the url that you see in the browser. """,
        )

    def crearTablaToken(self) -> None:
        """Tabla de una sola fila con el refresh_token de Strava."""
        self.cursor.execute("CREATE TABLE IF NOT EXISTS token (refresh_token TEXT)")
        self.sqliteConnection.commit()

    def guardarTokenBDD(self, refresh_token=None) -> bool:
        """Guarda el refresh_token en la BD (sustituye el anterior). Sin argumento usa el de strava_tokens.json."""
        if refresh_token is None:
            refresh_token = (self.load_tokens() or {}).get("refresh_token")
        if not refresh_token:
            logging.warning("No hay refresh_token que guardar en la BD")
            return False
        try:
            self.crearTablaToken()
            self.cursor.execute("DELETE FROM token")
            self.cursor.execute("INSERT INTO token (refresh_token) VALUES (?)", (refresh_token,))
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            self.sqliteConnection.rollback()
            logging.error("Error al guardar el token en la BD: %s", error)
            return False
        logging.info("Token de Strava guardado en la BD")
        return True

    def actualizarTokenBDD(self, refresh_token) -> bool:
        """Actualiza el refresh_token guardado; si todavía no había ninguno, lo inserta."""
        try:
            self.crearTablaToken()
            self.cursor.execute("UPDATE token SET refresh_token = ?", (refresh_token,))
            if self.cursor.rowcount == 0:
                self.cursor.execute("INSERT INTO token (refresh_token) VALUES (?)", (refresh_token,))
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            self.sqliteConnection.rollback()
            logging.error("Error al actualizar el token en la BD: %s", error)
            return False
        logging.info("Token de Strava actualizado en la BD")
        return True

    def recuperarTokenBDD(self) -> str:
        try:
            self.cursor.execute("SELECT refresh_token FROM token")
            resultado = self.cursor.fetchone()
        except sqlite3.Error as error:
            logging.error("Error al leer el token de la BD: %s", error)
            return "Error"
        return resultado[0] if resultado else "Error"

    def checkearTokenBDD(self) -> bool:
        try:
            self.cursor.execute("SELECT * FROM token")
            rows = self.cursor.fetchall()
        except sqlite3.Error as error:
            logging.error("Error al consultar la tabla token: %s", error)
            return False
        return len(rows) > 0

    def chequearDatosBDD(self, fecha) -> bool:
        try:
            self.cursor.execute("SELECT * FROM stravaValores sv WHERE sv.fecha = ?", (_dia(fecha),))
            rows = self.cursor.fetchall()
        except sqlite3.Error as error:
            logging.error("Error al consultar stravaValores: %s", error)
            return False
        return len(rows) > 0
        
    def operacionesFecha(self) -> bool:    
        hoy = datetime.today()
        print(hoy)
        primer_dia_mes = hoy.replace(day=1)
        print(primer_dia_mes)
        # Saber mes
        mes = hoy.month
        while mes > 1:
            check = self.chequearDatosBDD(primer_dia_mes)
            if check:
                self.extraerDatos
                self.guardarDatosBDD(primer_dia_mes)

            primer_dia_mes = primer_dia_mes - relativedelta(months=1)
            mes -= 1

        agnoPasado = primer_dia_mes.replace(month=12)
        agnoPasado = agnoPasado - relativedelta(years=1)
        print(agnoPasado)
        mes = hoy.month
        while mes > 1:
            check = self.chequearDatosBDD(primer_dia_mes)
            if check:
                self.guardarDatosBDD(primer_dia_mes)

            primer_dia_mes = primer_dia_mes - relativedelta(months=1)
            mes -= 1            
  
        return True

    def extraerDatos(self, fecha1, fecha2, tipoActividad="Ride", progreso=None):
        """Descarga las actividades entre fecha1 y fecha2. progreso(n) se llama tras cada una."""
        self.fecha_referencia = fecha1
        self.fecha_objetivo = fecha2
        print("Fecha Referencia: ", self.fecha_referencia)
        print("Fecha Objetivo: ", self.fecha_objetivo)
        #client = Client(access_token=code)

        self.total_distancia = 0
        self.total_distancia2 = 0
        self.total_tiempo = 0
        self.total_tiempo2 = 0
        self.total_desnivel = 0
        self.total_desnivel2 = 0
        self.contador = 0
        self.contador2 = 0
        self.actividades = []   # todas las descargadas, para ActividadesStrava

        for actividad in self.client.get_activities(after=self.fecha_referencia, before=self.fecha_objetivo):
            self.actividades.append(actividad)
            if progreso:
                progreso(len(self.actividades))
            if actividad.type == tipoActividad:
                self.total_distancia += actividad.distance  # metros
                self.total_tiempo += actividad.moving_time
                self.total_desnivel += actividad.total_elevation_gain
                self.contador += 1
        
        #print("Parte 1 FIN")
#
        #for actividad2 in self.client.get_activities(before=self.fecha_objetivo):
        #    if actividad2.type == tipoActividad:
        #        total_distancia2 += actividad2.distance  # metros
        #        total_tiempo2 += actividad2.moving_time
        #        total_desnivel2 += actividad2.total_elevation_gain
        #        contador2 += 1
#
        #print("Parte 2 end")
#
        self.total_actividades = math.trunc(self.contador)

    def imprimirDatos(self):
        print("Actividades:", math.trunc(self.contador))
        print("Distancia (km):", math.trunc(self.total_distancia  / 1000))
        print("Tiempo (horas):", math.trunc(self.total_tiempo / 3600))
        print("Desnivel (m):", math.trunc(self.total_desnivel))

    def crearTablaActividades(self) -> bool:
        try:
            asegurarTablaActividades(self.sqliteConnection)
            return True
        except sqlite3.Error as error:
            logging.error("Error al crear la tabla ActividadesStrava: %s", error)
            return False

    def nombreEquipo(self, gear_id):
        """Nombre de la bici/equipo de Strava (se consulta una vez por gear_id). Si falla, el propio id."""
        if not gear_id:
            return None
        cache = self._equipos
        if gear_id not in cache:
            try:
                cache[gear_id] = self.client.get_gear(gear_id).name or gear_id
            except Exception as error:   # red, permisos o equipo borrado: no debe parar la carga
                logging.warning("No se pudo obtener el equipo %s de Strava: %s", gear_id, error)
                cache[gear_id] = gear_id
        return cache[gear_id]

    def guardarActividadesBDD(self, usuario, tipo_vehiculo=None, actividades=None, progreso=None) -> int:
        """Guarda (o actualiza si ya existían) las actividades en ActividadesStrava. Devuelve cuántas.

        progreso(actual, total) se llama tras preparar cada actividad (incluye pedir a Strava el
        nombre de la bici, que es la parte lenta)."""
        actividades = [a for a in (self.actividades if actividades is None else actividades) if a.id is not None]
        filas = []
        for numero, actividad in enumerate(actividades, start=1):
            filas.append((
                actividad.id,                                           # -> StravaID
                _texto(actividad.type),
                _numero(actividad.distance, 1 / 1000),                  # m -> km
                _numero(actividad.total_elevation_gain, 1, 1),          # m
                _numero(actividad.moving_time, 1 / 3600, 3),            # s -> h
                _numero(actividad.average_speed, 3.6),                  # m/s -> km/h
                None if (_texto(actividad.type) or "").lower() in TIPOS_SIN_VEHICULO else tipo_vehiculo,
                self.nombreEquipo(getattr(actividad, "gear_id", None)),
                usuario,
            ))
            if progreso:
                progreso(numero, len(actividades))
        if not self.crearTablaActividades():
            return 0
        try:
            self.cursor.executemany(
                f"""INSERT INTO ActividadesStrava (StravaID, {COLUMNAS_DATOS_ACTIVIDADES})
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(StravaID) DO UPDATE SET
                       tipo = excluded.tipo, distancia = excluded.distancia, altimetria = excluded.altimetria,
                       duracion = excluded.duracion, velocidad_media = excluded.velocidad_media,
                       tipo_vehiculo = excluded.tipo_vehiculo, elemento = excluded.elemento, user = excluded.user""",
                filas,
            )
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            self.sqliteConnection.rollback()
            logging.error("Error al guardar en ActividadesStrava: %s", error)
            return 0
        logging.info("Guardadas %d actividades de Strava de %s", len(filas), usuario)
        return len(filas)

    def quitarActividadesDuplicadas(self) -> int:
        try:
            return quitarActividadesDuplicadas(self.sqliteConnection)
        except sqlite3.Error as error:
            self.sqliteConnection.rollback()
            logging.error("Error al quitar actividades duplicadas: %s", error)
            return 0

    def guardarDatosBDD(self, fecha) -> bool:
        """Guarda el resumen en stravaValores. Una fila por día y tipo: si ya había una (otra
        sincronización el mismo día) se actualiza en vez de duplicarla."""
        fila = (_dia(fecha), math.trunc(self.total_distancia / 1000), math.trunc(self.total_desnivel), "bike",
                self.total_actividades, math.trunc(self.total_tiempo / 3600))
        try:
            asegurarStravaValoresSinDuplicados(self.sqliteConnection)
            self.cursor.execute(
                """INSERT INTO stravaValores (fecha, valor, ascenso, tipo, num_actividades, horas)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(fecha, tipo) DO UPDATE SET
                       valor = excluded.valor, ascenso = excluded.ascenso,
                       num_actividades = excluded.num_actividades, horas = excluded.horas""",
                fila,
            )
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            self.sqliteConnection.rollback()
            print("Error al insertar en stravaValores:", error)
            logging.error("Error al insertar en stravaValores: %s", error)
            return False
        logging.info("Resumen de Strava guardado para %s", fila[0])
        return True
