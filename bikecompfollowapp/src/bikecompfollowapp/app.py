""""""""""
App to follow up bike comp, sneakers and car comp to avoid breaks.
"""""""""""

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW, LEFT
from toga.colors import rgb
from toga.sources import AccessorColumn

from pathlib import Path
import sys
import sqlite3
import logging
from datetime import datetime

if __name__ == "__main__" or __package__ is None:
    import notificaciones
    import stravaConnect
    import translations
else:
    from . import notificaciones, stravaConnect, translations
t = translations.t
import asyncio

# ---- Medidas de interfaz (Toga trabaja en píxeles; 1 cm ≈ 38 px a 96 ppp) ----
ANCHO_CAMPO = 250
ANCHO_BOTONES_MENU = 320
ALTO_ESTADISTICAS = 130      # ≈ 3,5 cm
ALTO_MANTENIMIENTO = 260     # el doble ≈ 7 cm
ESPACIO = 10                 # separación entre botones

DISTANCIA_LIMITE_DEFECTO = 5000
TIEMPO_LIMITE_DEFECTO = 500
ELEMENTOS_POR_DEFECTO = ["Cadena", "Pastillas Freno", "Cubiertas"]

# Columnas de las tablas de la pantalla Estadísticas: (clave de traducción de la cabecera, atributo de la fila)
COLUMNAS_COMPONENTES = [
    ("col.componente", "elemento"), ("col.descripcion", "descripcion"), ("col.fecha", "fechaInsercion"),
    ("col.km_max", "distanciaLimite"), ("col.km_desde_alta", "distanciaDesdeInsercion"),
    ("col.tiempo", "tiempoLimite"), ("col.activo", "activo"),
]
COLUMNAS_LIMITES = [("col.componente", "componente"), ("col.tipo_limite", "tipo_limite"), ("col.valor", "valor")]

# Tipos de límite tal y como se guardan en LimitesAlerta -> clave del texto que se muestra
TIPOS_LIMITE = {"superior": "alerta.superior", "inferior": "alerta.inferior"}


def _columnas(definicion):
    return [AccessorColumn(t(clave), atributo) for clave, atributo in definicion]


# Datos con los que se siembra una BD nueva
VEHICULOS_INICIALES = ["Coche", "Bici Carretera", "Bici Gravel", "Bici MTB", "Tractor"]
ELEMENTOS_INICIALES = [
    "cadena", "pastillas freno", "Cubierta", "Cinta Manillar", "Piñonera",
    "Plato", "Cambio Trasero", "Líquido Frenos", "Maneta Cambio", "Cámara",
]

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

class BikeCompFollowApp(toga.App):
    label_estado = ""
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
    def lanzarNotificacion(self, titulo=None, mensaje=None) -> bool:
        return notificaciones.notificar(titulo or t("notificacion.titulo"), mensaje or t("notificacion.fin"))

    def crearDBBasica(self):
        try:
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS datos (id integer PRIMARY KEY, fecha Date, datos text NOT NULL, km integer NOT NULL, activo BOOLEAN NOT NULL)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS Elemento (id INTEGER PRIMARY KEY,nombre TEXT)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS stravaValores  (id integer PRIMARY KEY,  fecha date not NULL, valor INTEGER not NULL,  ascenso INTEGER, tipo TEXT not null, num_actividades INTEGER, horas INTEGER)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS EntradasUsers (id integer PRIMARY KEY,  fecha Date,  nombre text NOT NULL,  usuario text,  tipov integer NOT NULL, descripcion  TEXT NOT NULL, FOREIGN KEY (tipov) REFERENCES tipo_vehiculo(id))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS linked_elements (id integer PRIMARY KEY, fecha Date, Entrada_num integer, num_elemento, FOREIGN KEY (Entrada_num) REFERENCES EntradasUsers(id), FOREIGN KEY (num_Elemento) REFERENCES Elemento(id))""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS tipo_vehiculo (id	INTEGER PRIMARY KEY,vehiculo TEXT)""")
            self.cursor.execute("""CREATE TABLE IF NOT EXISTS archivoscomponentes (id INTEGER PRIMARY KEY, usuario NOT NULL, elemento TEXT NOT NULL, descripcion TEXT, marca TEXT, fechaInsercion Date NOT NULL, distanciaLimite integer, tiempoLimite integer, activo BOOLEAN DEFAULT True)""")
        except sqlite3.Error as error:
            logging.error("Error al crear Tablas en SQLite: %s", error)
            logging.error("Tablas ya existen en SQLite")
        finally:
            logging.info('Tablas DB creadas')
            self.sqliteConnection.commit()

        # Carga de los datos básicos
        try:
            self.cursor.executemany("INSERT INTO tipo_vehiculo (vehiculo) VALUES (?)", [(v,) for v in VEHICULOS_INICIALES])
            self.cursor.executemany("INSERT INTO Elemento (nombre) VALUES (?)", [(e,) for e in ELEMENTOS_INICIALES])
            self.sqliteConnection.commit()
            logging.info('Carga de datos básicos (tipo_vehiculo, Elemento) correcta.')
        except sqlite3.Error as error:
            logging.error("Error al cargar datos de las Tablas Básicas en SQLite: %s", error)

    def arrancarDB(self):
        # Obtener la ruta del directorio actual del script
        
        self.db_path = AppPaths.get("data", "BikeCFU", "dbbcfu.db")

        # Esto crea el fichero si no existe
        self.sqliteConnection = sqlite3.connect(self.db_path)
        self.cursor = self.sqliteConnection.cursor()

        print("DB DIR:", self.db_path)
        
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
            style=Pack(height=ALTO_ESTADISTICAS, background_color="#FF8C00", **estilo_comun),
        )
        self.boton_mantenimiento = toga.Button(
            t("menu.mantenimiento"),
            on_press=lambda widget: self.ir_a_mantenimiento(PANTALLA_MANTENIMIENTO),
            style=Pack(height=ALTO_MANTENIMIENTO, background_color="#1E64C8", **estilo_comun),
        )

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
            "SELECT nombre FROM Elemento ORDER BY nombre",
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

        self.label_pantalla_dos = toga.Label(
            t("menu.usuario", usuario=valor),
            style=Pack(margin_bottom=20, text_align=CENTER)
        )

        try:
            data = self.sqliteConnection.execute(
                "SELECT elemento, descripcion, fechaInsercion, distanciaLimite, 'x', tiempoLimite, activo "
                "FROM archivoscomponentes WHERE usuario = ?",
                (valor,),
            ).fetchall()
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
                self.label_pantalla_dos,
                self.tabla,
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

    def ir_a_pantalla_tres(self, widget, valor):
        self._mostrar(self.construir_pantalla_tres(valor))

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
    def anadirComponente(self, valor1, user, valor2, valor3, valor4, valor5=None, valor6=None):
        logging.info("Dentro añadir Componente.")

        distancia = (getattr(valor5, "value", None) or "").strip() or DISTANCIA_LIMITE_DEFECTO
        tiempo = (getattr(valor6, "value", None) or "").strip() or TIEMPO_LIMITE_DEFECTO
        f = (valor1.value or "").strip() or datetime.today().strftime("%Y-%m-%d")

        try:
            self.sqliteConnection.execute(
                "INSERT INTO archivoscomponentes (fechaInsercion, usuario, elemento, descripcion, marca, distanciaLimite, tiempoLimite) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f, user, valor2.value, valor3.value, valor4.value, distancia, tiempo)
            )
            self.sqliteConnection.commit()
        except sqlite3.Error as error:
            logging.error("Error al insertar en archivoscomponentes: %s", error)
            self._mostrar_estado(self.label_pantalla_dos, t("estado.componente_error"), ok=False)
            return False
        self._mostrar_estado(self.label_pantalla_dos, t("estado.entrada_ok"))
        logging.info("Componente cargado correctamente.")
        return True

    def cargar_componente(self, entrada_fecha, usuarioSeleccionado, selection_elemento, descripcion_texto, marca_texto, distancialim_texto, tiempolim_texto) -> bool:
        return self.anadirComponente(entrada_fecha, usuarioSeleccionado, selection_elemento, descripcion_texto, marca_texto, distancialim_texto, tiempolim_texto)

    # -------- Pantalla 5 (alta de componente) --------
    def construir_pantalla_cinco(self, valor, elemento=None, volver=None):
        """Alta de componente. `elemento` lo preselecciona; `volver` es la pantalla de retorno."""
        tipos_elemento = self._leer_lista(
            "SELECT nombre FROM Elemento ORDER BY nombre",
            por_defecto=ELEMENTOS_POR_DEFECTO,
        )
        if elemento:
            coincidencia = next((e for e in tipos_elemento if e.casefold() == elemento.casefold()), None)
            if coincidencia is None:
                tipos_elemento.insert(0, elemento)
                coincidencia = elemento
            elemento = coincidencia

        self.label_pantalla_dos = toga.Label(
            t("componente.titulo", usuario=valor),
            style=Pack(margin_bottom=20, text_align=CENTER)
        )
        self.entrada_fecha = self._texto(t("campo.fecha_placeholder"), value=datetime.today().strftime("%Y-%m-%d"))
        self.selection_elemento = toga.Selection(items=tipos_elemento, style=Pack(width=ANCHO_CAMPO))
        if elemento:
            self.selection_elemento.value = elemento
        self.descripcion_texto = self._texto()
        self.marca_texto = self._texto()
        self.distancialim_texto = self._texto()
        self.tiempolim_texto = self._texto()

        contenido_box = self._formulario()
        contenido_box.add(self.label_pantalla_dos)
        contenido_box.add(self._campo(t("campo.fecha"), self.entrada_fecha))
        contenido_box.add(self._campo(t("campo.elemento"), self.selection_elemento))
        contenido_box.add(self._campo(t("campo.descripcion"), self.descripcion_texto))
        contenido_box.add(self._campo(t("campo.marca"), self.marca_texto))
        contenido_box.add(self._campo(t("campo.distancia_limite"), self.distancialim_texto))
        contenido_box.add(self._campo(t("campo.tiempo_limite"), self.tiempolim_texto))
        contenido_box.add(self._boton(t("comun.cargar"), lambda widget: self.cargar_componente(
            self.entrada_fecha, self.usuarioSeleccionado, self.selection_elemento, self.descripcion_texto,
            self.marca_texto, self.distancialim_texto, self.tiempolim_texto,
        )))

        volver = volver or (lambda: self.ir_a_pantalla_tres(None, valor))
        return self._pantalla(contenido_box, self._barra_inferior(izquierda=self._boton_volver(volver)))

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
        fila = self.cursor.execute(
            """SELECT COALESCE(tv.vehiculo, eu.tipov) FROM EntradasUsers eu
               LEFT JOIN tipo_vehiculo tv ON tv.id = eu.tipov
               WHERE eu.usuario = ? ORDER BY eu.id DESC LIMIT 1""",
            (usuario,),
        ).fetchone()
        return None if fila is None or fila[0] is None else str(fila[0])

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
    def iniciar_tarea(self, widget):
        # Se guarda la referencia para que el recolector de basura no cancele la tarea
        self._tarea_sync = asyncio.create_task(self.tarea_larga())

    async def tarea_larga(self, widget=None):
        for i in range(1, self.total + 1):
            await asyncio.sleep(0.3)
            self.progress.value = i
            self.label.text = t("strava.procesando", actual=i, total=self.total)
        # Aviso al terminar (antes se lanzaba al empezar la tarea)
        self.lanzarNotificacion()

    def recolectarDatosStrava(self, widget):
        datosStrava = stravaConnect.StravaData(self)
        datosStrava.initConexion()
        datosStrava.crearObjetoCliente()
        datosStrava.extraerDatos(datetime(2025, 12, 31), datetime.now())
        datosStrava.guardarDatosBDD(datetime.now())
        datosStrava.guardarActividadesBDD(self.usuarioSeleccionado, self.vehiculoDelUsuario(self.usuarioSeleccionado))

    def ir_a_pantalla_recoleccionDatos(self, widget=None):
        self._mostrar(self.barraProgresoCargaDatos())

    def barraProgresoCargaDatos(self):
        self.total = 20

        self.label = toga.Label(t("strava.pulsa_inicio"), style=Pack(margin=10))
        self.progress = toga.ProgressBar(max=self.total, value=0, style=Pack(margin=10))

        box = toga.Box(style=Pack(direction=COLUMN, margin=20))
        box.add(self.label)
        box.add(self.progress)
        box.add(self._boton(t("strava.iniciar"), self.iniciar_tarea))
        box.add(self._boton(t("strava.extraer"), self.recolectarDatosStrava))
        box.add(self._barra_inferior(izquierda=self._boton_volver(self.ir_a_menu_usuario)))
        return box

def main():
    # Nombre visible y ID de la app (ajústalo a tu dominio)
    return BikeCompFollowApp("Bike Comp Follow App", "com.SkullWithGasMask", icon="resources/icon.png")

if __name__ == "__main__":
    app = main()
    app.main_loop()
