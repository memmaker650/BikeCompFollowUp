# You will use this to log in to your Strava account
import webbrowser
import json
import sys
import math

from datetime import datetime

import sqlite3
import logging

from stravalib.client import Client

# Open the secrets file and store the client ID and client secret as objects, separated by a comma
# Read below to learn how to set up the app that provides you with the client ID
# and the client secret
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

client_id = valor1
client_secret = valor2
code = valor5

# sys.exit()

# Create a client object
client = Client()
# Define your scope (this is read-only - see below for a "write" example which
# allows you to update activities and publish new activities to your Strava account).
# read_all allows read access for both private and public activities
request_scope = ["read_all", "profile:read_all", "activity:read_all"]

# Create a localhost URL for authorization (for local development)
redirect_url = "http://127.0.0.1:5000/authorization"

# Create authorization url; your app client_id required to authorize
url = client.authorization_url(
    client_id=client_id,
    redirect_uri=redirect_url,
    scope=request_scope,
)

# Open the URL in a web browser
webbrowser.open(url)

print(
    """You will see a url that looks like this. """,
    """http://127.0.0.1:5000/authorization?state=&code=12323423423423423423423550&scope=read,activity:read_all,profile:read_all,read_all")""",
    """Copy the values between code= and & in the url that you see in the browser. """,
)
#
#    
# Using input allows you to copy the code into your Python console
# (or Jupyter Notebook)
code = input("Please enter the code that you received: ")
print(
    f"Great! Your code is {code}\n"
    "Next, I will exchange that code for a token.\n"
    "I only have to do this once."
)


# Exchange the code returned from Strava for an access token
token_response = client.exchange_code_for_token(
    client_id=client_id, client_secret=client_secret, code=code
)
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
athlete = client.get_athlete()
# Print athlete name :) If this works, your connection is successful!
print(f"Hi, {athlete.firstname} Welcome to stravalib!")

# You are now successfully authenticated!

fecha_limite = datetime(2025, 12, 31)
fecha_hoy = datetime(2026, 3, 2)
#client = Client(access_token=code)

total_distancia = 0
total_distancia2 = 0
total_tiempo = 0
total_tiempo2 = 0
total_desnivel = 0 
total_desnivel2 = 0
contador = 0
contador2 = 0

for actividad in client.get_activities(before=fecha_limite):
    if actividad.type == "Ride": 
        total_distancia += actividad.distance  # metros
        total_tiempo += actividad.moving_time
        total_desnivel += actividad.total_elevation_gain
        contador += 1

for actividad2 in client.get_activities(before=fecha_hoy):
    if actividad2.type == "Ride":
        total_distancia2 += actividad2.distance  # metros
        total_tiempo2 += actividad2.moving_time
        total_desnivel2 += actividad2.total_elevation_gain
        contador2 += 1

total_actividades = math.trunc(contador2-contador)        

print("Actividades:", math.trunc(contador2-contador))
print("Distancia (km):", math.trunc((total_distancia2-total_distancia)  / 1000))
print("Tiempo (horas):", math.trunc((total_tiempo2-total_tiempo) / 3600))
print("Desnivel (m):", math.trunc((total_desnivel2-total_desnivel)))


# Meter los datos extraídos en base de datos.
sqliteConnection = sqlite3.connect("./DB/dbbcfu.db")
cursor = sqliteConnection.cursor()
logging.info("Successfully Connected to SQLite")

try:
    cursor = sqliteConnection.cursor()
    cursor.execute("INSERT INTO stravaValores (fecha, valor, ascenso, tipo, num_actividades, horas) VALUES (?, ?, ?, ?, ?, ?)", (fecha_hoy, math.trunc((total_distancia2-total_distancia)  / 1000), 
    math.trunc((total_desnivel2-total_desnivel)), "bike", total_actividades, math.trunc((total_tiempo2-total_tiempo) / 3600))            )
except sqlite3.Error as error: 
    print("Error al insertar en Entradas: %s", error)
    logging.error("Error al insertar en Entradas: %s", error)
finally:
    print("Datos cargados correctamente en BDD.")
    logging.info("Datos de Entrada cargados correctamente.")
    sqliteConnection.commit()