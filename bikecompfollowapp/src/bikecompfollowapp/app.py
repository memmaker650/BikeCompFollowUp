""""""""""
App to follow up bike comp, sneakers and car comp to avoid breaks.
"""""""""""

import datetime
import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW, LEFT, RIGHT, END
from toga.colors import rgb

from pathlib import Path
import sys
import sqlite3
import logging
from datetime import datetime

if __name__ == "__main__" or __package__ is None:
    import stravaConnect
else:
    from . import stravaConnect
import asyncio
from plyer import notification


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
    def get(cls, kind="data", filename=None):
        base = cls.base_dir(kind)
        return base / filename if filename else base

class BikeCompFollowApp(toga.App):
    cursor = None
    sqliteConnection = 0
    index_entrada = 0
    db_path = None
    log_path = None
    usuarioSeleccionado = None

    def startup(self):
        # ✅ AQUÍ sí existe self
        AppPaths.init(self)
        print("APP ID:", self.app_id)

        self.main_window = toga.MainWindow(title=self.formal_name)
        
        # Obtener la ruta del directorio actual del script
        self.log_path = AppPaths.get("data", "bikecfu.log")
        print("DATA DIR:", self.paths.data)
        print("Log DIR:", self.log_path)
        
        logging.basicConfig(filename=self.log_path, level=logging.DEBUG,
        format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',datefmt='%Y-%m-%d %H:%M:%S')
        logging.info("Inicio BikeCompFollowApp iOS App!!!")
        print("Inicio BikeCompFollowApp iOS App!!!")

        self.arrancarDB()

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
    def lanzarNotificacion(self):
        logging.info("Dentro lanzar Notificación.")

    def crearDBBasica(self):
        try:
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS datos (id integer PRIMARY KEY, fecha Date, datos text NOT NULL, km integer NOT NULL, activo BOOLEAN NOT NULL)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS Elemento (id INTEGER PRIMARY KEY,nombre TEXT)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS stravaValores  (id integer PRIMARY KEY,  fecha date not NULL, valor INTEGER not NULL,  ascenso INTEGER, tipo TEXT not null, num_actividades INTEGER, horas INTEGER)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS Entradas (id integer PRIMARY KEY,  fecha Date,  nombre text NOT NULL,  usuario text,  tipov integer NOT NULL, descripcion  TEXT NOT NULL, FOREIGN KEY (tipov) REFERENCES tipo_vehiculo(id))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS linked_elements (id integer PRIMARY KEY, fecha Date, Entrada_num integer, num_elemento, FOREIGN KEY (Entrada_num) REFERENCES Entradas(id), FOREIGN KEY (num_Elemento) REFERENCES Elemento(id))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS estadisticas (id interger PRIMARY KEY, jugador text NOT NULL, partida integer, disparos integer, nivelmax integer NOT NULL, enemigosmuertos integer, vidasusadas integer)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS tipo_vehiculo (id	INTEGER PRIMARY KEY,vehiculo TEXT)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS archivoscomponentes (id INTEGER PRIMARY KEY, usuario NOT NULL, elemento TEXT NOT NULL, descripcion TEXT, marca TEXT, fechaInsercion Date NOT NULL, distanciaLímite integer, activo BOOLEAN NO NULL)""")
        except sqlite3.Error as error:
            logging.error("Error al crear Tablas en SQLite", error)
            logging.error("Tablas ya existen en SQLite")
        finally:
            logging.info('Tablas DB creadas')
            self.sqliteConnection.commit

        # Carga de los datos básicos
        try:
            self.cursor.execute("""INSERT INTO tipo_vehiculo (vehiculo) VALUES ('Coche')""")
            self.cursor.execute("""INSERT INTO tipo_vehiculo (vehiculo) VALUES ('Bici Carretera')""")
            self.cursor.execute("""INSERT INTO tipo_vehiculo (vehiculo) VALUES ('Bici Gravel')""")
            self.cursor.execute("""INSERT INTO tipo_vehiculo (vehiculo) VALUES ('Bici MTB')""")
            self.cursor.execute("""INSERT INTO tipo_vehiculo (vehiculo) VALUES ('Tractor')""")
        except sqlite3.Error as error:
            logging.error("Error al cargar datos de las Tablas Básicas en SQLite", error)
        finally:
            logging.info('Carga de datos en Tipo Vehículos correcta.')
            self.sqliteConnection.commit
        
        try:
            self.cursor.execute("""INSERT INTO Elemento (nombre) VALUES ('cadena')""")
            self.cursor.execute("""INSERT INTO Elemento (nombre) VALUES ('pastillas freno')""")
            self.cursor.execute("""INSERT INTO Elemento (nombre) VALUES ('Cubierta')""")
            self.cursor.execute("""INSERT INTO Elemento (nombre) VALUES ('Cinta Manillar')""")
            self.cursor.execute("""INSERT INTO Elemento (nombre) VALUES ('Piñonera')""")
            self.cursor.execute("""INSERT INTO Elemento (nombre) VALUES ('Plato')""")
            self.cursor.execute("""INSERT INTO Elemento (nombre) VALUES ('Cambio Trasero')""")
            self.cursor.execute("""INSERT INTO Elemento (nombre) VALUES ('Líquido Frenos')""")
            self.cursor.execute("""INSERT INTO Elemento (nombre) VALUES ('Maneta Cambio')""")
            self.cursor.execute("""INSERT INTO Elemento (nombre) VALUES ('Cámara')""")
        except sqlite3.Error as error:
            logging.error("Error al cargar datos de las Tablas Básicas en SQLite", error)
        finally:
            logging.info('Carga de datos en Elementos correcta.')
            self.sqliteConnection.commit

    def arrancarDB(self):
        # Obtener la ruta del directorio actual del script
        
        self.db_path = AppPaths.get("data", "dbbcfu.db")

        # Esto crea el fichero si no existe
        self.sqliteConnection = sqlite3.connect(self.db_path)
        self.cursor = self.sqliteConnection.cursor()

        print("DB DIR:", self.db_path)
        
        self.sqliteConnection.commit()
        print("Base de datos lista")

        logging.info('Creación Base de Datos y Tablas principales.')
        try:
            res = self.cursor.execute("""select * FROM Entradas""")
            tables = self.cursor.fetchall()
            if not tables:
                print("⚠️ Base de datos vacía o incorrecta")
                self.crearDBBasica()
                return 
            else:
                print("Tablas encontradas:", tables)

            if res.fetchone() != None:
                self.crearDBBasica()
                self.sqliteConnection.commit()
                logging.info('Ejecución SQL creación tablas Básicas.')

            logging.info('Ejecución SQL creación tablas.')
        except sqlite3.Error as error:
            logging.error("Error al crear Tablas en SQLite", error)
            logging.error("Tablas ya existen en SQLite")
        finally:
            logging.info('Tablas DB creadas')

        # Crear tabla de tipos de vehículo si no existe
        try:
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS tipo_vehiculo (
                    id integer PRIMARY KEY,
                    nombre text NOT NULL UNIQUE
                )"""
            )

            # Valores por defecto si la tabla está vacía
            self.cursor.execute("SELECT COUNT(*) FROM tipo_vehiculo")
            count = self.cursor.fetchone()[0]
            if count == 0:
                self.cursor.executemany(
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
        filas = None 
        self.usuarioSeleccionado = ""

        contenido_box = toga.Box(
            style=Pack(direction=COLUMN, align_items=CENTER, gap=15)
        )

        try:
            self.cursor.execute("""SELECT nombre, usuario from ENTRADAS""")
            filas = self.cursor.fetchall()   # lista de tuplas (nombre, tipov)
        except sqlite3.Error as error:
            logging.error("Error al crear/rellenar tabla tipo_vehiculo en SQLite %s", error)

        # Texto inicial encima del botón
        self.label = toga.Label(
            "Selecciona el usuario",
            style=Pack(margin_bottom=20, text_align=CENTER)
        )

        contenido_box.add(self.label)

        if (filas != None):
            for nombre, usuario in filas:
                print("Nombre:", nombre, "Usuario:", usuario) 

                cadena = usuario + "-" + nombre # Concatener 2 string añadiendo un salto de línea. " \n "
                # Botón que cambia el texto (ahora circular con símbolo '+')
                boton = toga.Button(cadena, on_press=lambda widget, valor=usuario: self.ir_a_pantalla_tres(widget, valor),
                style=Pack(width=140, height=60, padding=0))

                contenido_box.add(boton)

        # Espaciador vertical para empujar la barra inferior hacia abajo
        espaciador_vertical = toga.Box(style=Pack(flex=1))

        # Barra inferior: botón izquierda, hueco en medio, botón derecha
        barra_inferior = toga.Box(
            style=Pack(direction=ROW)
        )

        boton_strava = toga.Button(
            "Strava Sync",
            on_press=self.ir_a_pantalla_recoleccionDatos,
            style=Pack(margin=10)
        )

        boton_siguiente = toga.Button(
            "+ Usuario",
            on_press=self.ir_a_pantalla_dos,
            style=Pack(margin=10)
        )

        espaciador_horizontal = toga.Box(style=Pack(flex=1))

        barra_inferior.add(boton_strava)
        barra_inferior.add(espaciador_horizontal)
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

        # Caja con label "Usuario" a la izquierda y campo de texto a la derecha
        caja_usuario = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_usuario = toga.Label(
            "Usuario",
            style=Pack(margin_right=10)
        )

        self.usuario_texto = toga.TextInput(
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
            value=datetime.today().strftime("%Y-%m-%d")
        )

        # Orden de tabulación (Tab) entre campos
        self.entrada_texto.tab_index = 0
        self.usuario_texto.tab_index = 1
        self.descripcion_texto.tab_index = 2
        self.selection_tipo_vehiculo.tab_index = 3
        self.selection_elemento.tab_index = 4
        self.entrada_fecha.tab_index = 5

        caja_nombre.add(label_nombre)
        caja_nombre.add(self.entrada_texto)

        caja_usuario.add(label_usuario)
        caja_usuario.add(self.usuario_texto)

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
        boton_mostrar_texto.tab_index = 5

        contenido_box.add(self.label_pantalla_dos)
        contenido_box.add(caja_nombre)
        contenido_box.add(caja_usuario)
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
        boton_volver.tab_index = 6

        barra_inferior.add(boton_volver)

        # En macOS (Cocoa) tab_index no está implementado; enlazar cadena de foco a mano
        if sys.platform == "darwin":
            try:
                n = lambda w: w._impl.native
                n(self.entrada_texto).nextKeyView = n(self.usuario_texto)
                n(self.usuario_texto).nextKeyView = n(self.descripcion_texto)
                n(self.descripcion_texto).nextKeyView = n(self.selection_tipo_vehiculo)
                n(self.selection_tipo_vehiculo).nextKeyView = n(self.selection_elemento)
                n(self.selection_elemento).nextKeyView = n(self.entrada_fecha)
                n(self.entrada_fecha).nextKeyView = n(boton_mostrar_texto)
                n(boton_mostrar_texto).nextKeyView = n(boton_volver)
                n(boton_volver).nextKeyView = n(self.entrada_texto)
            except Exception as e:
                logging.debug("No se pudo configurar cadena Tab en Cocoa: %s", e)

        main_box.add(contenido_box)
        main_box.add(espaciador)
        main_box.add(barra_inferior)

        return main_box

    def mostrar_texto_segunda(self, widget):
        texto = (self.entrada_texto.value or "").strip()
        self.label_pantalla_dos.text = texto if texto else "No has escrito nada"

    def cargar_entrada(self, widget):
        texto1 = (self.entrada_texto.value or "").strip()
        textoUser = (self.usuario_texto.value or "").strip()
        texto2 = (self.descripcion_texto.value or "").strip()
        tipov = (self.selection_tipo_vehiculo.value or "").strip()
        elemento = (self.selection_elemento.value or "").strip()
        f = (self.entrada_fecha.value or "").strip() or datetime.today().strftime("%Y-%m-%d")

        try:
            cursor = self.sqliteConnection.cursor()
            cursor.execute(
                "INSERT INTO Entradas (fecha, nombre, usuario, tipov, descripcion) VALUES (?, ?, ?, ?, ?)",
                (f, texto1, textoUser, tipov, texto2)
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
    
    # -------- Pantalla 3 --------
    def construir_pantalla_tres(self, valor):
        main_box = toga.Box(style=Pack(direction=COLUMN, margin=20))

        contenido_box = toga.Box(
            style=Pack(direction=COLUMN, padding_left=40, align_items='start', flex=1)
        )

        titulo = "User: " + str(valor) 
        self.usuarioSeleccionado = valor

        self.label_pantalla_dos = toga.Label(
            titulo,
            style=Pack(margin_bottom=20, text_align=CENTER)
        )

        contenido_box.add(self.label_pantalla_dos)

        dataTable = None
        data = None

        # archivoscomponentes (id INTEGER PRIMARY KEY, usuario, elemento TEXT, descripcion TEXT, marca TEXT, fechaInsercion Date, distanciaLímite integer, tiempoLímite integer, activo BOOLEAN)
        try:
            cursor = self.sqliteConnection.cursor()
            cursor.execute(
                "SELECT elemento, descripcion, fechaInsercion, distanciaLimite, 'x', tiempoLimite, activo "
                "FROM archivoscomponentes WHERE usuario = ?",
                (self.usuarioSeleccionado,),
            )
            dataTable = cursor.fetchall()
        except sqlite3.Error as error:
            logging.error("Error en el SELECT de la TABLA Comp: %s", error)
            print("Error en el SELECT de la TABLA Comp: %s", error)
            data=[("Juan", "Madrid", "08-07-1984", 5000, 1249, 300, "True"),
                ("Ana", "Barcelona","06-08-2020", 2500, 2300, 125, "False"),
                ("Luis", "Zaragoza","28-11-2023", 3300, 256, 120, "True"),
            ]
        finally:
            self.label_pantalla_dos.text = "Datos de la TABLA COMP leídos  correctamente."
            self.label_pantalla_dos.style.color = rgb(0, 255, 0)
            logging.info("Datos de TABLA LEÍDOS correctamente.")
            if dataTable is not None:
                data = dataTable

        data = list(data) if data is not None else []
        # Altura según nº de filas (Toga no la calcula sola). Tope para listas largas → scroll dentro de la tabla.
        _h_cabecera, _h_fila, _h_max = 28, 22, 520
        _n = len(data)
        _altura_tabla = _h_cabecera + max(_n, 1) * _h_fila
        _altura_tabla = min(_altura_tabla, _h_max)

        # Definir tabla con cabeceras
        self.tabla = toga.Table(
            headings=["Componente", "Descripción", "Fecha", "Distancia Max Comp", "Distancia desde Inserción", "Tiempo Montado", "Activo"],
            data=data,
            style=Pack(height=_altura_tabla),
        )

        contenido_box.add(self.tabla)

        # Barra inferior con botón a la izquierda (por defecto)
        barra_inferior = toga.Box(
            style=Pack(direction=ROW)
        )

        boton_volver = toga.Button(
            "◀ Volver",
            on_press=self.volver_pantalla_inicial,
            style=Pack(margin=10)
        )

        espaciador_horizontal = toga.Box(style=Pack(flex=1))

        boton_nuevocomponente = toga.Button(
            "+ Componente",
            on_press=lambda widget, valor=valor:self.ir_a_pantalla_cinco(widget, valor),
            style=Pack(margin=10)
        )

        barra_inferior.add(boton_volver)
        barra_inferior.add(espaciador_horizontal)
        barra_inferior.add(boton_nuevocomponente)

        main_box.add(contenido_box)
        main_box.add(barra_inferior)

        return main_box

    def ir_a_pantalla_tres(self, widget, valor):
        self.main_window.content = self.construir_pantalla_tres(valor)

    # -------- Pantalla 4 --------
    def construir_pantalla_cuatro(self):
        main_box = toga.Box(style=Pack(direction=COLUMN, margin=20))

        contenido_box = toga.Box(
            style=Pack(direction=COLUMN, padding_left=40, align_items='start')
        )

        self.label_pantalla_dos = toga.Label(
            "Pantalla 4",
            style=Pack(margin_bottom=20, text_align=CENTER)
        )

        contenido_box.add(self.label_pantalla_dos)

        # Espaciador vertical para empujar la barra inferior hacia abajo
        espaciador_vertical = toga.Box(style=Pack(flex=1))

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
        main_box.add(espaciador_vertical)
        main_box.add(barra_inferior)

        return main_box

    def ir_a_pantalla_cuatro(self, widget):
        self.main_window.content = self.construir_pantalla_cuatro()

    def desactivarComponente(self, componente, usuario):
        try:
            cursor = self.sqliteConnection.cursor()
            cursor.execute(
                "UPDATE archivoscomponentes SET activo =False WHERE usuario = ? AND componente = ?", (componente, usuario)
            )
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            
            logging.error("Error al DESACTIVAR el Componente: %s", error)
        finally:
            self.label_pantalla_dos.text = "Entrada cargada correctamente."
            self.label_pantalla_dos.style.color = rgb(0, 255, 0)
            logging.info("UPDATE hecho para DESACTIVAR Componente.")

    # CREATE TABLE IF NOT EXISTS archivoscomponentes (id INTEGER PRIMARY KEY, usuario NOT NULL, elemento TEXT NOT NULL, descripcion TEXT, marca TEXT, fechaInsercion Date NOT NULL, distanciaLímite integer, tiempoLímite integer, activo BOOLEAN DEFAULT True)
    def anadirComponente(self, valor1, user, valor2, valor3, valor4, valor5=None, valor6=None):
        logging.info("Dentro añadir Componente.")

        tiempolim = 500
        distlim = 5000

        #if not (mi_textinput.value or "").strip():
        if not (valor5.value or "").strip():
            valor5 = distlim
        else:
            valor5 = valor5.value
        if not (valor6.value or "").strip():
            valor6 = tiempolim
        else:
            valor6 = valor6.value
        

        f = f = (valor1.value or "").strip() or datetime.today().strftime("%Y-%m-%d")
        print("Fecha de Inserción : ", f)
        print("Seleccion Elemento : ", valor2.value)
        print("Distancia Límite : ", valor5)
        print("Tiempo Límite : ", valor6)

        try:
            cursor = self.sqliteConnection.cursor()
            cursor.execute(
                "INSERT INTO archivoscomponentes (fechaInsercion, usuario, elemento, descripcion, marca, distanciaLimite, tiempoLimite) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f, user, valor2.value, valor3.value, valor4.value, valor5, valor6)
            )
        except sqlite3.Error as error:
            print("Error al insertar en Entradas: %s", error)
            logging.error("Error al insertar en Entradas: %s", error)
        finally:
            self.sqliteConnection.commit()
            self.label_pantalla_dos.text = "Entrada cargada correctamente."
            self.label_pantalla_dos.style.color = rgb(0, 255, 0)
            logging.info("Datos de Entrada cargados correctamente.")

    def cargar_componente(self, entrada_fecha, usuarioSeleccionado, selection_elemento, descripcion_texto, marca_texto, distancialim_texto, tiempolim_texto) -> bool: 
        logging.info("Dentro de método Cargar Componente.")
        print("Dentro de método Cargar Componente.")
        self.anadirComponente(entrada_fecha, usuarioSeleccionado, selection_elemento, descripcion_texto, marca_texto, distancialim_texto, tiempolim_texto)

        return True

    # -------- Pantalla 5 --------
    def construir_pantalla_cinco(self, valor):
        main_box = toga.Box(style=Pack(direction=COLUMN, margin=20))

        contenido_box = toga.Box(
            style=Pack(direction=COLUMN, padding_left=40, align_items='start')
        )

        tituloSreen5 = "Añadir Componente: "+str(valor)

        self.label_pantalla_dos = toga.Label(
            tituloSreen5,
            style=Pack(margin_bottom=20, text_align=CENTER)
        )

        contenido_box.add(self.label_pantalla_dos)

        # Caja con label "Fecha" a la izquierda y campo de texto a la derecha
        caja_fecha = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_fecha = toga.Label(
            "Fecha",
            style=Pack(margin_right=10)
        )

        self.entrada_fecha = toga.TextInput(
            placeholder="Fecha instalación",
            style=Pack(width=250),
            value=datetime.today().strftime("%Y-%m-%d")
        )

        caja_fecha.add(label_fecha)
        caja_fecha.add(self.entrada_fecha)

        # Caja con dropdown "Elemento"
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

        caja_elemento = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_elemento = toga.Label(
            "Elemento",
            style=Pack(margin_right=10)
        )

        self.selection_elemento = toga.Selection(
            items=tipos_elemento,
            style=Pack(width=250)
        )

        # Caja con label "Descripción" a la izquierda y campo de texto a la derecha
        caja_descripcion = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_descripcion = toga.Label(
            "Descripción: ",
            style=Pack(margin_right=10)
        )

        self.descripcion_texto = toga.TextInput(
            placeholder="Escribe algo...",
            style=Pack(width=250)
        )

        # Caja con label "Marca" a la izquierda y campo de texto a la derecha
        caja_marca = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_marca = toga.Label(
            "Marca Comp: ",
            style=Pack(margin_right=10)
        )

        self.marca_texto = toga.TextInput(
            placeholder="Escribe algo...",
            style=Pack(width=250)
        )

        # Caja con label "Marca" a la izquierda y campo de texto a la derecha
        caja_tiempolim = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_tiempolim = toga.Label(
            "Tiempo Límite: ",
            style=Pack(margin_right=10)
        )

        self.tiempolim_texto = toga.TextInput(
            placeholder="Escribe algo...",
            style=Pack(width=250)
        )

        # Caja con label "Marca" a la izquierda y campo de texto a la derecha
        caja_distancialim = toga.Box(style=Pack(direction=ROW, margin_bottom=10, align_items=CENTER))

        label_distancialim = toga.Label(
            "Distancia Límite: ",
            style=Pack(margin_right=10)
        )

        self.distancialim_texto = toga.TextInput(
            placeholder="Escribe algo...",
            style=Pack(width=250)
        )

        boton_Cargar = toga.Button(
            "Cargar",
            on_press=lambda widget:self.cargar_componente(self.entrada_fecha, self.usuarioSeleccionado, self.selection_elemento, self.descripcion_texto, self.marca_texto, self.distancialim_texto, self.tiempolim_texto),
            style=Pack(margin=10)
        )

        caja_elemento.add(label_elemento)
        caja_elemento.add(self.selection_elemento)
        caja_descripcion.add(label_descripcion)
        caja_descripcion.add(self.descripcion_texto)
        caja_marca.add(label_marca)
        caja_marca.add(self.marca_texto)
        caja_distancialim.add(label_distancialim)
        caja_distancialim.add(self.distancialim_texto)
        caja_tiempolim.add(label_tiempolim)
        caja_tiempolim.add(self.tiempolim_texto)
        

        contenido_box.add(caja_fecha)
        contenido_box.add(caja_elemento)
        contenido_box.add(caja_descripcion)
        contenido_box.add(caja_marca)
        contenido_box.add(caja_distancialim)
        contenido_box.add(caja_tiempolim)
        
        contenido_box.add(boton_Cargar)

        # Espaciador vertical para empujar la barra inferior hacia abajo
        espaciador_vertical = toga.Box(style=Pack(flex=1))

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
        main_box.add(espaciador_vertical)
        main_box.add(barra_inferior)

        return main_box

    def ir_a_pantalla_cinco(self, widget, valor):
        self.main_window.content = self.construir_pantalla_cinco(valor)

    def iniciar_tarea(self, widget):
        self.add_background_task(self.tarea_larga)
        notification.notify(title="Inicio", message="Fin Tareas", app_name="BikeCompFollowApp", app_icon="resources/bici2.icns")

    async def tarea_larga(self, widget):
        for i in range(1, self.total + 1):
            await asyncio.sleep(0.3)   
            # Actualizar barra
            self.progress.value = i
            # actualizar texto
            self.label.text = f"Procesando {i} de {self.total}"
    
    def recolectarDatosStrava(self, widget):
        datosStrava = stravaConnect.StravaData(self)
        datosStrava.initConexion()
        datosStrava.crearObjetoCliente()
        datosStrava.extraerDatos(datetime(2025, 12, 31), datetime.now())
        datosStrava.guardarDatosBDD(datetime.now())

    def ir_a_pantalla_recoleccionDatos(self, widget):
        self.main_window.content = self.barraProgresoCargaDatos()    

    def barraProgresoCargaDatos(self):    

        self.total = 20

        # Texto de progreso
        self.label = toga.Label(
            "Pulsa Inicio para cargar los datos.",
            style=Pack(padding=10)
        )

        # Barra de progreso
        self.progress = toga.ProgressBar(max=self.total,
            value=0, style=Pack(padding=10))

        # Botón para iniciar tarea
        box = toga.Box(style=Pack(direction=COLUMN, padding=20))

        # Añadimos los widgets al mismo box
        box.add(self.label)
        box.add(self.progress)

        boton_iniciar = toga.Button("Iniciar", on_press=self.iniciar_tarea, style=Pack(padding=10))
        box.add(boton_iniciar)

        boton_datos = toga.Button("Extraer Datos Strava", on_press=self.recolectarDatosStrava, style=Pack(padding=10))
        box.add(boton_datos)

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
        box.add(barra_inferior)

        # self.main_window = toga.MainWindow(title="Ejemplo ProgressBar")
        # self.main_window.content = box
        # self.main_window.show()
        return box

def main():
    # Nombre visible y ID de la app (ajústalo a tu dominio)
    return BikeCompFollowApp("Bike Comp Follow App", "com.SkullWithGasMask", icon="resources/icon.png")

if __name__ == "__main__":
    app = main()
    app.main_loop()
