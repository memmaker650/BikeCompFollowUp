# You will use this to log in to your Strava account
import webbrowser
import json
import sys
import math

from datetime import datetime
from dateutil.relativedelta import relativedelta

import sqlite3
import logging

from stravalib.client import Client

class StravaData:
    contador, contador2 = 0
    client_id, client_secret, code = ""
    client = ""
    total_distancia, total_distancia2 = 0
    total_desnivel, total_desnivel2 = 0
    total_tiempo, total_tiempo2 = 0
    total_actividades = 0
    fecha_hoy, fecha_objetivo = datetime

    # Constructor: inicializa atributos (características)
    def __init__(self):
        self.contador = 0
        self.contador2 = 0

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

# sys.exit()
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

        # Open the URL in a web browser
        webbrowser.open(url)

        print(
            """You will see a url that looks like this. """,
            """http://127.0.0.1:5000/authorization?state=&code=12323423423423423423423550&scope=read,activity:read_all,profile:read_all,read_all")""",
            """Copy the values between code= and & in the url that you see in the browser. """,
        )
  
        # Using input allows you to copy the code into your Python console
        # (or Jupyter Notebook)
        code = input("Please enter the code that you received: ")
        print(
            f"Great! Your code is {code}\n"
            "Next, I will exchange that code for a token.\n"
            "I only have to do this once."
        )


        #    Exchange the code returned from Strava for an access token
        token_response = self.client.exchange_code_for_token(client_id=self.client_id, client_secret=self.client_secret, code=code)
        with open("Resources/token_response.json", "w", encoding="utf-8") as f:
            json.dump(token_response, f, ensure_ascii=False, indent=2)

        # Save the token response as a JSON file
        with open("Resources/token_response.json", "w") as f:
            json.dump(token_response, f)

        print("Token saved - hooray!")

        # Access and refresh tokens
        access_token = token_response["access_token"]
        refresh_token = token_response["refresh_token"]  # Use this after 6 hours

        print(f"Token Response -->  {token_response}" )
        # Example output of token_response
        # {'access_token': 'value-here-123123123', 'refresh_token': # '123123123',
        # 'expires_at': 1673665980}

        # Get current athlete details
        athlete = self.client.get_athlete()
        # Print athlete name :) If this works, your connection is successful!
        print(f"Hi, {athlete.firstname} Welcome to stravalib!")

        # You are now successfully authenticated!

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
            if rows.count > 0:
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
        #client = Client(access_token=code)

        total_distancia = 0
        total_distancia2 = 0
        total_tiempo = 0
        total_tiempo2 = 0
        total_desnivel = 0
        total_desnivel2 = 0
        contador = 0
        contador2 = 0

        for actividad in self.client.get_activities(before=self.fecha_referencia):
            if actividad.type == tipoActividad: 
                total_distancia += actividad.distance  # metros
                total_tiempo += actividad.moving_time
                total_desnivel += actividad.total_elevation_gain
                contador += 1

        for actividad2 in self.client.get_activities(before=self.fecha_objetivo):
            if actividad2.type == tipoActividad:
                total_distancia2 += actividad2.distance  # metros
                total_tiempo2 += actividad2.moving_time
                total_desnivel2 += actividad2.total_elevation_gain
                contador2 += 1

        self.total_actividades = math.trunc(contador2-contador)

    def imprimirDatos(self):
        print("Actividades:", math.trunc(self.contador2-self.contador))
        print("Distancia (km):", math.trunc((self.total_distancia2-self.total_distancia)  / 1000))
        print("Tiempo (horas):", math.trunc((self.total_tiempo2-self.total_tiempo) / 3600))
        print("Desnivel (m):", math.trunc((self.total_desnivel2-self.total_desnivel)))

    def guardarDatosBDD(self, fecha):
        # Meter los datos extraídos en base de datos.
        sqliteConnection = sqlite3.connect("./DB/dbbcfu.db")
        cursor = sqliteConnection.cursor()
        logging.info("Successfully Connected to SQLite")

        try:
            cursor = sqliteConnection.cursor()
            cursor.execute("INSERT INTO stravaValores (fecha, valor, ascenso, tipo, num_actividades, horas) VALUES (?, ?, ?, ?, ?, ?)", (fecha, math.trunc((self.total_distancia2-self.total_distancia)  / 1000), 
                math.trunc((self.total_desnivel2-self.total_desnivel)), "bike", self.total_actividades, math.trunc((self.total_tiempo2-self.total_tiempo) / 3600))            )
        except sqlite3.Error as error: 
            print("Error al insertar en Entradas: %s", error)
            logging.error("Error al insertar en Entradas: %s", error)
        finally:
            print("Datos cargados correctamente en BDD.")