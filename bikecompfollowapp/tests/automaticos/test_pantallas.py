"""Tests de navegación entre pantallas (backend toga_dummy, sin ventanas reales)."""

from types import SimpleNamespace

import pytest
import toga
from toga.colors import rgb

from datetime import date

from bikecompfollowapp import DB_Operations as dbops
from bikecompfollowapp import app as modulo_app
from bikecompfollowapp import translations
from bikecompfollowapp.translations import t
from bikecompfollowapp.DB_Operations import orden_alfabetico
from bikecompfollowapp.app import (
    AZUL,
    PANTALLA_MANTENIMIENTO,
    PANTALLAS_MANTENIMIENTO,
    SUBPANTALLAS_MANTENIMIENTO,
    texto_activo,
)

USUARIO = "DaMario Bros"


# ---- Utilidades para recorrer y pulsar widgets ----

def widgets(raiz, tipo=None):
    """Todos los widgets descendientes de `raiz` (incluida), opcionalmente filtrados por tipo."""
    pendientes, encontrados = [raiz], []
    while pendientes:
        w = pendientes.pop(0)
        if tipo is None or isinstance(w, tipo):
            encontrados.append(w)
        pendientes.extend(getattr(w, "children", None) or [])
    return encontrados


def textos_botones(raiz):
    return [b.text for b in widgets(raiz, toga.Button)]


def boton(raiz, texto):
    candidatos = [b for b in widgets(raiz, toga.Button) if b.text == texto]
    assert candidatos, f"No hay botón '{texto}' en la pantalla. Botones: {textos_botones(raiz)}"
    return candidatos[0]


def pulsar(ui, texto):
    boton(ui.main_window.content, texto)._impl.simulate_press()
    return ui.main_window.content


def textos_labels(raiz):
    return [label.text for label in widgets(raiz, toga.Label)]


def barra_inferior(pantalla):
    return pantalla.children[-1]


@pytest.fixture
def con_usuario(ui, db):
    db.execute(
        "INSERT INTO EntradasUsers (fecha, nombre, usuario, tipov, descripcion) "
        "VALUES ('2026-10-01', 'Damián Vega', ?, 'Bici Carretera', 'Bici')",
        (USUARIO,),
    )
    ui.sqliteConnection.commit()
    ui.volver_pantalla_inicial()
    return ui


@pytest.fixture
def en_menu(con_usuario):
    pulsar(con_usuario, f"{USUARIO}-Damián Vega")
    return con_usuario


# ---- Pantalla inicial ----

def test_pantalla_inicial_sin_boton_strava(con_usuario):
    botones = textos_botones(con_usuario.main_window.content)
    assert "Strava Sync" not in botones
    assert "+ Usuario" in botones
    assert f"{USUARIO}-Damián Vega" in botones


def test_pantalla_inicial_usuario_sin_alias(ui, db):
    db.execute("INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) VALUES ('Lucía', NULL, 1, '')")
    ui.volver_pantalla_inicial()
    assert "-Lucía" in textos_botones(ui.main_window.content)


def test_usuario_abre_menu(en_menu):
    pantalla = en_menu.main_window.content
    assert en_menu.usuarioSeleccionado == USUARIO
    assert f"Usuario: {USUARIO}" in textos_labels(pantalla)
    assert {"Estadísticas", "Mantenimiento / Paso por taller", "Strava Sync", "◀ Volver"} <= set(textos_botones(pantalla))


def test_mas_usuario_abre_alta_y_vuelve(con_usuario):
    pantalla = pulsar(con_usuario, "+ Usuario")
    assert "Nueva Entrada" in textos_labels(pantalla)
    pantalla = pulsar(con_usuario, "◀ Volver")
    assert "+ Usuario" in textos_botones(pantalla)


# ---- Menú del usuario ----

def test_menu_volver_abajo_izquierda_y_strava_sync_a_la_derecha(en_menu):
    barra = barra_inferior(en_menu.main_window.content)
    assert isinstance(barra.children[0], toga.Button)
    assert barra.children[0].text == "◀ Volver"
    assert isinstance(barra.children[-1], toga.Button)
    assert barra.children[-1].text == "Strava Sync"


def test_menu_tamano_botones(en_menu):
    pantalla = en_menu.main_window.content
    estadisticas = boton(pantalla, "Estadísticas")
    mantenimiento = boton(pantalla, "Mantenimiento / Paso por taller")
    assert mantenimiento.style.height == 2 * estadisticas.style.height
    assert mantenimiento.style.width == estadisticas.style.width


def test_menu_volver_a_inicial(en_menu):
    pantalla = pulsar(en_menu, "◀ Volver")
    assert "Selecciona el usuario" in textos_labels(pantalla)


def test_estadisticas_abre_tabla_componentes(en_menu):
    pantalla = pulsar(en_menu, "Estadísticas")
    assert en_menu.tabla in widgets(pantalla)
    assert {"+ Componente", "+ Límite Alerta"} <= set(textos_botones(pantalla))


def test_estadisticas_volver_a_menu(en_menu):
    pulsar(en_menu, "Estadísticas")
    pantalla = pulsar(en_menu, "◀ Volver")
    assert "Estadísticas" in textos_botones(pantalla)


def test_strava_sync_abre_sincronizacion_y_vuelve_a_menu(en_menu):
    pantalla = pulsar(en_menu, "Strava Sync")
    assert "Extraer Datos Strava" in textos_botones(pantalla)
    assert "Iniciar" not in textos_botones(pantalla)
    assert widgets(pantalla, toga.DateInput)
    pantalla = pulsar(en_menu, "◀ Volver")
    assert "Mantenimiento / Paso por taller" in textos_botones(pantalla)


# ---- Pantallas de mantenimiento ----

def test_mantenimiento_muestra_cuadricula(en_menu):
    pantalla = pulsar(en_menu, "Mantenimiento / Paso por taller")
    filas = PANTALLAS_MANTENIMIENTO[PANTALLA_MANTENIMIENTO][1]
    esperados = [t(clave) for fila in filas for clave in fila]
    assert [texto for texto in textos_botones(pantalla) if texto != "◀ Volver"] == esperados


@pytest.mark.parametrize("ruta, clave", [
    (["Otros"], "componentes"),
    (["Otros", "Otros"], "otros"),
    (["Otros", "RODAMIENTOS"], "rodamientos"),
    (["Otros", "TUBELESS"], "tubeless"),
])
def test_navegacion_subpantallas(en_menu, ruta, clave):
    pulsar(en_menu, "Mantenimiento / Paso por taller")
    for texto in ruta:
        pantalla = pulsar(en_menu, texto)

    titulo, filas, alto, _ = PANTALLAS_MANTENIMIENTO[clave]
    assert t(titulo) in textos_labels(pantalla)
    botones = [b for b in widgets(pantalla, toga.Button) if b.text != "◀ Volver"]
    assert [b.text for b in botones] == [t(c) for fila in filas for c in fila], "Se pintan todas las filas"
    if alto:
        assert all(b.style.height == alto for b in botones)


def test_volver_recorre_las_subpantallas_hasta_el_menu(en_menu):
    pulsar(en_menu, "Mantenimiento / Paso por taller")
    pulsar(en_menu, "Otros")
    pulsar(en_menu, "RODAMIENTOS")

    assert "Componentes" in textos_labels(pulsar(en_menu, "◀ Volver"))
    assert "Mantenimiento / Paso por taller" in textos_labels(pulsar(en_menu, "◀ Volver"))
    assert "Estadísticas" in textos_botones(pulsar(en_menu, "◀ Volver"))


def test_componente_abre_alta_con_elemento_preseleccionado(en_menu):
    pulsar(en_menu, "Mantenimiento / Paso por taller")
    pantalla = pulsar(en_menu, "Cadena")

    assert "Añadir Componente" in textos_labels(pantalla)
    assert f"Añadir Componente: {USUARIO}" not in textos_labels(pantalla)
    # 'Cadena' coincide (sin distinguir mayúsculas) con 'cadena' de la tabla Componente
    assert en_menu.selection_elemento.value == "cadena"
    assert [fila.value for fila in en_menu.selection_elemento.items].count("cadena") == 1


def test_componente_que_no_esta_en_bd_se_anade_al_desplegable(en_menu):
    pulsar(en_menu, "Mantenimiento / Paso por taller")
    pulsar(en_menu, "Otros")
    pulsar(en_menu, "HORQUILLA")
    assert en_menu.selection_elemento.value == "HORQUILLA"


def test_alta_desde_mantenimiento_guarda_y_vuelve_a_la_cuadricula(en_menu, db):
    pulsar(en_menu, "Mantenimiento / Paso por taller")
    pulsar(en_menu, "Otros")
    pulsar(en_menu, "Otros")
    pulsar(en_menu, "PEDALIER")
    en_menu.marca_texto.value = "Shimano"
    pulsar(en_menu, "Cargar")

    assert db.execute("SELECT usuario, elemento, marca FROM archivoscomponentes").fetchall() == [
        (USUARIO, "PEDALIER", "Shimano")
    ]
    pantalla = pulsar(en_menu, "◀ Volver")
    assert "Otros componentes" in textos_labels(pantalla)


def test_mas_componente_desde_estadisticas_vuelve_a_estadisticas(en_menu):
    pulsar(en_menu, "Estadísticas")
    pulsar(en_menu, "+ Componente")
    pantalla = pulsar(en_menu, "◀ Volver")
    assert en_menu.tabla in widgets(pantalla)


def test_limite_alerta_desde_estadisticas(en_menu, db):
    pulsar(en_menu, "Estadísticas")
    pulsar(en_menu, "+ Límite Alerta")
    en_menu.tipo_limite.value = "Precio Inferior"
    en_menu.valor_limite.value = "300"
    en_menu.componente_dropdown.items = ["Plato"]
    en_menu.componente_dropdown.value = "Plato"
    pulsar(en_menu, "Añadir")

    assert db.execute("SELECT componente, tipo_limite, valor FROM LimitesAlerta").fetchall() == [
        ("Plato", "inferior", 300)
    ]
    pantalla = pulsar(en_menu, "◀ Volver")
    assert en_menu.tabla in widgets(pantalla)


# ---- Coherencia de la definición de pantallas ----

def test_definicion_subpantallas_coherente():
    for (origen, texto), destino in SUBPANTALLAS_MANTENIMIENTO.items():
        assert origen in PANTALLAS_MANTENIMIENTO
        assert destino in PANTALLAS_MANTENIMIENTO
        filas_origen = PANTALLAS_MANTENIMIENTO[origen][1]
        assert any(texto in fila for fila in filas_origen), f"'{texto}' no es un botón de '{origen}'"
        assert PANTALLAS_MANTENIMIENTO[destino][3] == origen, "Volver debe regresar a la pantalla de origen"

    for clave, (_, _, _, anterior) in PANTALLAS_MANTENIMIENTO.items():
        assert anterior is None or anterior in PANTALLAS_MANTENIMIENTO, clave


# ---- Estadísticas: tabla 1 con todos los componentes ----

def _alta(db, elemento, fecha="2026-04-01", activo=1, usuario=USUARIO, descripcion="desc"):
    db.execute(
        "INSERT INTO archivoscomponentes (usuario, elemento, descripcion, fechaInsercion, distanciaLimite, "
        "tiempoLimite, activo) VALUES (?, ?, ?, ?, 5000, 500, ?)",
        (usuario, elemento, descripcion, fecha, activo),
    )
    db.connection.commit()


def test_estadisticas_muestra_todos_los_componentes_uno_por_linea(en_menu, db):
    pulsar(en_menu, "Estadísticas")
    catalogo = sorted((f[0] for f in db.execute("SELECT nombre FROM Componente")), key=orden_alfabetico)
    filas = list(en_menu.tabla.data)
    assert [f.elemento for f in filas] == catalogo
    assert all(f.descripcion == "POR DEFECTO" and f.distanciaDesdeInsercion == 0 for f in filas), \
        "Sin altas: componentes POR DEFECTO con 0 km"


def test_estadisticas_cruza_las_altas_del_usuario(en_menu, db):
    _alta(db, "Plato", descripcion="Plato 50")
    _alta(db, "Cadena", descripcion="KMC")                # 'cadena' en el catálogo: no se duplica
    _alta(db, "Plato", usuario="Otro", descripcion="ajeno")
    pulsar(en_menu, "Estadísticas")
    filas = {f.elemento: f for f in en_menu.tabla.data}
    assert len(filas) == 10
    assert filas["Plato"].descripcion == "Plato 50"
    assert filas["Cadena"].descripcion == "KMC" and "cadena" not in filas
    assert filas["Cubierta"].descripcion == "POR DEFECTO"


def test_estadisticas_varias_altas_muestra_la_activa_mas_reciente(en_menu, db):
    _alta(db, "Plato", fecha="2026-01-01", descripcion="vieja")
    _alta(db, "Plato", fecha="2026-03-01", descripcion="nueva")
    _alta(db, "Plato", fecha="2026-05-01", activo=0, descripcion="desactivada")
    pulsar(en_menu, "Estadísticas")
    platos = [f for f in en_menu.tabla.data if f.elemento == "Plato"]
    assert [f.descripcion for f in platos] == ["nueva"]


def test_estadisticas_incluye_componentes_fuera_del_catalogo(en_menu, db):
    _alta(db, "HORQUILLA")
    pulsar(en_menu, "Estadísticas")
    nombres = [f.elemento for f in en_menu.tabla.data]
    assert "HORQUILLA" in nombres and len(nombres) == 11
    assert "HORQUILLA" in en_menu.componentes_disponibles


def test_estadisticas_orden_alfabetico_ignora_acentos(en_menu):
    pulsar(en_menu, "Estadísticas")
    nombres = [f.elemento for f in en_menu.tabla.data]
    assert nombres.index("Cámara") < nombres.index("Cubierta")
    assert nombres[0] == "cadena"


def test_estadisticas_columna_activo_si_no(en_menu, db):
    _alta(db, "Plato", activo=1)
    _alta(db, "HORQUILLA", activo=0)
    pulsar(en_menu, "Estadísticas")
    filas = {f.elemento: f.activo for f in en_menu.tabla.data}
    assert filas["Plato"] == "Sí"
    assert filas["HORQUILLA"] == "No"
    assert set(filas.values()) == {"Sí", "No"}


@pytest.mark.parametrize("valor, texto", [
    (1, "Sí"), (0, "No"), (True, "Sí"), (False, "No"), ("1", "Sí"), ("0", "No"),
    ("True", "Sí"), ("False", "No"), (None, ""),
])
def test_texto_activo(valor, texto):
    assert texto_activo(valor) == texto


def test_texto_activo_traducido():
    translations.set_language("en")
    assert (texto_activo(1), texto_activo(0)) == ("Yes", "No")
    translations.set_language("fr")
    assert (texto_activo(1), texto_activo(0)) == ("Oui", "Non")


def test_estadisticas_cabeceras_horas(en_menu):
    pulsar(en_menu, "Estadísticas")
    assert [c.heading for c in en_menu.tabla.columns] == [
        "Componente", "Descripción", "Fecha", "Km máx", "Km desde alta", "Horas máx", "Horas desde alta",
        "Meses máx", "Meses desde alta", "Activo"]
    assert "Tiempo" not in [c.heading for c in en_menu.tabla.columns]


def test_estadisticas_columna_horas_desde_alta(en_menu, db):
    _alta(db, "Plato")
    db.execute("INSERT INTO ActividadesStrava (StravaID, tipo, distancia, duracion, user, fecha) "
               "VALUES (1, 'Ride', 40, 1.5, ?, '2026-04-02')", (USUARIO,))
    db.connection.commit()
    pulsar(en_menu, "Estadísticas")
    plato = [f for f in en_menu.tabla.data if f.elemento == "Plato"][0]
    assert (plato.tiempoLimite, plato.horasDesdeInsercion, plato.distanciaDesdeInsercion) == (500, 1.5, 40.0)


def test_alta_componente_etiqueta_horas_limite(en_menu):
    pulsar(en_menu, "Estadísticas")
    pantalla = pulsar(en_menu, "+ Componente")
    assert "Horas Límite: " in textos_labels(pantalla)


def test_alta_componente_usuario_en_la_linea_siguiente_en_azul(en_menu):
    pulsar(en_menu, "Mantenimiento / Paso por taller")
    pantalla = pulsar(en_menu, "Cadena")
    labels = textos_labels(pantalla)
    titulo = labels.index("Añadir Componente")
    assert labels[titulo + 1:titulo + 3] == ["Usuario: ", USUARIO]

    etiqueta, usuario = en_menu.label_usuario_componente, en_menu.label_usuario_seleccionado
    assert etiqueta.parent is usuario.parent and etiqueta.parent.style.direction == "row"
    assert etiqueta.parent.children == [etiqueta, usuario]
    assert str(etiqueta.style.color) == str(AZUL)
    assert usuario.style.color is None, "Solo el texto 'Usuario:' va en azul"


def test_alta_componente_usuario_traducido(en_menu):
    translations.set_language("fr")
    pantalla = en_menu.construir_pantalla_cinco(USUARIO)
    assert ["Ajouter un composant", "Utilisateur : ", USUARIO] == textos_labels(pantalla)[:3]


# ---- Límites por defecto en la pantalla de alta de componente ----

def limites_en_pantalla(ui):
    return ui.distancialim_texto.value, ui.tiempolim_texto.value, ui.meseslim_texto.value


@pytest.mark.parametrize("componente, esperado", [
    ("Cubierta", ("4000", "500", "")),
    ("cadena", ("2000", "500", "")),
    ("Líquido Frenos", ("", "", "12")),
    ("pastillas freno", ("4000", "500", "")),
    ("Plato", ("5000", "500", "")),
    ("Cámara", ("5000", "500", "")),
])
def test_alta_rellena_limites_por_defecto(en_menu, componente, esperado):
    en_menu.construir_pantalla_cinco(USUARIO, elemento=componente)
    assert limites_en_pantalla(en_menu) == esperado


@pytest.mark.parametrize("ruta, esperado", [
    (["Cadena"], ("2000", "500", "")),
    (["Pastillas freno"], ("4000", "500", "")),
    (["Cubiertas"], ("4000", "500", "")),
    (["Otros", "Otros", "Purgado FRENOS"], ("", "", "12")),
])
def test_alta_desde_mantenimiento_trae_sus_limites(en_menu, ruta, esperado):
    pulsar(en_menu, "Mantenimiento / Paso por taller")
    for texto in ruta:
        pulsar(en_menu, texto)
    assert limites_en_pantalla(en_menu) == esperado


def test_cambiar_de_componente_cambia_los_limites(en_menu):
    en_menu.construir_pantalla_cinco(USUARIO, elemento="Plato")
    en_menu.selection_elemento.value = "cadena"
    assert limites_en_pantalla(en_menu) == ("2000", "500", "")
    en_menu.selection_elemento.value = "Líquido Frenos"
    assert limites_en_pantalla(en_menu) == ("", "", "12")


def test_alta_guarda_los_limites_de_los_cuadros(en_menu, db):
    pantalla = en_menu.construir_pantalla_cinco(USUARIO, elemento="Líquido Frenos")
    en_menu.meseslim_texto.value = "18"
    boton(pantalla, "Cargar")._impl.simulate_press()
    assert db.execute("SELECT elemento, distanciaLimite, tiempoLimite, mesesLimite FROM archivoscomponentes").fetchall() == [
        ("Líquido Frenos", None, None, 18)]


def test_alta_con_cuadros_vacios_usa_los_limites_del_componente(en_menu, db, campo):
    en_menu.anadirComponente(campo("2026-06-01"), USUARIO, campo("Cadena"), campo(""), campo(""))
    assert db.execute("SELECT distanciaLimite, tiempoLimite, mesesLimite FROM archivoscomponentes").fetchone() == (
        2000, 500, None)


def test_estadisticas_meses(en_menu, db):
    from datetime import date
    hoy = date.today()
    alta = date(hoy.year - 1, hoy.month, 1)          # día 1 de hace 12 meses: 12 meses completos
    _alta(db, "Líquido Frenos", fecha=alta.isoformat())
    db.execute("UPDATE archivoscomponentes SET mesesLimite = 12 WHERE elemento = 'Líquido Frenos'")
    db.connection.commit()
    pulsar(en_menu, "Estadísticas")
    fila = [f for f in en_menu.tabla.data if f.elemento == "Líquido Frenos"][0]
    assert (fila.mesesLimite, fila.mesesDesdeInsercion) == (12, 12)


# ---- Ventana de Alerta al cargar el menú del usuario ----

@pytest.fixture
def dialogos(con_usuario, monkeypatch):
    """Ventanas de Alerta abiertas (su contenido); en los tests no se crea una ventana real."""
    abiertos = []
    monkeypatch.setattr(type(con_usuario), "_abrir_ventana_alerta", lambda self, contenido, titulo: abiertos.append(contenido))
    return abiertos


def test_menu_abre_alerta_con_componentes_urgentes(con_usuario, dialogos):
    pulsar(con_usuario, f"{USUARIO}-Damián Vega")
    assert len(dialogos) == 1
    assert textos_labels(dialogos[0]) == [
        "Alerta", "Componentes a cambiar de manera urgente :\n\n• Cadena\n• Pastillas de Freno"]
    assert "Aceptar" in textos_botones(dialogos[0])


def test_titulo_alerta_en_rojo_y_tamano_24(con_usuario, dialogos):
    pulsar(con_usuario, f"{USUARIO}-Damián Vega")
    titulo = con_usuario.label_titulo_alerta
    assert titulo.text == "Alerta"
    assert titulo.style.color == rgb(220, 0, 0)
    assert titulo.style.font_size == 24
    assert con_usuario.label_mensaje_alerta.style.color is None, "Solo el título va en rojo"


def test_alerta_se_muestra_tambien_al_volver_al_menu(con_usuario, dialogos):
    pulsar(con_usuario, f"{USUARIO}-Damián Vega")
    pulsar(con_usuario, "Estadísticas")
    pulsar(con_usuario, "◀ Volver")
    assert [d.label_titulo.text for d in dialogos].count("Alerta") == 2


def test_sin_componentes_urgentes_no_hay_alerta(con_usuario, dialogos, monkeypatch):
    monkeypatch.setattr(type(con_usuario), "componentesUrgentes", lambda self, usuario: [])
    pulsar(con_usuario, f"{USUARIO}-Damián Vega")
    assert dialogos == []


def test_alerta_traducida(con_usuario, dialogos):
    translations.set_language("en")
    con_usuario.ir_a_menu_usuario(None, USUARIO)
    assert textos_labels(dialogos[0])[0] == "Alert"
    assert textos_labels(dialogos[0])[1].startswith("Components to replace urgently:")
    assert "OK" in textos_botones(dialogos[0])


def test_aceptar_cierra_la_ventana_de_alerta(con_usuario, dialogos):
    cerradas = []
    contenido = con_usuario.construirVentanaAlerta(["Cadena"])
    contenido.ventana = SimpleNamespace(close=lambda: cerradas.append(True))
    con_usuario.boton_aceptar_alerta._impl.simulate_press()
    assert cerradas == [True] and contenido.ventana is None
    con_usuario.cerrarVentanaAviso(contenido)                 # ya cerrada: no falla


def test_sin_app_de_toga_no_se_abre_ventana(con_usuario):
    assert con_usuario._abrir_ventana_alerta(con_usuario.construirVentanaAlerta(["Cadena"]), "Alerta") is None


def test_pintar_fondo_boton_solo_en_cocoa(en_menu):
    from toga.colors import color as parse_color

    from bikecompfollowapp.app import pintar_fondo_boton
    # backend de pruebas (toga_dummy): no se toca nada, se queda el background_color de Pack
    assert pintar_fondo_boton(en_menu.boton_estadisticas, "#FF8C00") is False
    assert en_menu.boton_estadisticas.style.background_color == parse_color("#FF8C00")
    assert en_menu.boton_mantenimiento.style.background_color == parse_color("#1E64C8")


# ---- Estadísticas: "Usuario:" en azul y tabla Tiempo y Kms por Modalidad ----

def test_estadisticas_usuario_en_azul_a_la_izquierda(en_menu):
    pantalla = pulsar(en_menu, "Estadísticas")
    etiqueta, usuario = en_menu.label_usuario_estadisticas, en_menu.label_usuario_seleccionado_est
    linea = etiqueta.parent
    assert linea.style.direction == "row" and linea.children[:2] == [etiqueta, usuario]
    assert (etiqueta.text, usuario.text) == ("Usuario: ", USUARIO)
    assert etiqueta.style.color == AZUL and usuario.style.color is None
    contenido = pantalla.children[0]
    assert contenido.children[0] is linea, "Primera línea de la pantalla"
    assert f"Usuario: {USUARIO}" not in textos_labels(pantalla), "Ya no va centrado en un solo texto"


def actividad_bd(db, strava_id, modalidad, fecha, km, horas, usuario=USUARIO, tipo="Ride"):
    db.execute("INSERT INTO ActividadesStrava (StravaID, tipo, Modalidad, distancia, duracion, user, fecha) "
               "VALUES (?, ?, ?, ?, ?, ?, ?)", (strava_id, tipo, modalidad, km, horas, usuario, fecha))
    db.connection.commit()


def cabeceras(tabla):
    return [c.heading for c in tabla.columns]


def filas_texto(tabla):
    """Filas de la tabla como listas de textos, en el orden de sus columnas."""
    return [[getattr(fila, c.accessor) for c in tabla.columns] for fila in tabla.data]


def test_tabla_modalidad_debajo_de_componentes(en_menu):
    pulsar(en_menu, "Estadísticas")
    contenido = en_menu.tabla.parent
    hijos = contenido.children
    i = hijos.index(en_menu.tabla)
    assert en_menu.Title_tablaModalidad in hijos[i + 1:i + 3]
    assert hijos.index(en_menu.tablaModalidad) == hijos.index(en_menu.Title_tablaModalidad) + 1
    assert hijos.index(en_menu.tablaModalidad) < hijos.index(en_menu.Title_tablaLimites)
    assert en_menu.Title_tablaModalidad.text == "Tiempo y Kms por Modalidad"


def test_tabla_modalidad_cabeceras_y_filas(en_menu, monkeypatch):
    monkeypatch.setattr(dbops, "date", type("D", (), {"today": staticmethod(lambda: __import__("datetime").date(2026, 11, 5))}))
    pulsar(en_menu, "Estadísticas")
    assert cabeceras(en_menu.tablaModalidad) == [
        "Modalidad", "Desde", "2024 KMs", "2024 Horas", "2025 KMs", "2025 Horas", "2026 KMs", "2026 Horas"]
    assert [f[0] for f in filas_texto(en_menu.tablaModalidad)] == ["Road", "MTB", "Gravel"]


def test_tabla_modalidad_mismo_estilo_que_las_otras_tablas(en_menu):
    pulsar(en_menu, "Estadísticas")
    assert all(isinstance(tabla, toga.Table) for tabla in (en_menu.tabla, en_menu.tablaModalidad, en_menu.tablaLimites))
    assert en_menu.tablaModalidad.style.flex == en_menu.tabla.style.flex == 1
    assert en_menu.tablaModalidad.style.height == 28 + 3 * 22


def test_tabla_modalidad_acumulados(en_menu, db, dialogos):
    actividad_bd(db, 1, "Road", "2024-03-01", 50.0, 2.0)
    actividad_bd(db, 2, "Road", "2024-05-01", 30.25, 1.25)
    actividad_bd(db, 3, "Road", "2026-01-10", 80.0, 3.0)
    actividad_bd(db, 4, "MTB", "2025-06-01", 40.0, 2.5)
    actividad_bd(db, 5, "Gravel", "2026-02-01", 60.0, 3.0)
    actividad_bd(db, 6, None, "2026-02-02", 10.0, 1.0, tipo="Run")             # sin modalidad: no cuenta
    actividad_bd(db, 7, "Road", "2025-02-02", 999.0, 9.0, usuario="Otro")      # otro usuario
    actividad_bd(db, 8, "Road", "2023-12-31", 500.0, 20.0)                     # fuera de los 3 años
    filas, sin_datos = dbops.kmsHorasPorModalidad(db.connection, USUARIO, [2024, 2025, 2026])
    assert filas == [
        ("Road", "2023-12-31", 80.3, 3.3, 0.0, 0.0, 80.0, 3.0),
        ("MTB", "2025-06-01", 0.0, 0.0, 40.0, 2.5, 0.0, 0.0),
        ("Gravel", "2026-02-01", 0.0, 0.0, 0.0, 0.0, 60.0, 3.0),
    ]
    assert sin_datos == []


def test_tabla_modalidad_se_pinta_con_los_datos(en_menu, db, dialogos):
    actividad_bd(db, 1, "MTB", f"{date.today().year}-01-02", 40.0, 2.5)
    pulsar(en_menu, "Estadísticas")
    mtb = [f for f in filas_texto(en_menu.tablaModalidad) if f[0] == "MTB"][0]
    assert mtb[1] == f"{date.today().year}-01-02"
    assert mtb[-2:] == ["40", "2.5"]
    road = [f for f in filas_texto(en_menu.tablaModalidad) if f[0] == "Road"][0]
    assert road[1] == "—" and set(road[2:]) == {"0"}


def test_advertencia_por_cada_anio_sin_datos(en_menu, db, dialogos):
    hoy = date.today().year
    actividad_bd(db, 1, "Road", f"{hoy - 1}-05-01", 50.0, 2.0)
    pulsar(en_menu, "Estadísticas")
    avisos = [d for d in dialogos if d.label_titulo.text == "Advertencia !!!"]
    assert len(avisos) == 1
    assert avisos[0].label_mensaje.text.splitlines() == [f"No hay datos del año {hoy - 2}", f"No hay datos del año {hoy}"]
    assert avisos[0].label_titulo.style.color == modulo_app.ROJO_ALERTA


def test_sin_advertencia_si_hay_datos_los_tres_anios(en_menu, db, dialogos):
    hoy = date.today().year
    for n, anio in enumerate(range(hoy - 2, hoy + 1)):
        actividad_bd(db, n, "Gravel", f"{anio}-05-01", 10.0, 1.0)
    pulsar(en_menu, "Estadísticas")
    assert not [d for d in dialogos if d.label_titulo.text == "Advertencia !!!"]


def test_un_anio_solo_con_carreras_cuenta_como_sin_datos(en_menu, db):
    hoy = date.today().year
    actividad_bd(db, 1, None, f"{hoy}-05-01", 10.0, 1.0, tipo="Run")
    _, sin_datos = dbops.kmsHorasPorModalidad(db.connection, USUARIO, [hoy])
    assert sin_datos == [hoy]


def test_advertencia_traducida(en_menu, dialogos):
    translations.set_language("en")
    en_menu.ir_a_pantalla_tres(None, USUARIO)
    aviso = [d for d in dialogos if d.label_titulo.text == "Warning !!!"][0]
    assert aviso.label_mensaje.text.splitlines()[0].startswith("No data for year ")
    assert cabeceras(en_menu.tablaModalidad)[2:4] == [f"{date.today().year - 2} Km", f"{date.today().year - 2} Hours"]


@pytest.mark.parametrize("valor, texto", [(None, ""), (0.0, "0"), (12.0, "12"), (1959.45, "1959.5"), (2.24, "2.2")])
def test_texto_numero(valor, texto):
    assert modulo_app.texto_numero(valor) == texto


def test_anios_estadisticas():
    from datetime import date as fecha
    assert dbops.aniosEstadisticas(fecha(2026, 11, 5)) == [2024, 2025, 2026]
