"""Tests de los límites de alerta (tabla LimitesAlerta)."""

from types import SimpleNamespace

import pytest


def _preparar_limite(app, campo, tipo="Precio Superior", valor="5000", componente="Cambio Trasero"):
    app.tipo_limite = campo(tipo)
    app.valor_limite = campo(valor)
    app.componente_dropdown = campo(componente)


def test_guardar_limite_superior(app, db, campo):
    _preparar_limite(app, campo)
    assert app.cargar_limiteAlerta() is True

    assert db.execute("SELECT componente, tipo_limite, valor FROM LimitesAlerta").fetchall() == [
        ("Cambio Trasero", "superior", 5000)
    ]
    assert app.label_estado == "✅"
    assert app.label_pantalla_LimiteNuevaAlerta.text.endswith("✅")


def test_guardar_limite_inferior(app, db, campo):
    _preparar_limite(app, campo, tipo="Precio Inferior", valor="100")
    app.cargar_limiteAlerta()
    assert db.execute("SELECT tipo_limite, valor FROM LimitesAlerta").fetchone() == ("inferior", 100)


def test_limite_duplicado_no_se_inserta_dos_veces(app, db, campo):
    _preparar_limite(app, campo, valor="5000")
    app.cargar_limiteAlerta()
    _preparar_limite(app, campo, valor="9999")
    app.cargar_limiteAlerta()

    assert db.execute("SELECT valor FROM LimitesAlerta").fetchall() == [(5000,)]


def test_limite_sin_tipo_marca_error(app, db, campo):
    _preparar_limite(app, campo, tipo=None)
    assert app.cargar_limiteAlerta() is False

    assert db.execute("SELECT COUNT(*) FROM LimitesAlerta").fetchone()[0] == 0
    assert app.label_estado == "❌"


@pytest.mark.parametrize("tipo, esperado", [
    ("Precio Superior", "superior"),
    ("Precio Inferior", "inferior"),
    ("superior", "superior"),   # valores leídos de LimitesAlerta en el desplegable
    ("inferior", "inferior"),
])
def test_tipo_de_limite_se_normaliza(app, db, campo, tipo, esperado):
    _preparar_limite(app, campo, tipo=tipo)
    app.cargar_limiteAlerta()
    assert db.execute("SELECT tipo_limite FROM LimitesAlerta").fetchone() == (esperado,)


def test_seleccionar_limites_componente(app, campo):
    _preparar_limite(app, campo, tipo="Precio Superior", valor="5000")
    app.cargar_limiteAlerta()
    _preparar_limite(app, campo, tipo="Precio Inferior", valor="1000")
    app.cargar_limiteAlerta()
    _preparar_limite(app, campo, componente="Plato", valor="20000")
    app.cargar_limiteAlerta()

    limites = app.seleccionarLimitesComponente("Cambio Trasero")
    assert sorted(limites) == [("Cambio Trasero", "inferior", 1000), ("Cambio Trasero", "superior", 5000)]


def test_seleccionar_limites_componente_sin_datos(app):
    assert app.seleccionarLimitesComponente("No existe") == []


def test_seleccionar_limites_sin_tabla_devuelve_lista_vacia(app):
    app.sqliteConnection.execute("DROP TABLE LimitesAlerta")
    assert app.seleccionarLimitesComponente("Cambio Trasero") == []


def test_tipos_alerta_se_leen_de_limites_alerta(app, campo):
    """La consulta que alimenta el desplegable de la pantalla de nuevo límite."""
    _preparar_limite(app, campo, tipo="Precio Inferior")
    app.cargar_limiteAlerta()
    _preparar_limite(app, campo, tipo="Precio Superior", componente="Plato")
    app.cargar_limiteAlerta()

    tipos = [
        f[0]
        for f in app.sqliteConnection.execute(
            "SELECT DISTINCT tipo_limite FROM LimitesAlerta WHERE tipo_limite IS NOT NULL ORDER BY tipo_limite"
        )
    ]
    assert tipos == ["inferior", "superior"]


# ---- Selección en la tabla de componentes -> tabla de límites ----

def test_obtener_componente_sin_tabla(app):
    app.tabla = None
    assert app.obtener_componente_seleccionado() is None


def test_obtener_componente_sin_seleccion(app):
    app.tabla = SimpleNamespace(selection=None)
    assert app.obtener_componente_seleccionado() is None


def test_obtener_componente_seleccion_simple(app):
    app.tabla = SimpleNamespace(selection=SimpleNamespace(elemento="Cadena"))
    assert app.obtener_componente_seleccionado() == "Cadena"


def test_obtener_componente_seleccion_multiple(app):
    app.tabla = SimpleNamespace(selection=[SimpleNamespace(elemento="Plato"), SimpleNamespace(elemento="Cadena")])
    assert app.obtener_componente_seleccionado() == "Plato"


def test_obtener_componente_seleccion_lista_vacia(app):
    app.tabla = SimpleNamespace(selection=[])
    assert app.obtener_componente_seleccionado() is None


def test_actualizar_limites_rellena_tabla(app, campo):
    _preparar_limite(app, campo)
    app.cargar_limiteAlerta()
    app.tabla = SimpleNamespace(selection=SimpleNamespace(elemento="Cambio Trasero"))
    app.tablaLimites = SimpleNamespace(data=None)

    app.actualizar_limites_componente_seleccionado()

    assert app.tablaLimites.data == [("Cambio Trasero", "superior", 5000)]


def test_actualizar_limites_sin_seleccion_vacia_tabla(app):
    app.tabla = SimpleNamespace(selection=None)
    app.tablaLimites = SimpleNamespace(data=[("x", "y", 1)])

    app.actualizar_limites_componente_seleccionado()

    assert app.tablaLimites.data == []
