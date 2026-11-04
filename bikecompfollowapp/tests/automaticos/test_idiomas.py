"""Tests del fichero de textos (translations_data.xml) y del botón de idioma de la pantalla inicial."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import toga

from bikecompfollowapp import translations
from bikecompfollowapp.translations import t

APP_PY = Path(translations.__file__).with_name("app.py")
BANDERAS = {"es": "🇪🇸", "en": "🇬🇧", "fr": "🇫🇷"}


def botones(raiz):
    pendientes, encontrados = [raiz], []
    while pendientes:
        w = pendientes.pop(0)
        if isinstance(w, toga.Button):
            encontrados.append(w)
        pendientes.extend(getattr(w, "children", None) or [])
    return encontrados


def textos(raiz):
    return [b.text for b in botones(raiz)]


def pulsar(ui, texto):
    [b for b in botones(ui.main_window.content) if b.text == texto][0]._impl.simulate_press()
    return ui.main_window.content


# ---- Fichero XML ----

def test_xml_define_castellano_ingles_y_frances():
    assert [(l.code, l.name, l.flag) for l in translations.languages()] == [
        ("es", "Castellano", BANDERAS["es"]),
        ("en", "English", BANDERAS["en"]),
        ("fr", "Français", BANDERAS["fr"]),
    ]


def test_idioma_por_defecto_es_castellano():
    assert translations.current().code == "es"
    assert t("comun.volver") == "◀ Volver"


def test_todos_los_idiomas_tienen_los_mismos_textos():
    claves = {l.code: set(l.texts) for l in translations.languages()}
    for code, ks in claves.items():
        assert ks == claves["es"], f"Diferencias en {code}: {ks ^ claves['es']}"


def test_no_hay_claves_duplicadas_ni_textos_vacios():
    root = ET.parse(translations.XML_PATH).getroot()
    for idioma in root.findall("language"):
        claves = [x.get("key") for x in idioma.findall("text")]
        assert len(claves) == len(set(claves)), idioma.get("code")
        vacios = [x.get("key") for x in idioma.findall("text") if not (x.text or "").strip()]
        assert not vacios, (idioma.get("code"), vacios)


def test_marcadores_iguales_en_todos_los_idiomas():
    marcadores = lambda texto: set(re.findall(r"{(\w+)}", texto))
    por_defecto = {l.code: l for l in translations.languages()}["es"]
    for idioma in translations.languages():
        for clave, texto in idioma.texts.items():
            assert marcadores(texto) == marcadores(por_defecto.texts[clave]), (idioma.code, clave)


def test_todas_las_claves_del_codigo_existen_en_el_xml():
    codigo = APP_PY.read_text(encoding="utf-8")
    prefijos = {clave.split(".")[0] for clave in translations.current().texts}
    usadas = set(re.findall(r'"((?:%s)\.[a-z_]+)"' % "|".join(prefijos), codigo))
    assert usadas, "No se encontraron claves en app.py"
    assert usadas <= set(translations.current().texts), usadas - set(translations.current().texts)


# ---- Funciones de traducción ----

def test_t_con_marcadores():
    assert t("menu.usuario", usuario="Ana") == "Usuario: Ana"
    translations.set_language("en")
    assert t("menu.usuario", usuario="Ana") == "User: Ana"
    translations.set_language("fr")
    assert t("strava.guardando", actual=2, total=5) == "Enregistrement de l'activité 2 sur 5"


def test_clave_inexistente_devuelve_la_clave():
    assert t("no.existe") == "no.existe"


def test_idioma_desconocido_no_cambia_el_activo():
    translations.set_language("de")
    assert translations.current().code == "es"


def test_texto_sin_traducir_usa_el_castellano(tmp_path):
    xml = tmp_path / "textos.xml"
    xml.write_text(
        '<translations default="es">'
        '<language code="es" flag="E"><text key="a">Hola</text><text key="b">Adiós</text></language>'
        '<language code="en" flag="U"><text key="a">Hello</text></language>'
        '</translations>',
        encoding="utf-8",
    )
    translations.load(xml)
    translations.set_language("en")
    assert t("a") == "Hello"
    assert t("b") == "Adiós"


def test_siguiente_idioma_es_ciclico():
    orden = []
    for _ in range(4):
        siguiente = translations.next_language()
        translations.set_language(siguiente.code)
        orden.append(siguiente.code)
    assert orden == ["en", "fr", "es", "en"]


def test_default_text_ignora_el_idioma_activo():
    translations.set_language("fr")
    assert translations.default_text("pieza.horquilla") == "HORQUILLA"
    assert t("pieza.horquilla") == "FOURCHE"


# ---- Botón de idioma y textos de las pantallas ----

@pytest.fixture
def inicio(ui, db):
    db.execute(
        "INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) VALUES ('Damián', 'DaMario', 1, '')"
    )
    ui.sqliteConnection.commit()
    ui.volver_pantalla_inicial()
    return ui


def test_boton_bandera_abajo_a_la_derecha(inicio):
    barra = inicio.main_window.content.children[-1]
    esquina = barra.children[-1]
    assert textos(esquina)[-1] == BANDERAS["es"]
    assert "+ Usuario" in textos(esquina)


@pytest.mark.parametrize("pulsaciones, idioma, titulo, nuevo_usuario", [
    (1, "en", "Select the user", "+ User"),
    (2, "fr", "Sélectionnez l'utilisateur", "+ Utilisateur"),
    (3, "es", "Selecciona el usuario", "+ Usuario"),
])
def test_bandera_cambia_idioma_y_textos(inicio, pulsaciones, idioma, titulo, nuevo_usuario):
    bandera = BANDERAS["es"]
    for _ in range(pulsaciones):
        pantalla = pulsar(inicio, bandera)
        bandera = translations.current().flag

    assert translations.current().code == idioma
    assert bandera == BANDERAS[idioma]
    assert inicio.label.text == titulo
    assert nuevo_usuario in textos(pantalla)


def test_idioma_se_guarda_en_bd(inicio):
    pulsar(inicio, BANDERAS["es"])
    assert inicio.leerAjuste("idioma") == "en"
    pulsar(inicio, BANDERAS["en"])
    assert inicio.leerAjuste("idioma") == "fr"


def test_idioma_guardado_se_recupera_al_arrancar(inicio):
    pulsar(inicio, BANDERAS["es"])        # -> inglés
    translations.load()                  # simula reinicio: vuelve al castellano...
    inicio.cargarIdioma()                # ...y al arrancar se aplica el guardado
    assert translations.current().code == "en"


def test_ajustes_guardar_y_leer(app):
    assert app.leerAjuste("x", "def") == "def"
    assert app.guardarAjuste("x", "1") is True
    assert app.guardarAjuste("x", "2") is True
    assert app.leerAjuste("x") == "2"


def test_menu_y_mantenimiento_en_ingles(inicio):
    pulsar(inicio, BANDERAS["es"])
    pantalla = pulsar(inicio, "DaMario-Damián")
    assert {"Statistics", "Maintenance / Workshop visit", "Strava Sync", "◀ Back"} <= set(textos(pantalla))

    pantalla = pulsar(inicio, "Maintenance / Workshop visit")
    assert {"Chain", "Brake pads", "Others"} <= set(textos(pantalla))

    pantalla = pulsar(inicio, "Others")
    assert {"FORK", "BEARINGS", "TUBELESS"} <= set(textos(pantalla))


def test_componente_en_frances_se_guarda_en_castellano(inicio, db):
    pulsar(inicio, BANDERAS["es"])
    pulsar(inicio, BANDERAS["en"])       # -> francés
    pulsar(inicio, "DaMario-Damián")
    pulsar(inicio, "Entretien / Passage à l'atelier")
    pulsar(inicio, "Autres")
    pulsar(inicio, "FOURCHE")
    assert inicio.selection_elemento.value == "HORQUILLA"
    pulsar(inicio, "Enregistrer")
    assert db.execute("SELECT elemento FROM archivoscomponentes").fetchone() == ("HORQUILLA",)


def test_limite_en_ingles_se_guarda_como_superior(inicio, db):
    pulsar(inicio, BANDERAS["es"])
    inicio.usuarioSeleccionado = "DaMario"
    inicio.PantallaNuevaAlerta("Plato", ["Plato"])
    assert [fila.value for fila in inicio.tipo_limite.items] == ["Upper limit", "Lower limit"]
    inicio.tipo_limite.value = "Upper limit"
    inicio.valor_limite.value = "100"
    assert inicio.cargar_limiteAlerta() is True
    assert db.execute("SELECT tipo_limite FROM LimitesAlerta").fetchone() == ("superior",)


def test_cabeceras_de_tabla_traducidas(inicio):
    translations.set_language("fr")
    inicio.ir_a_pantalla_tres(None, "DaMario")
    assert [c.heading for c in inicio.tabla.columns][:3] == ["Composant", "Description", "Date"]


def test_tabla_ajustes_existe_en_bd_nueva(app, tablas):
    assert "ajustes" in tablas(app.sqliteConnection)
