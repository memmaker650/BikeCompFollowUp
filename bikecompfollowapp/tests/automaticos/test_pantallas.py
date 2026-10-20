"""Tests de navegación entre pantallas (backend toga_dummy, sin ventanas reales)."""

import pytest
import toga

from bikecompfollowapp.app import (
    PANTALLA_MANTENIMIENTO,
    PANTALLAS_MANTENIMIENTO,
    SUBPANTALLAS_MANTENIMIENTO,
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

def test_menu_strava_sync_abajo_a_la_izquierda(en_menu):
    barra = barra_inferior(en_menu.main_window.content)
    assert isinstance(barra.children[0], toga.Button)
    assert barra.children[0].text == "Strava Sync"


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
    assert {"Iniciar", "Extraer Datos Strava"} <= set(textos_botones(pantalla))
    pantalla = pulsar(en_menu, "◀ Volver")
    assert "Mantenimiento / Paso por taller" in textos_botones(pantalla)


# ---- Pantallas de mantenimiento ----

def test_mantenimiento_muestra_cuadricula(en_menu):
    pantalla = pulsar(en_menu, "Mantenimiento / Paso por taller")
    filas = PANTALLAS_MANTENIMIENTO[PANTALLA_MANTENIMIENTO][1]
    esperados = [t for fila in filas for t in fila]
    assert [t for t in textos_botones(pantalla) if t != "◀ Volver"] == esperados


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
    assert titulo in textos_labels(pantalla)
    botones = [b for b in widgets(pantalla, toga.Button) if b.text != "◀ Volver"]
    assert [b.text for b in botones] == [t for fila in filas for t in fila], "Se pintan todas las filas"
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

    assert f"Añadir Componente: {USUARIO}" in textos_labels(pantalla)
    # 'Cadena' coincide (sin distinguir mayúsculas) con 'cadena' de la tabla Elemento
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
