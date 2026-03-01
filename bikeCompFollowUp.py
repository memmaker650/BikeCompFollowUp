from turtle import right
import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW, LEFT, RIGHT, END
from toga.colors import rgb

import sqlite3
import logging
from datetime import date

class HolaMundoApp(toga.App):
    sqliteConnection = 0
    index_entrada = 0

    def open_document(self, file):
        # Ignorar cualquier documento que intente abrir la app
        return
        
    def arrancarDB(self):
        self.sqliteConnection = sqlite3.connect("./DB/dbbcfu.db")
        cursor = self.sqliteConnection.cursor()
        logging.info("Successfully Connected to SQLite")

        logging.info('Creación Base de Datos y Tablas principales.')
        try:
            res = cursor.execute("""select * FROM datos""")
            if res.fetchone() != None:
                cursor.execute("""CREATE TABLE datos (id integer PRIMARY KEY, fecha Date, datos text NOT NULL, km integer NOT NULL, activo BOOLEAN NOT NULL)""")
                cursor.execute("""CREATE TABLE estadisticas (id interger PRIMARY KEY, jugador text NOT NULL, partida integer, disparos integer, nivelmax integer NOT NULL, enemigosmuertos integer, vidasusadas integer)""")
                self.sqliteConnection.commit()
                logging.info('Ejecución SQL creación tablas.')

            logging.info('Ejecución SQL creación tablas.')
        except sqlite3.Error as error:
            logging.error("Error al crear Tablas en SQLite", error)
            logging.error("Tablas ya existen en SQLite")
        finally:
            logging.info('Tablas DB creadas')

        # Crear tabla de tipos de vehículo si no existe
        try:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS tipo_vehiculo (
                    id integer PRIMARY KEY,
                    nombre text NOT NULL UNIQUE
                )"""
            )

            # Valores por defecto si la tabla está vacía
            cursor.execute("SELECT COUNT(*) FROM tipo_vehiculo")
            count = cursor.fetchone()[0]
            if count == 0:
                cursor.executemany(
                    "INSERT INTO tipo_vehiculo (nombre) VALUES (?)",
                    [("Carretera",), ("Montaña",), ("Híbrida",)]
                )
                self.sqliteConnection.commit()
                logging.info("Tabla tipo_vehiculo creada y rellenada con valores por defecto.")
        except sqlite3.Error as error:
            logging.error("Error al crear/rellenar tabla tipo_vehiculo en SQLite %s", error)

        logging.info('Fin acciones Base de Datos')

    def cerrarDB(self):
        #Cerramos base de datos
        self.sqliteConnection.close()
        logging.info("The SQLite connection is closed")

    # -------- Pantalla 1 (inicial) --------
    def construir_pantalla_inicial(self):
        main_box = toga.Box(style=Pack(direction=COLUMN, margin=20))

        contenido_box = toga.Box(
            style=Pack(direction=COLUMN, align_items=CENTER)
        )

        # Texto inicial encima del botón
        self.label = toga.Label(
            "Pulsa el botón",
            style=Pack(margin_bottom=20, text_align=CENTER)
        )

        # Botón que cambia el texto (ahora circular con símbolo '+')
        boton = toga.Button(
            "+",
            on_press=self.mostrar_hola_mundo,
            style=Pack(margin=10, width=40, height=40, padding=0, align_items=END)
        )

        contenido_box.add(self.label)
        contenido_box.add(boton)

        # Espaciador vertical para empujar la barra inferior hacia abajo
        espaciador_vertical = toga.Box(style=Pack(flex=1))

        # Barra inferior con botón a la derecha
        barra_inferior = toga.Box(
            style=Pack(margin_left=430, direction=COLUMN, horizontal_align_items=END)
        )

        boton_siguiente = toga.Button(
            "+",
            on_press=self.ir_a_pantalla_dos,
            style=Pack(margin=10)
        )

        barra_inferior.add(boton_siguiente)

        main_box.add(contenido_box)
        main_box.add(espaciador_vertical)
        main_box.add(barra_inferior)

        return main_box

    def mostrar_hola_mundo(self, widget):
        self.label.text = "Hola Mundo !"
        self.label.style.color = rgb(255, 165, 0)

    def ir_a_pantalla_dos(self, widget):
        self.main_window.content = self.construir_pantalla_dos()

    # -------- Pantalla 2 --------
    def construir_pantalla_dos(self):
        main_box = toga.Box(style=Pack(direction=COLUMN, margin=20))

        contenido_box = toga.Box(
            style=Pack(direction=COLUMN, padding_left=40, align_items='start')
        )

        self.label_pantalla_dos = toga.Label(
            "Nueva Entrada",
            style=Pack(margin_bottom=20, text_align=CENTER)
        )

        # Cargar opciones de tipo de vehículo desde la base de datos
        tipos_vehiculo = []
        try:
            cursor = self.sqliteConnection.cursor()
            cursor.execute("SELECT vehiculo FROM tipo_vehiculo ORDER BY vehiculo")
            tipos_vehiculo = [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as error:
            logging.error("Error al leer tabla tipo_vehiculo %s", error)

        if not tipos_vehiculo:
            tipos_vehiculo = ["Carretera", "Montaña", "Híbrida"]

        tipos_elemento = []
        try:
            cursor = self.sqliteConnection.cursor()
            cursor.execute("SELECT nombre FROM Elemento ORDER BY nombre")
            tipos_elemento = [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as error:
            logging.error("Error al leer tabla Elemento %s", error)

        # Si no hay datos en la tabla Elemento, usamos una lista por defecto
        if not tipos_elemento:
            tipos_elemento = ["Cadena", "Pastillas Freno", "Cubiertas"]

        # Caja con label "Nombre" a la izquierda y campo de texto a la derecha
        caja_nombre = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_nombre = toga.Label(
            "Nombre",
            style=Pack(margin_right=10)
        )

        self.entrada_texto = toga.TextInput(
            placeholder="Escribe algo...",
            style=Pack(width=250)
        )

        # Caja con label "DEscripción" a la izquierda y campo de texto a la derecha
        caja_descripcion = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_descripcion = toga.Label(
            "Descripción: ",
            style=Pack(margin_right=10)
        )

        self.descripcion_texto = toga.TextInput(
            placeholder="Escribe algo...",
            style=Pack(width=250)
        )

        # Caja con dropdown "Tipo vehículo"
        caja_tipo_vehiculo = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))
        

        label_tipo_vehiculo = toga.Label(
            "Tipo vehículo",
            style=Pack(margin_right=10)
        )

        self.selection_tipo_vehiculo = toga.Selection(
            items=tipos_vehiculo,
            style=Pack(width=250)
        )

        # Caja con dropdown "Elemento"
        caja_elemento = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_elemento = toga.Label(
            "Elemento",
            style=Pack(margin_right=10)
        )

        self.selection_elemento = toga.Selection(
            items=tipos_elemento,
            style=Pack(width=250)
        )

        # Caja con label "Fecha" a la izquierda y campo de texto a la derecha
        caja_fecha = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_fecha = toga.Label(
            "Fecha",
            style=Pack(margin_right=10)
        )

        self.entrada_fecha = toga.TextInput(
            placeholder="Fecha instalación",
            style=Pack(width=250),
            value=date.today().strftime("%Y-%m-%d")
        )

        caja_nombre.add(label_nombre)
        caja_nombre.add(self.entrada_texto)

        caja_descripcion.add(label_descripcion)
        caja_descripcion.add(self.descripcion_texto)

        caja_tipo_vehiculo.add(label_tipo_vehiculo)
        caja_tipo_vehiculo.add(self.selection_tipo_vehiculo)

        caja_elemento.add(label_elemento)
        caja_elemento.add(self.selection_elemento)

        caja_fecha.add(label_fecha)
        caja_fecha.add(self.entrada_fecha)

        boton_mostrar_texto = toga.Button(
            "Cargar",
            on_press=self.cargar_entrada,
            style=Pack(margin=10)
        )

        contenido_box.add(self.label_pantalla_dos)
        contenido_box.add(caja_nombre)
        contenido_box.add(caja_descripcion)
        contenido_box.add(caja_tipo_vehiculo)
        contenido_box.add(caja_elemento)
        contenido_box.add(caja_fecha)
        contenido_box.add(boton_mostrar_texto)

        espaciador = toga.Box(style=Pack(flex=1))

        # Barra inferior con botón a la izquierda (por defecto)
        barra_inferior = toga.Box(
            style=Pack(direction=ROW)
        )

        boton_volver = toga.Button(
            "◀ Volver",
            on_press=self.volver_pantalla_inicial,
            style=Pack(margin=10)
        )

        barra_inferior.add(boton_volver)

        main_box.add(contenido_box)
        main_box.add(espaciador)
        main_box.add(barra_inferior)

        return main_box

    def mostrar_texto_segunda(self, widget):
        texto = (self.entrada_texto.value or "").strip()
        self.label_pantalla_dos.text = texto if texto else "No has escrito nada"

    def cargar_entrada(self, widget):
        texto1 = (self.entrada_texto.value or "").strip()
        texto2 = (self.descripcion_texto.value or "").strip()
        tipov = (self.selection_tipo_vehiculo.value or "").strip()
        elemento = (self.selection_elemento.value or "").strip()
        f = (self.entrada_fecha.value or "").strip() or date.today().strftime("%Y-%m-%d")

        usuario = ""  # Ajusta si tienes campo de usuario en el formulario

        try:
            cursor = self.sqliteConnection.cursor()
            cursor.execute(
                "INSERT INTO Entradas (fecha, nombre, usuario, tipov, descripcion) VALUES (?, ?, ?, ?, ?)",
                (f, texto1, usuario, tipov, texto2)
            )
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            
            logging.error("Error al insertar en Entradas: %s", error)
        finally:
            self.label_pantalla_dos.text = "Entrada cargada correctamente."
            self.label_pantalla_dos.style.color = rgb(0, 255, 0)
            logging.info("Datos de Entrada cargados correctamente.")
            


    def volver_pantalla_inicial(self, widget):
        self.main_window.content = self.construir_pantalla_inicial()

    def startup(self):
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.arrancarDB()
        # Pantalla inicial al arrancar
        self.main_window.content = self.construir_pantalla_inicial()
        self.main_window.show()


def main():
    logging.basicConfig(filename="./log/bikecfu.log", level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',datefmt='%Y-%m-%d %H:%M:%S')
    logging.warning("Inicio pyiOS!!!")

    # Nombre visible y ID de la app (ajústalo a tu dominio)
    return HolaMundoApp("Bike Comp Follow App", "org.ejemplo.holamundo", icon="resources/icon.png")

if __name__ == "__main__":
    app = main()
    app.main_loop()