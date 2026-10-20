"""Tests de alta de entradas (vehículos/usuarios) y de componentes."""

from datetime import datetime


def _rellenar_entrada(app, campo, **valores):
    app.entrada_texto = campo(valores.get("nombre", "Damián Vega"))
    app.usuario_texto = campo(valores.get("usuario", "DaMario Bros"))
    app.descripcion_texto = campo(valores.get("descripcion", "Bici de carretera"))
    app.selection_tipo_vehiculo = campo(valores.get("tipov", "Bici Carretera"))
    app.selection_elemento = campo(valores.get("elemento", "cadena"))
    app.entrada_fecha = campo(valores.get("fecha", "2026-10-01"))


def test_cargar_entrada_inserta_en_entradas_users(app, db, campo):
    _rellenar_entrada(app, campo)
    app.cargar_entrada(None)

    fila = db.execute("SELECT fecha, nombre, usuario, tipov, descripcion FROM EntradasUsers").fetchone()
    assert fila == ("2026-10-01", "Damián Vega", "DaMario Bros", "Bici Carretera", "Bici de carretera")
    assert app.label_pantalla_dos.text == "Entrada cargada correctamente."


def test_cargar_entrada_limpia_espacios(app, db, campo):
    _rellenar_entrada(app, campo, nombre="  Lucía  ", usuario=" lucia ")
    app.cargar_entrada(None)
    assert db.execute("SELECT nombre, usuario FROM EntradasUsers").fetchone() == ("Lucía", "lucia")


def test_cargar_entrada_sin_fecha_usa_hoy(app, db, campo):
    _rellenar_entrada(app, campo, fecha="")
    app.cargar_entrada(None)
    hoy = datetime.today().strftime("%Y-%m-%d")
    assert db.execute("SELECT fecha FROM EntradasUsers").fetchone()[0] == hoy


def _rellenar_componente(campo, distancia="", tiempo="", fecha="2026-10-01"):
    return dict(
        valor1=campo(fecha),
        user="DaMario Bros",
        valor2=campo("Cambio Trasero"),
        valor3=campo("Shimano 105"),
        valor4=campo("Shimano"),
        valor5=campo(distancia),
        valor6=campo(tiempo),
    )


def test_anadir_componente_con_limites(app, db, campo):
    app.anadirComponente(**_rellenar_componente(campo, distancia="8000", tiempo="300"))

    fila = db.execute(
        "SELECT fechaInsercion, usuario, elemento, descripcion, marca, distanciaLimite, tiempoLimite, activo "
        "FROM archivoscomponentes"
    ).fetchone()
    assert fila == ("2026-10-01", "DaMario Bros", "Cambio Trasero", "Shimano 105", "Shimano", 8000, 300, 1)


def test_anadir_componente_sin_limites_usa_valores_por_defecto(app, db, campo):
    app.anadirComponente(**_rellenar_componente(campo))
    assert db.execute("SELECT distanciaLimite, tiempoLimite FROM archivoscomponentes").fetchone() == (5000, 500)


def test_cargar_componente_devuelve_true(app, db, campo):
    datos = _rellenar_componente(campo)
    assert app.cargar_componente(*datos.values()) is True
    assert db.execute("SELECT COUNT(*) FROM archivoscomponentes").fetchone()[0] == 1


def test_desactivar_componente(app, db, campo):
    app.anadirComponente(**_rellenar_componente(campo))
    datos = _rellenar_componente(campo)
    datos["user"] = "Otro usuario"
    app.anadirComponente(**datos)

    app.desactivarComponente("Cambio Trasero", "DaMario Bros")

    filas = dict(db.execute("SELECT usuario, activo FROM archivoscomponentes"))
    assert filas == {"DaMario Bros": 0, "Otro usuario": 1}, "Solo se desactiva el del usuario indicado"


def test_desactivar_componente_inexistente_no_cambia_nada(app, db, campo):
    app.anadirComponente(**_rellenar_componente(campo))
    app.desactivarComponente("Plato", "DaMario Bros")
    assert db.execute("SELECT activo FROM archivoscomponentes").fetchone()[0] == 1
