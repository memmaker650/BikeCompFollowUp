"""Tests de navegación entre pantallas (backend toga_dummy, sin ventanas reales)."""

import pytest
import toga

from bikecompfollowapp import translations
from bikecompfollowapp.translations import t
from bikecompfollowapp.app import (
    AZUL,
    PANTALLA_MANTENIMIENTO,
    PANTALLAS_MANTENIMIENTO,
    SUBPANTALLAS_MANTENIMIENTO,
    orden_alfabetico,
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
