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
import logging
from datetime import date, datetime, time
import asyncio

if __name__ == "__main__" or __package__ is None:
    import DB_Operations as dbops
    import notificaciones
    import stravaConnect
    import translations
else:
    from . import DB_Operations as dbops
    from . import notificaciones, stravaConnect, translations
t = translations.t

# ---- Medidas de interfaz (Toga trabaja en píxeles; 1 cm ≈ 38 px a 96 ppp) ----
ANCHO_CAMPO = 250
ANCHO_BOTONES_MENU = 320
ALTO_ESTADISTICAS = 130      # ≈ 3,5 cm
ALTO_MANTENIMIENTO = 260     # el doble ≈ 7 cm
ESPACIO = 10                 # separación entre botones

AZUL = rgb(0, 102, 204)
COLOR_ESTADISTICAS = "#FF8C00"
# Ventana de Alerta (componentes a cambiar de manera urgente)
ROJO_ALERTA = rgb(220, 0, 0)
TAMANO_TITULO_ALERTA = 24
TAMANO_VENTANA_ALERTA = (420, 260)

COLOR_MANTENIMIENTO = "#1E64C8"

# Pantalla previa a Mantenimiento: cuándo es el paso por taller y con qué bici
MECANICO_HOY, MECANICO_EN_FECHA = "hoy", "fecha"
MODALIDADES_MANTENIMIENTO = ("Road", "MTB", "Gravel")      # valores de ActividadesStrava.Modalidad
ALTO_BOTON_PREPARACION = 90
COLOR_SELECCIONADO = COLOR_MANTENIMIENTO                     # fondo del botón elegido

# Componentes de prueba para la ventana de Alerta del menú del usuario (ver componentesUrgentes)
COMPONENTES_URGENTES_PRUEBA = ["Cadena", "Pastillas de Freno"]

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


class BikeCompFollowApp(toga.App):
    label_estado = ""
    cursor = None
    sqliteConnection = 0
    index_entrada = 0
    db_path = None
    log_path = None
    usuarioSeleccionado = None
    sync_strava_en_curso = False

    @property
    def db(self):
        """Operaciones de BD (DB_Operations.BaseDatos) sobre la conexión actual de la app."""
        bd = getattr(self, "_db", None)
        if bd is None or bd.conexion is not self.sqliteConnection:
            bd = self._db = dbops.BaseDatos(self.sqliteConnection)
        return bd

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
        self.db.prepararTablas()
        self.cargarIdioma()

        # Pantalla inicial al arrancar
        self.main_window.content = self.construir_pantalla_inicial()
        self.main_window.show()

    # Método para borrar datos en cascada.
    def borrarDatosDB(self):
        logging.info("Dentro borrar Datos")

    # Método para lanzar Notificaciones
    def lanzarNotificacion(self, titulo, mensaje) -> bool:
        return notificaciones.notificar(titulo, mensaje)

    def arrancarDB(self):
        """Abre la BD de la app (la crea y siembra si es nueva). Ver DB_Operations.BaseDatos."""
        self.db_path = AppPaths.get("data", "BikeCFU", "dbbcfu.db")
        self._db = dbops.BaseDatos.abrir(self.db_path)
        self.sqliteConnection = self._db.conexion
        self.cursor = self._db.cursor

    # -------- Idioma --------
    def cargarIdioma(self):
        """Carga el XML de textos y aplica el idioma guardado (castellano si no hay ninguno)."""
        translations.load()
        translations.set_language(self.db.leerAjuste("idioma", translations.current().code))

    def cambiarIdioma(self, widget=None):
        """Botón de la bandera: pasa al siguiente idioma, lo guarda y redibuja la pantalla."""
        idioma = translations.next_language()
        translations.set_language(idioma.code)
        if not self.db.guardarAjuste("idioma", idioma.code):
            logging.error("No se pudo guardar el idioma %s; solo se aplica a esta sesión", idioma.code)
        self.volver_pantalla_inicial()

    # -------- Utilidades comunes de interfaz --------
    def _mostrar(self, contenido):
        self.main_window.content = contenido

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

        for nombre, usuario in self.db.usuarios():
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
            on_press=self.ir_a_preparacion_mantenimiento,
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
        if self.preparacion_completa():
            self.label_preparacion = toga.Label(
                t("preparacion.resumen", modalidad=self.modalidad_mantenimiento.upper(),
                  fecha=self.fecha_mecanico.isoformat()),
                style=Pack(margin_bottom=ESPACIO, color=AZUL))
            contenido.add(self.label_preparacion)
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
            self.volver_a_preparacion_mantenimiento()
        else:
            self.ir_a_mantenimiento(anterior)

    # -------- Pantalla previa a Mantenimiento: MECÁNICO HOY / EN FECHA + ROAD / MTB / GRAVEL --------
    def ir_a_preparacion_mantenimiento(self, widget=None):
        """Desde el menú: se empieza sin nada elegido."""
        self.mecanico = None
        self.fecha_mecanico = date.today()
        self.modalidad_mantenimiento = None
        self._mostrar(self.construir_preparacion_mantenimiento())

    def volver_a_preparacion_mantenimiento(self):
        """Desde la cuadrícula de componentes: se conserva lo elegido."""
        self._mostrar(self.construir_preparacion_mantenimiento())

    def construir_preparacion_mantenimiento(self):
        """Arriba MECÁNICO HOY / MECÁNICO EN FECHA (este muestra un selector de fecha); abajo ROAD / MTB / GRAVEL.
        Continuar solo se activa con un botón elegido arriba y otro abajo."""
        mecanico = getattr(self, "mecanico", None)
        modalidad = getattr(self, "modalidad_mantenimiento", None)

        def boton(texto, elegido, accion):
            estilo = dict(flex=1, height=ALTO_BOTON_PREPARACION, font_size=16, font_weight="bold")
            if elegido:
                estilo.update(background_color=COLOR_SELECCIONADO, color="#FFFFFF")
            b = toga.Button(texto, on_press=accion, style=Pack(**estilo))
            if elegido:
                pintar_fondo_boton(b, COLOR_SELECCIONADO)
            return b

        def fila(botones):
            caja = toga.Box(style=Pack(direction=ROW))
            for i, b in enumerate(botones):
                if i:
                    caja.add(toga.Box(style=Pack(width=ESPACIO)))
                caja.add(b)
            return caja

        self.boton_mecanico_hoy = boton(t("preparacion.hoy"), mecanico == MECANICO_HOY,
                                        lambda w: self.elegir_mecanico(MECANICO_HOY))
        self.boton_mecanico_fecha = boton(t("preparacion.en_fecha"), mecanico == MECANICO_EN_FECHA,
                                          lambda w: self.elegir_mecanico(MECANICO_EN_FECHA))
        # Cada botón de arriba va en su columna: el selector de fecha sale justo debajo de MECÁNICO EN FECHA
        columna_hoy = toga.Box(children=[self.boton_mecanico_hoy], style=Pack(direction=COLUMN, flex=1))
        self.columna_mecanico_fecha = toga.Box(children=[self.boton_mecanico_fecha], style=Pack(direction=COLUMN, flex=1))
        self.selector_fecha_mecanico = None
        if mecanico == MECANICO_EN_FECHA:
            self.selector_fecha_mecanico = toga.DateInput(
                value=self.fecha_mecanico, on_change=self.cambiar_fecha_mecanico, style=Pack(margin_left=10))
            self.columna_mecanico_fecha.add(toga.Box(
                children=[toga.Label(t("preparacion.fecha")), self.selector_fecha_mecanico],
                style=Pack(direction=ROW, align_items=CENTER, justify_content=CENTER, margin_top=ESPACIO)))
        arriba = toga.Box(children=[
            toga.Label(t("preparacion.cuando"), style=Pack(font_size=16, margin_bottom=ESPACIO)),
            fila([columna_hoy, self.columna_mecanico_fecha]),
        ], style=Pack(direction=COLUMN))

        self.botones_modalidad = {
            m: boton(m.upper(), modalidad == m, lambda w, m=m: self.elegir_modalidad_mantenimiento(m))
            for m in MODALIDADES_MANTENIMIENTO
        }
        abajo = toga.Box(children=[
            toga.Label(t("preparacion.modalidad"), style=Pack(font_size=16, margin_bottom=ESPACIO)),
            fila(list(self.botones_modalidad.values())),
        ], style=Pack(direction=COLUMN))

        contenido = toga.Box(children=[
            toga.Label(t("menu.mantenimiento"), style=Pack(font_size=16, margin_bottom=20)),
            arriba,
            toga.Box(style=Pack(height=40)),
            abajo,
        ], style=Pack(direction=COLUMN))

        self.boton_continuar_mantenimiento = self._boton(t("preparacion.continuar"), self.continuar_a_mantenimiento)
        self.boton_continuar_mantenimiento.enabled = self.preparacion_completa()
        return self._pantalla(contenido, self._barra_inferior(
            izquierda=self._boton_volver(self.ir_a_menu_usuario),
            derecha=self.boton_continuar_mantenimiento,
        ))

    def preparacion_completa(self):
        return getattr(self, "mecanico", None) is not None and getattr(self, "modalidad_mantenimiento", None) is not None

    def elegir_mecanico(self, mecanico):
        self.mecanico = mecanico
        if mecanico == MECANICO_HOY:
            self.fecha_mecanico = date.today()
        self.volver_a_preparacion_mantenimiento()

    def cambiar_fecha_mecanico(self, widget=None):
        self.fecha_mecanico = self.selector_fecha_mecanico.value or date.today()

    def elegir_modalidad_mantenimiento(self, modalidad):
        self.modalidad_mantenimiento = modalidad
        self.volver_a_preparacion_mantenimiento()

    def continuar_a_mantenimiento(self, widget=None):
        if not self.preparacion_completa():      # el botón está desactivado; por si acaso
            return
        if self.mecanico == MECANICO_EN_FECHA and self.selector_fecha_mecanico is not None:
            self.fecha_mecanico = self.selector_fecha_mecanico.value or date.today()
        logging.info("Mantenimiento (%s): mecánico %s el %s, modalidad %s", self.usuarioSeleccionado,
                     self.mecanico, self.fecha_mecanico, self.modalidad_mantenimiento)
        self.ir_a_mantenimiento(PANTALLA_MANTENIMIENTO)

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
                fecha=getattr(self, "fecha_mecanico", None),
            ))

    # -------- Pantalla 2 (alta de usuario / vehículo) --------
    def ir_a_pantalla_dos(self, widget=None):
        self._mostrar(self.construir_pantalla_dos())

    def construir_pantalla_dos(self):
        tipos_vehiculo = self.db.tiposVehiculo(por_defecto=["Carretera", "Montaña", "Híbrida"])
        tipos_elemento = self.db.nombresComponentes(por_defecto=ELEMENTOS_POR_DEFECTO)

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

        if not self.db.insertarEntrada(f, texto1, textoUser, tipov, texto2):
            self._mostrar_estado(self.label_pantalla_dos, t("estado.entrada_error"), ok=False)
            return
        self._mostrar_estado(self.label_pantalla_dos, t("estado.entrada_ok"))

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
            data = [(*fila[:-1], texto_activo(fila[-1])) for fila in self.db.componentesEstadisticas(valor)]
            logging.info("Datos de TABLA LEÍDOS correctamente.")
        except sqlite3.Error as error:
            logging.error("Error al leer la tabla de componentes de Estadísticas: %s", error)
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
        self.anios_estadisticas = dbops.aniosEstadisticas()
        try:
            self.filas_modalidad, self.anios_sin_datos = self.db.kmsHorasPorModalidad(valor, self.anios_estadisticas)
        except sqlite3.Error as error:
            logging.error("Error al leer los km y horas por modalidad: %s", error)
            self.filas_modalidad = [(m, None) + (0.0, 0.0) * len(self.anios_estadisticas)
                                    for m in dbops.MODALIDADES_ESTADISTICAS]
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
        self.tablaLimites.data = self.db.seleccionarLimitesComponente(componente) if componente else []

    def anadirComponente(self, valor1, user, valor2, valor3, valor4, valor5=None, valor6=None, valor7=None):
        """valor5/6/7: km, horas y meses límite. Si se dejan vacíos se usan los del componente."""
        logging.info("Dentro añadir Componente.")

        km_defecto, horas_defecto, meses_defecto = self.db.limitesComponente(valor2.value, user)
        distancia = (getattr(valor5, "value", None) or "").strip() or km_defecto
        tiempo = (getattr(valor6, "value", None) or "").strip() or horas_defecto
        meses = (getattr(valor7, "value", None) or "").strip() or meses_defecto
        f = (valor1.value or "").strip() or datetime.today().strftime("%Y-%m-%d")

        if not self.db.guardarComponente(f, user, valor2.value, valor3.value, valor4.value, distancia, tiempo, meses):
            self._mostrar_estado(self.label_pantalla_dos, t("estado.componente_error"), ok=False)
            return False
        self._mostrar_estado(self.label_pantalla_dos, t("estado.entrada_ok"))
        return True

    def cargar_componente(self, entrada_fecha, usuarioSeleccionado, selection_elemento, descripcion_texto, marca_texto, distancialim_texto, tiempolim_texto, meseslim_texto=None) -> bool:
        return self.anadirComponente(entrada_fecha, usuarioSeleccionado, selection_elemento, descripcion_texto, marca_texto, distancialim_texto, tiempolim_texto, meseslim_texto)

    # -------- Pantalla 5 (alta de componente) --------
    def construir_pantalla_cinco(self, valor, elemento=None, volver=None, fecha=None):
        """Alta de componente. `elemento` lo preselecciona; `volver` es la pantalla de retorno."""
        tipos_elemento = self.db.nombresComponentes(por_defecto=ELEMENTOS_POR_DEFECTO)
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
        fecha_alta = fecha.isoformat() if fecha else datetime.today().strftime("%Y-%m-%d")
        self.entrada_fecha = self._texto(t("campo.fecha_placeholder"), value=fecha_alta)
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
        km, horas, meses = self.db.limitesComponente(
            self.selection_elemento.value, getattr(self, "usuario_alta_componente", None))
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
            for tipo in self.db.tiposLimiteUsados(por_defecto=list(TIPOS_LIMITE))
        ]

        componentes_disponibles = list(componentes or [])
        if not componentes_disponibles and self.usuarioSeleccionado is not None:
            componentes_disponibles = self.db.elementosDeUsuario(self.usuarioSeleccionado)
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
            ok = self.db.insertarLimiteAlerta(tipo_alerta, valor_limite, compo)

        self.label_estado = "✅" if ok else "❌"
        self.label_pantalla_LimiteNuevaAlerta.text += self.label_estado
        return ok

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
                dbops.calcularKmComponentes(datos.sqliteConnection, usuario)
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
        vehiculo = self.db.vehiculoDelUsuario(usuario)
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
