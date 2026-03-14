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
    def __init__(self):
        self.contador = 0
        self.contador2 = 0

        self.sqliteConnection = sqlite3.connect("./DB/dbbcfu.db")
        self.cursor = self.sqliteConnection.cursor()
        logging.info("Successfully Connected to SQLite")

    # Open the secrets file and store the client ID and client secret as objects, separated by a comma
    # Read below to learn how to set up the app that provides you with the client ID
    # and the client secret
    def initConexion(self):    
        with open("Resources/client_secrets.txt", "r", encoding="utf-8") as f:
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

        if tokens is not None:
            access_token = self.get_valid_token()
        else:
            print("No hay tokens guardados. Necesario OAuth.")
            CLIENT_ID = self.client_id

            code = self.get_strava_code(CLIENT_ID)
            print("Code final recibido:", code)   
            tokens = self.get_tokens(self.client_id, self.client_secret, code)
            print("Tokens :", tokens) 
            self.save_tokens(tokens)
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

    def save_tokens(self, tokens):
        with open("Resources/strava_tokens.json", "w") as f:
            json.dump(tokens, f)
            f.flush()

    def load_tokens(self):
        try:
            with open("Resources/strava_tokens.json") as f:
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

        if self.token_expired(tokens):
            print("Token caducado, refrescando...")

            tokens = self.refresh_token(
                self.client_id,
                self.client_secret,
                tokens["refresh_token"]
            )

            self.save_tokens(tokens)

        return tokens["access_token"]

    def primeraEntrada(self, url):
        # Open the URL in a web browser
        webbrowser.open(url)

        print(
            """You will see a url that looks like this. """,
            """http://127.0.0.1:5000/authorization?state=&code=12323423423423423423423550&scope=read,activity:read_all,profile:read_all,read_all")""",
            """Copy the values between code= and & in the url that you see in the browser. """,
        )

    def guardarTokenBDD(self) -> bool:
        try:
            self.cursor.execute("INSERT into token FROM stravaValores sv WHERE sv.fecha = ?", (fecha))
        except sqlite3.Error as error: 
            print("Error al insertar en Entradas: %s", error)
            logging.error("Error al insertar en Entradas: %s", error)
            return False
        finally:
            rows = self.cursor.fetchall()
            if rows.count > 0:
                print("Resultado del SELECT: ", rows.count)
                print("Chequeo ha ido bien.")
                return True
            else:
                return False

    def actualizarTokenBDD(self, toek) -> bool:
        try:
            self.cursor.execute("UPDATE token SET refresh_token = ?", (toek))
            print("UPDATE Token correcto !!")
            logging.error("UPDATE Token correcto !!")
        except sqlite3.Error as error: 
            print("Error al UPDATE el token: %s", error)
            logging.error("Error al UPDATE el token:  %s", error)
            return False

    def recuperarTokenBDD(self) -> str:
        try:
            self.cursor.execute("select refresh_token from token")
            resultado = self.cursor.fetchone()
            refresh_token = resultado[0]
            return refresh_token
        except sqlite3.Error as error: 
            print("Error al SELECT Token: %s", error)
            logging.error("Error al SELECT Token: %s", error)
            return "Error"            

    def checkearTokenBDD(self) -> bool:
        try:
            self.cursor.execute("SELECT * FROM token")
        except sqlite3.Error as error: 
            print("Error al ejecutar la SELECT: %s", error)
            logging.error("Error al ejecutar la SELECT: %s", error)
            return False
        finally:
            rows = self.cursor.fetchall()
            if len(rows) > 0:
                print("Resultado del SELECT: ", rows.count)
                print("Chequeo ha ido bien.")
                return True
            else:
                return False

    def chequearDatosBDD(self, fecha) -> bool:
        sqliteConnection = sqlite3.connect("./DB/dbbcfu.db")
        cursor = sqliteConnection.cursor()
        logging.info("Successfully Connected to SQLite")

        try:
            cursor = sqliteConnection.cursor()
            cursor.execute("SELECT * FROM stravaValores sv WHERE sv.fecha = ?", (fecha))
        except sqlite3.Error as error: 
            print("Error al insertar en Entradas: %s", error)
            logging.error("Error al insertar en Entradas: %s", error)
            return False
        finally:
            rows = cursor.fetchall()
            if len(rows) > 0:
                print("Resultado del SELECT: ", rows.count)
                print("Chequeo ha ido bien.")
                return True
            else:
                return False
        
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

    def extraerDatos(self, fecha1, fecha2, tipoActividad="Ride"):
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

        for actividad in self.client.get_activities(after=self.fecha_referencia, before=self.fecha_objetivo):
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

    def guardarDatosBDD(self, fecha):
        # Meter los datos extraídos en base de datos.
        try:
            self.cursor.execute("INSERT INTO stravaValores (fecha, valor, ascenso, tipo, num_actividades, horas) VALUES (?, ?, ?, ?, ?, ?)", (fecha, math.trunc(self.total_distancia/ 1000), 
                math.trunc(self.total_desnivel), "bike", self.total_actividades, math.trunc(self.total_tiempo / 3600)))
            
            self.sqliteConnection.commit()
            
            if self.cursor.rowcount > 0:
                print("Registro insertado correctamente")
                logging.info("Registro insertado correctamente")
            else:
                print("No se insertó ningún registro")
                logging.warning("No se insertó ningún registro")
        except sqlite3.Error as error: 
            print("Error al insertar en Entradas: %s", error)
            logging.error("Error al insertar en Entradas: %s", error) 