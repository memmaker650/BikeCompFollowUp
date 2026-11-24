"""Pantalla de alta de componente: obligatorios con asterisco rojo, sin Descripción, Marca y Modelo, campo Otros
de la cadena (velocidades) y sección de límites."""

import sqlite3

import pytest
import toga

from bikecompfollowapp import translations
from bikecompfollowapp.app import ROJO_OBLIGATORIO, VELOCIDADES_CADENA

USUARIO = "memmaker650"


@pytest.fixture
def alta(ui):
    ui.sqliteConnection.execute("INSERT INTO EntradasUsers (nombre, usuario, tipov, descripcion) "
                                "VALUES ('Jorge', ?, 'Bici Gravel', '')", (USUARIO,))
    ui.sqliteConnection.commit()
    ui.usuarioSeleccionado = USUARIO

    def abrir(elemento="cadena", **kw):
        ui.pantalla_alta = ui.construir_pantalla_cinco(USUARIO, elemento=elemento, **kw)
        return ui
    return abrir


def widgets(raiz, tipo=None):
    pendientes, encontrados = [raiz], []
    while pendientes:
        w = pendientes.pop(0)
        if tipo is None or isinstance(w, tipo):
            encontrados.append(w)
        pendientes.extend(getattr(w, "children", None) or [])
        if isinstance(w, toga.ScrollContainer) and w.content is not None:   # p. ej. Estadísticas
            pendientes.append(w.content)
    return encontrados


def filas_formulario(ui):
    """{texto de la etiqueta: fila} de las filas de campo (las que tienen el atributo obligatorio)."""
    return {fila.children[0].children[0].text: fila for fila in widgets(ui.pantalla_alta)
            if hasattr(fila, "obligatorio")}


def pulsar_cargar(ui):
    [b for b in widgets(ui.pantalla_alta, toga.Button) if b.text == "Cargar"][0]._impl.simulate_press()


def otros_visible(ui):
    """La fila Otros está en el formulario (justo después de Modelo)."""
    hijos = ui.formulario_alta.children
    if ui.fila_otros not in hijos:
        return False
    assert hijos.index(ui.fila_otros) == hijos.index(ui.fila_modelo) + 1
    return True


def componentes(ui):
    return ui.sqliteConnection.execute(
        "SELECT elemento, modalidad, descripcion, marca, otros FROM archivoscomponentes ORDER BY id").fetchall()


# ---- Obligatorios con asterisco rojo ----

def test_obligatorios_con_asterisco_rojo(alta):
    ui = alta()
    filas = filas_formulario(ui)
    obligatorios = {texto for texto, fila in filas.items() if fila.obligatorio}
    assert obligatorios == {"Fecha", "Elemento", "Modalidad: "}
    for texto, fila in filas.items():
        etiqueta = fila.children[0]
        asteriscos = [w for w in etiqueta.children if w.text == "*"]
        if fila.obligatorio:
            assert len(asteriscos) == 1 and asteriscos[0].style.color == ROJO_OBLIGATORIO, texto
        else:
            assert not asteriscos, f"{texto} no es obligatorio"


def test_leyenda_de_obligatorio(alta):
    ui = alta()
    leyenda = [w for w in widgets(ui.pantalla_alta, toga.Label) if w.text == "* Campo obligatorio"]
    assert len(leyenda) == 1 and leyenda[0].style.color == ROJO_OBLIGATORIO


def test_sin_fecha_no_se_guarda(alta):
    ui = alta()
    ui.entrada_fecha.value = "   "
    pulsar_cargar(ui)
    assert componentes(ui) == []
    assert ui.label_pantalla_dos.text == "Faltan campos obligatorios (*)"


# ---- Sin Descripción ----

def test_no_hay_campo_descripcion(alta):
    ui = alta()
    assert not [t for t in filas_formulario(ui) if t.startswith("Descripción")]
    assert not hasattr(ui, "descripcion_texto") or ui.descripcion_texto not in widgets(ui.pantalla_alta)


def test_alta_guarda_sin_descripcion_y_deja_de_ser_por_defecto(alta):
    ui = alta("Plato")
    ui.db.calcularKmComponentes(USUARIO)                     # crea los POR DEFECTO (Gravel)
    ui = alta("Plato", modalidad="Gravel")
    ui.marca_texto.value = "SRAM"
    pulsar_cargar(ui)
    fila = ui.sqliteConnection.execute(
        "SELECT descripcion, marca FROM archivoscomponentes WHERE elemento = 'Plato'").fetchall()
    assert fila == [(None, "SRAM")], "El POR DEFECTO se rellena y ya no se marca como POR DEFECTO"


# ---- Otros: velocidades de la cadena ----

def test_velocidades_de_6_a_13():
    assert VELOCIDADES_CADENA == ["6v", "7v", "8v", "9v", "10v", "11v", "12v", "13v"]


def test_campo_otros_solo_para_la_cadena(alta):
    ui = alta("cadena")
    assert otros_visible(ui)
    assert [i.value for i in ui.selection_otros.items] == [""] + VELOCIDADES_CADENA
    assert ui.selection_otros.value == "", "Por defecto sin indicar"
    assert ui.fila_otros.obligatorio is False
    ui.selection_otros.value = "12v"
    ui.selection_elemento.value = "Plato"
    assert not otros_visible(ui)
    assert ui.selection_otros.value == "", "Al cambiar a otro componente se vacía"
    ui.selection_elemento.value = "cadena"
    assert otros_visible(ui)
    ui.selection_elemento.value = "cadena"          # sin cambio: no se duplica
    assert ui.formulario_alta.children.count(ui.fila_otros) == 1


@pytest.mark.parametrize("elemento", ["Cadena", "CADENA", "cadena"])
def test_otros_se_ve_con_cualquier_nombre_de_la_cadena(alta, elemento):
    assert otros_visible(alta(elemento))


@pytest.mark.parametrize("elemento", ["Plato", "Cubierta", "Líquido Frenos"])
def test_otros_oculto_en_el_resto(alta, elemento):
    assert not otros_visible(alta(elemento))


def test_cadena_guarda_las_velocidades(alta):
    ui = alta("cadena", modalidad="MTB")
    ui.selection_otros.value = "12v"
    pulsar_cargar(ui)
    assert componentes(ui) == [("cadena", "MTB", None, "", "12v")]


def test_cadena_sin_velocidades_se_guarda_igual(alta):
    ui = alta("cadena", modalidad="Road")
    pulsar_cargar(ui)
    assert componentes(ui) == [("cadena", "Road", None, "", None)]


def test_otro_componente_no_guarda_otros(alta, campo):
    ui = alta("Plato")
    ui.anadirComponente(campo("2026-06-01"), USUARIO, campo("Plato"), None, campo(""), valor8=campo("Road"),
                        valor9=campo("11v"))
    assert componentes(ui)[-1][4] is None


# ---- Sección de límites ----

def test_limites_en_su_seccion(alta):
    ui = alta()
    seccion = ui.seccion_limites
    assert seccion.children[0].text == "Límites" and seccion.children[0].style.font_weight == "bold"
    dentro = {w for w in widgets(seccion)}
    for cuadro in (ui.distancialim_texto, ui.tiempolim_texto, ui.meseslim_texto):
        assert cuadro in dentro
    for cuadro in (ui.entrada_fecha, ui.selection_elemento, ui.selection_modalidad, ui.marca_texto, ui.selection_otros):
        assert cuadro not in dentro


def test_ningun_limite_es_obligatorio(alta):
    ui = alta()
    filas = [w for w in widgets(ui.seccion_limites) if hasattr(w, "obligatorio")]
    assert len(filas) == 3 and not any(f.obligatorio for f in filas)
    for cuadro in (ui.distancialim_texto, ui.tiempolim_texto, ui.meseslim_texto):
        cuadro.value = ""
    pulsar_cargar(ui)
    assert len(componentes(ui)) == 1, "Se guarda con los límites vacíos"


def test_seccion_entre_los_datos_y_el_boton(alta):
    ui = alta()
    formulario = ui.seccion_limites.parent
    hijos = formulario.children
    cargar = [b for b in hijos if isinstance(b, toga.Button)][0]
    assert hijos.index(ui.fila_otros) < hijos.index(ui.seccion_limites) < hijos.index(cargar)
    ui.selection_elemento.value = "Plato"
    assert hijos.index(ui.fila_modelo) + 1 == hijos.index(ui.seccion_limites), "Sin hueco donde estaba Otros"


# ---- Base de datos e idiomas ----

def test_columna_otros_en_archivoscomponentes(ui):
    columnas = [f[1] for f in ui.sqliteConnection.execute("PRAGMA table_info(archivoscomponentes)")]
    assert columnas[columnas.index("mesesLimite") + 1] == "otros"


def test_tabla_sin_otros_se_migra(ui):
    con = ui.sqliteConnection
    con.execute("ALTER TABLE archivoscomponentes DROP COLUMN otros")
    con.execute("INSERT INTO archivoscomponentes (usuario, elemento, modalidad, fechaInsercion) "
                "VALUES ('u', 'Plato', 'Road', '2026-01-01')")
    from bikecompfollowapp.DB_Operations import asegurarColumnasArchivosComponentes
    asegurarColumnasArchivosComponentes(con)
    assert con.execute("SELECT elemento, otros FROM archivoscomponentes").fetchall() == [("Plato", None)]


def test_textos_traducidos(alta):
    translations.set_language("en")
    ui = alta()
    assert ui.seccion_limites.children[0].text == "Limits"
    assert "Other: " in filas_formulario(ui)
    assert [w for w in widgets(ui.pantalla_alta, toga.Label) if w.text == "* Required field"]


def test_columna_otros_admite_nulo(ui):
    ui.sqliteConnection.execute("INSERT INTO archivoscomponentes (usuario, elemento, modalidad, fechaInsercion) "
                                "VALUES ('u', 'x', 'MTB', '2026-01-01')")
    with pytest.raises(sqlite3.IntegrityError):
        ui.sqliteConnection.execute("INSERT INTO archivoscomponentes (usuario, elemento, fechaInsercion, otros) "
                                    "VALUES ('u', 'x', '2026-01-01', '12v')")


# ---- Modelo del componente (opcional, tras Marca) ----

def modelos(ui):
    return ui.sqliteConnection.execute(
        "SELECT elemento, marca, modelo FROM archivoscomponentes WHERE descripcion IS NULL ORDER BY id").fetchall()


def test_modelo_va_tras_marca_y_no_es_obligatorio(alta):
    ui = alta("Cubiertas")
    hijos = ui.formulario_alta.children
    assert hijos.index(ui.fila_modelo) == hijos.index(ui.fila_marca) + 1
    assert filas_formulario(ui)["Modelo Comp: "].obligatorio is False


def test_en_la_cadena_otros_va_tras_modelo(alta):
    ui = alta("cadena")
    hijos = ui.formulario_alta.children
    assert hijos.index(ui.fila_otros) == hijos.index(ui.fila_modelo) + 1


def test_alta_guarda_marca_y_modelo(alta):
    ui = alta("Cubiertas")
    ui.marca_texto.value = "Continental"
    ui.modelo_texto.value = "  Terra Speed  "
    pulsar_cargar(ui)
    assert modelos(ui) == [("Cubiertas", "Continental", "Terra Speed")]


def test_modelo_vacio_se_guarda_nulo(alta):
    ui = alta("Cubiertas")
    ui.marca_texto.value = "Continental"
    pulsar_cargar(ui)
    assert modelos(ui) == [("Cubiertas", "Continental", None)]


def test_columna_modelo_tras_marca_en_tablas_nuevas(ui):
    columnas = [f[1] for f in ui.sqliteConnection.execute("PRAGMA table_info(archivoscomponentes)")]
    assert columnas.index("modelo") == columnas.index("marca") + 1


def test_tabla_sin_modelo_se_migra_conservando_filas(ui):
    con = ui.sqliteConnection
    con.execute("ALTER TABLE archivoscomponentes DROP COLUMN modelo")
    con.execute("INSERT INTO archivoscomponentes (usuario, elemento, modalidad, marca, fechaInsercion) "
                "VALUES ('u', 'Plato', 'Road', 'Shimano', '2026-01-01')")
    from bikecompfollowapp.DB_Operations import asegurarColumnasArchivosComponentes
    asegurarColumnasArchivosComponentes(con)
    assert con.execute("SELECT elemento, marca, modelo FROM archivoscomponentes").fetchall() == [
        ("Plato", "Shimano", None)]


def test_campo_modelo_traducido(alta):
    translations.set_language("en")
    assert "Model: " in filas_formulario(alta("Cubiertas"))
    translations.set_language("fr")
    assert "Modèle : " in filas_formulario(alta("Cubiertas"))


# ---- Botón + Componente (guardar y dar de alta otro) ----

def botones(ui):
    return [b.text for b in widgets(ui.formulario_alta, toga.Button)]


def pulsar_mas_componente(ui):
    [b for b in widgets(ui.pantalla_alta, toga.Button) if b.text == "+ Componente"][0]._impl.simulate_press()


def test_mas_componente_justo_encima_de_cargar_con_el_mismo_formato(alta):
    ui = alta("Cubiertas")
    hijos = ui.formulario_alta.children
    mas = [w for w in hijos if isinstance(w, toga.Button) and w.text == "+ Componente"][0]
    cargar = [w for w in hijos if isinstance(w, toga.Button) and w.text == "Cargar"][0]
    assert hijos.index(cargar) == hijos.index(mas) + 1
    assert mas.style.margin == cargar.style.margin


def test_mas_componente_guarda_y_limpia_el_formulario(alta):
    ui = alta("cadena")
    fecha, modalidad = ui.entrada_fecha.value, ui.selection_modalidad.value
    km_defecto = ui.distancialim_texto.value
    ui.marca_texto.value, ui.modelo_texto.value = "KMC", "X11"
    ui.selection_otros.value = "11v"
    ui.distancialim_texto.value = "1500"
    pulsar_mas_componente(ui)
    assert ui.sqliteConnection.execute(
        "SELECT elemento, marca, modelo, otros, distanciaLimite FROM archivoscomponentes WHERE descripcion IS NULL"
    ).fetchall() == [("cadena", "KMC", "X11", "11v", 1500)]
    assert (ui.marca_texto.value, ui.modelo_texto.value, ui.selection_otros.value) == ("", "", "")
    assert ui.distancialim_texto.value == km_defecto
    assert (ui.entrada_fecha.value, ui.selection_elemento.value, ui.selection_modalidad.value) == (
        fecha, "cadena", modalidad)


def test_mas_componente_permite_dar_de_alta_otro_seguido(alta):
    ui = alta("Cubiertas")
    ui.marca_texto.value = "Continental"
    pulsar_mas_componente(ui)
    ui.selection_elemento.value = "cadena"
    ui.marca_texto.value = "KMC"
    pulsar_mas_componente(ui)
    assert ui.sqliteConnection.execute(
        "SELECT elemento, marca FROM archivoscomponentes WHERE descripcion IS NULL ORDER BY id").fetchall() == [
        ("Cubiertas", "Continental"), ("cadena", "KMC")]


def test_mas_componente_sin_obligatorios_no_guarda_ni_limpia(alta):
    ui = alta("Cubiertas")
    ui.entrada_fecha.value = ""
    ui.marca_texto.value = "Continental"
    pulsar_mas_componente(ui)
    assert ui.sqliteConnection.execute(
        "SELECT count(*) FROM archivoscomponentes WHERE descripcion IS NULL").fetchone() == (0,)
    assert ui.marca_texto.value == "Continental"


def test_mas_componente_traducido(alta):
    translations.set_language("en")
    assert "+ Component" in botones(alta("Cubiertas"))
    translations.set_language("fr")
    assert "+ Composant" in botones(alta("Cubiertas"))
