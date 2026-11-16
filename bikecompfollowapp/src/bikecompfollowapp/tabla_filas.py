"""
Tabla montada con filas de toga.Box, para poder poner widgets (p. ej. un botón ✏️) dentro de cada fila, cosa
que toga.Table no permite.

Imita lo que la app usaba de toga.Table:
  - `columns`: objetos con `heading` y `accessor`.
  - `data`: lista de filas con un atributo por columna (y por cualquier otro campo de los dicts que se le pasen).
    Admite dicts, tuplas/listas (en el orden de las columnas) u objetos con atributos.
  - `selection`: la fila elegida (None si ninguna); `on_select(tabla)` se llama al elegir una.

Pulsar la cabecera de una columna ordena las filas por esa columna (A→Z / menor a mayor); pulsarla otra vez,
al revés. La cabecera ordenada lleva ▲ o ▼. Los vacíos van siempre al final.

Cada fila: la primera celda es un botón plano (pulsarlo elige la fila, que se resalta); el resto son Labels con
ancho fijo para que las columnas queden alineadas con la cabecera. Opcionalmente, una última columna de
`accion(fila)` que devuelve un widget (o None para dejar la celda vacía).
"""

import logging
import unicodedata
from types import SimpleNamespace

import toga
from toga.colors import rgb
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

ANCHO_COLUMNA = 100
ALTO_FILA = 28
MARGEN_CELDA = 6
ALTO_MAXIMO = None   # sin tope: la tabla ocupa todas sus filas (la pantalla que la contiene hace scroll)
COLOR_FILA_ELEGIDA = rgb(30, 100, 200)     # mismo azul que el botón elegido en Mantenimiento
FLECHA_ASCENDENTE, FLECHA_DESCENDENTE = "▲", "▼"


def clave_orden(valor):
    """Clave para ordenar una celda: números como números ('10' después de '9'), textos sin distinguir
    mayúsculas ni acentos ('Cámara' junto a 'Cadena'). Devuelve None si la celda está vacía."""
    if valor is None or isinstance(valor, bool):
        return None if valor is None else (0, float(valor), "")
    if isinstance(valor, (int, float)):
        return (0, float(valor), "")
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return (0, float(texto.replace(",", ".")), "")
    except ValueError:
        sin_acentos = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
        return (1, 0.0, sin_acentos.casefold())


def ordenar_filas(filas, atributo, descendente=False):
    """Filas ordenadas por `atributo` (orden estable: a igualdad se mantiene el orden anterior). Las vacías,
    siempre al final y en su orden."""
    llenas = [f for f in filas if clave_orden(getattr(f, atributo, None)) is not None]
    vacias = [f for f in filas if clave_orden(getattr(f, atributo, None)) is None]
    return sorted(llenas, key=lambda f: clave_orden(getattr(f, atributo, None)), reverse=descendente) + vacias


class Columna(SimpleNamespace):
    """heading (texto de la cabecera), accessor (atributo de la fila) y ancho."""


class Fila(SimpleNamespace):
    """Una fila de la tabla: un atributo por campo."""


def _boton_plano(boton):
    """En macOS quita el borde del botón para que parezca una celda de texto. En otros backends no hace nada."""
    nativo = getattr(getattr(boton, "_impl", None), "native", None)
    if nativo is None or not type(boton._impl).__module__.startswith("toga_cocoa"):
        return
    try:
        nativo.bordered = False
        nativo.alignment = 0         # NSTextAlignmentLeft
    except Exception as error:       # solo es estética: nunca impide pintar la tabla
        logging.warning("No se pudo aplanar el botón %r: %s", boton.text, error)


class TablaFilas(toga.Box):
    def __init__(self, columnas, data=None, on_select=None, accion=None, titulo_accion="", ancho_accion=50,
                 alto_maximo=ALTO_MAXIMO, style=None):
        """columnas: [(cabecera, atributo) o (cabecera, atributo, ancho)]. accion(fila) -> widget o None.
        alto_maximo: con un número, las filas van en un ScrollContainer de ese alto como mucho. Ojo: en macOS un
        ScrollContainer no hace crecer la ventana, así que es mejor dejarlo en None y que haga scroll la pantalla."""
        super().__init__(style=style or Pack(direction=COLUMN))
        self.style.direction = COLUMN
        self.columns = [Columna(heading=c[0], accessor=c[1], ancho=c[2] if len(c) > 2 else ANCHO_COLUMNA)
                        for c in columnas]
        self.on_select = on_select
        self.accion = accion
        self.titulo_accion = titulo_accion
        self.ancho_accion = ancho_accion
        self.alto_maximo = alto_maximo
        self.selection = None
        self.filas_box = []           # Box de cada fila, en el orden de data
        self._data = []
        self.orden = None             # (atributo, descendente) de la columna por la que se ha ordenado

        self.cabecera = toga.Box(style=Pack(direction=ROW, margin_bottom=2))
        self.botones_cabecera = []
        for n, columna in enumerate(self.columns):
            # Cada cabecera es un botón plano que ordena por su columna. Mismo margen que las celdas: la primera
            # (botón) sin margen, el resto con MARGEN_CELDA
            boton = toga.Button(columna.heading, on_press=lambda w, c=columna: self.ordenar_por(c.accessor),
                                style=Pack(width=columna.ancho, font_weight="bold",
                                           margin_left=MARGEN_CELDA if n else 0))
            _boton_plano(boton)
            boton.columna = columna
            self.botones_cabecera.append(boton)
            self.cabecera.add(boton)
        if self.accion is not None:
            self.cabecera.add(toga.Label(titulo_accion, style=Pack(width=ancho_accion, font_weight="bold",
                                                                   text_align=CENTER)))
        self.cuerpo = toga.Box(style=Pack(direction=COLUMN))
        self.add(self.cabecera)
        self.add(toga.Divider())
        if alto_maximo is None:
            self.scroll = None
            self.add(self.cuerpo)
        else:
            self.scroll = toga.ScrollContainer(content=self.cuerpo, horizontal=False, style=Pack(height=ALTO_FILA))
            self.add(self.scroll)
        self.data = data or []

    # ---- datos ----
    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, filas):
        self._data = [self._a_fila(f) for f in (filas or [])]
        if self.orden is not None:     # datos nuevos: se mantiene el orden elegido por el usuario
            self._data = ordenar_filas(self._data, *self.orden)
        self.selection = None
        self._pintar_filas()

    # ---- orden por columnas ----
    def ordenar_por(self, atributo):
        """Ordena por la columna `atributo`: la primera vez ascendente; si ya lo estaba, descendente (y al
        revés). Se mantiene la fila elegida."""
        descendente = self.orden == (atributo, False)
        self.orden = (atributo, descendente)
        self._data = ordenar_filas(self._data, atributo, descendente)
        elegida = self.selection
        self._pintar_filas()
        self._pintar_cabecera()
        if elegida is not None:
            self._resaltar(elegida)
        logging.debug("Tabla ordenada por %s (%s)", atributo, "desc" if descendente else "asc")

    def _pintar_cabecera(self):
        for boton in self.botones_cabecera:
            texto = boton.columna.heading
            if self.orden is not None and self.orden[0] == boton.columna.accessor:
                texto = f"{texto} {FLECHA_DESCENDENTE if self.orden[1] else FLECHA_ASCENDENTE}"
            boton.text = texto

    def _a_fila(self, fila):
        if isinstance(fila, Fila):
            return fila
        if isinstance(fila, dict):
            return Fila(**fila)
        if isinstance(fila, (tuple, list)):
            return Fila(**{c.accessor: v for c, v in zip(self.columns, fila)})
        return Fila(**{c.accessor: getattr(fila, c.accessor, None) for c in self.columns})

    @staticmethod
    def texto(valor):
        return "" if valor is None else str(valor)

    def _pintar_filas(self):
        for hijo in list(self.cuerpo.children):
            self.cuerpo.remove(hijo)
        self.filas_box = []
        for fila in self._data:
            caja = toga.Box(style=Pack(direction=ROW, height=ALTO_FILA, align_items=CENTER))
            for n, columna in enumerate(self.columns):
                texto = self.texto(getattr(fila, columna.accessor, None))
                if n == 0:   # la primera celda elige la fila
                    celda = toga.Button(texto, on_press=lambda w, f=fila: self.elegir(f),
                                        style=Pack(width=columna.ancho))
                    _boton_plano(celda)
                else:
                    celda = toga.Label(texto, style=Pack(width=columna.ancho, margin_left=MARGEN_CELDA))
                caja.add(celda)
            if self.accion is not None:
                widget = self.accion(fila)
                celda = toga.Box(style=Pack(width=self.ancho_accion, direction=ROW, justify_content=CENTER))
                if widget is not None:
                    celda.add(widget)
                caja.add(celda)
            caja.fila = fila
            self.filas_box.append(caja)
            self.cuerpo.add(caja)
        if not self._data:   # sin filas: una vacía para que la tabla no se quede sin alto
            self.cuerpo.add(toga.Box(style=Pack(height=ALTO_FILA)))
        if self.scroll is not None:
            self.scroll.style.height = min(ALTO_FILA * max(len(self._data), 1) + 2, self.alto_maximo)

    # ---- selección ----
    def elegir(self, fila):
        """Elige la fila (se resalta) y avisa con on_select."""
        self._resaltar(fila)
        if self.on_select is not None:
            self.on_select(self)

    def _resaltar(self, fila):
        self.selection = fila
        for caja in self.filas_box:
            elegida = caja.fila is fila
            if elegida:
                caja.style.background_color = COLOR_FILA_ELEGIDA
            else:
                del caja.style.background_color
            for celda in caja.children:
                if isinstance(celda, toga.Label):
                    if elegida:
                        celda.style.color = "#FFFFFF"
                    else:
                        del celda.style.color
