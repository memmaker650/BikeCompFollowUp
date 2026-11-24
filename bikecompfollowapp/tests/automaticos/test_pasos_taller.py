"""Tabla PasosTaller: cada confirmación de componentes cambiados en Mantenimiento es un paso por taller
(id, usuario, fecha, modalidad) y sus componentes llevan su id en archivoscomponentes.idPasoTaller."""

import sqlite3

import pytest

from bikecompfollowapp.DB_Operations import asegurarColumnasArchivosComponentes

USUARIO = "memmaker650"


def componente(elemento, **extra):
    return dict(fecha="2026-05-20", elemento=elemento, descripcion=None, marca="", distancia=2000, tiempo=500,
                meses=None, modalidad="MTB", **extra)


def test_columnas_de_pasos_taller(db):
    assert [f[1] for f in db.execute("PRAGMA table_info(PasosTaller)")] == [
        "id", "usuario", "fecha", "modalidad", "coste"]


@pytest.mark.parametrize("fila", [
    (None, "2026-05-20", "MTB"), ("u", None, "MTB"), ("u", "2026-05-20", None), ("u", "2026-05-20", "Trail"),
])
def test_usuario_fecha_y_modalidad_obligatorios(db, fila):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO PasosTaller (usuario, fecha, modalidad) VALUES (?, ?, ?)", fila)


def test_registrar_paso_guarda_el_paso_y_enlaza_sus_componentes(app, db):
    id_paso = app.db.registrarPasoTaller(USUARIO, "2026-05-20", "MTB",
                                         [componente("cadena", otros="12v"), componente("Cubiertas")])
    assert db.execute("SELECT id, usuario, fecha, modalidad FROM PasosTaller").fetchall() == [
        (id_paso, USUARIO, "2026-05-20", "MTB")]
    assert db.execute("SELECT elemento, otros, idPasoTaller FROM archivoscomponentes ORDER BY id").fetchall() == [
        ("cadena", "12v", id_paso), ("Cubiertas", None, id_paso)]


def test_si_falla_un_componente_no_se_guarda_nada(app, db):
    malo = componente("Plato") | {"modalidad": "Trail"}      # modalidad no válida
    assert app.db.registrarPasoTaller(USUARIO, "2026-05-20", "MTB", [componente("cadena"), malo]) is None
    assert db.execute("SELECT count(*) FROM PasosTaller").fetchone() == (0,)
    assert db.execute("SELECT count(*) FROM archivoscomponentes").fetchone() == (0,)


def test_paso_sin_modalidad_valida_no_se_guarda(app, db):
    assert app.db.registrarPasoTaller(USUARIO, "2026-05-20", "Trail", [componente("cadena")]) is None
    assert db.execute("SELECT count(*) FROM archivoscomponentes").fetchone() == (0,)


def test_el_componente_por_defecto_queda_enlazado_al_paso(app, db):
    db.execute("INSERT INTO archivoscomponentes (usuario, elemento, modalidad, descripcion, fechaInsercion) "
               "VALUES (?, 'cadena', 'MTB', 'POR DEFECTO', '2026-01-01')", (USUARIO,))
    app.sqliteConnection.commit()
    id_paso = app.db.registrarPasoTaller(USUARIO, "2026-05-20", "MTB", [componente("cadena")])
    assert db.execute("SELECT descripcion, fechaInsercion, idPasoTaller FROM archivoscomponentes").fetchall() == [
        (None, "2026-05-20", id_paso)]


def test_altas_sueltas_no_tienen_paso(app, db):
    app.db.guardarComponente("2026-05-20", USUARIO, "Plato", None, "", 5000, 500, None, "Road")
    assert db.execute("SELECT idPasoTaller FROM archivoscomponentes").fetchone() == (None,)


def test_lista_de_pasos_del_usuario_mas_reciente_primero(app):
    primero = app.db.registrarPasoTaller(USUARIO, "2026-03-01", "Road", [componente("cadena")])
    segundo = app.db.registrarPasoTaller(USUARIO, "2026-05-20", "MTB", [componente("cadena"), componente("Plato")],
                                         coste=85.5)
    app.db.registrarPasoTaller("otro", "2026-06-01", "MTB", [componente("cadena")])
    assert app.db.pasosTaller(USUARIO) == [(segundo, "2026-05-20", "MTB", 85.5, 2),
                                           (primero, "2026-03-01", "Road", None, 1)]


def test_tabla_antigua_gana_la_columna_id_paso_taller(app, db):
    con = app.sqliteConnection
    con.execute("ALTER TABLE archivoscomponentes DROP COLUMN idPasoTaller")
    con.execute("INSERT INTO archivoscomponentes (usuario, elemento, modalidad, fechaInsercion) "
                "VALUES ('u', 'Plato', 'Road', '2026-01-01')")
    asegurarColumnasArchivosComponentes(con)
    assert db.execute("SELECT elemento, idPasoTaller FROM archivoscomponentes").fetchall() == [("Plato", None)]


def test_se_crea_al_preparar_las_tablas(app, tablas):
    app.sqliteConnection.execute("DROP TABLE PasosTaller")
    app.db.prepararTablas()
    assert "PasosTaller" in tablas(app.sqliteConnection)


# ---- Coste de la reparación ----

def test_registrar_paso_guarda_el_coste(app, db):
    id_paso = app.db.registrarPasoTaller(USUARIO, "2026-05-20", "MTB", [componente("cadena")], coste=45.5)
    assert db.execute("SELECT coste FROM PasosTaller WHERE id = ?", (id_paso,)).fetchone() == (45.5,)


def test_coste_opcional(app, db):
    app.db.registrarPasoTaller(USUARIO, "2026-05-20", "MTB", [componente("cadena")])
    assert db.execute("SELECT coste FROM PasosTaller").fetchone() == (None,)


def test_coste_negativo_no_se_admite(app, db):
    assert app.db.registrarPasoTaller(USUARIO, "2026-05-20", "MTB", [componente("cadena")], coste=-1) is None
    assert db.execute("SELECT count(*) FROM archivoscomponentes").fetchone() == (0,), "Todo o nada"


def test_pasos_taller_antigua_gana_la_columna_coste(app, db):
    con = app.sqliteConnection
    con.execute("DROP TABLE PasosTaller")
    con.execute("CREATE TABLE PasosTaller (id INTEGER PRIMARY KEY, usuario TEXT NOT NULL, fecha DATE NOT NULL, "
                "modalidad TEXT NOT NULL)")
    con.execute("INSERT INTO PasosTaller (usuario, fecha, modalidad) VALUES ('u', '2026-01-01', 'Road')")
    app.db.crearTablaPasosTaller()
    assert db.execute("SELECT usuario, coste FROM PasosTaller").fetchall() == [("u", None)]


@pytest.mark.parametrize("texto, esperado", [
    ("", None), ("  ", None), ("45", 45.0), ("45,50", 45.5), ("45.5", 45.5), (" 120 € ", 120.0), ("0", 0.0),
    ("12,345", 12.35),
])
def test_leer_coste(texto, esperado):
    from bikecompfollowapp.app import BikeCompFollowApp
    assert BikeCompFollowApp.leer_coste(texto) == esperado


@pytest.mark.parametrize("texto", ["abc", "-5", "nan", "inf", "1.2.3"])
def test_leer_coste_no_valido(texto):
    from bikecompfollowapp.app import BikeCompFollowApp
    with pytest.raises(ValueError):
        BikeCompFollowApp.leer_coste(texto)


# ---- Historial y edición de pasos por taller ----

def test_historial_taller_con_componentes_y_fecha_descendente(app):
    viejo = app.db.registrarPasoTaller(USUARIO, "2026-03-01", "Road", [componente("cadena")], coste=40)
    nuevo = app.db.registrarPasoTaller(USUARIO, "2026-05-20", "MTB", [componente("Cubiertas"), componente("Plato")])
    assert app.db.historialTaller(USUARIO) == [
        dict(id=nuevo, fecha="2026-05-20", modalidad="MTB", coste=None, componentes="Cubiertas, Plato",
             num_componentes=2),
        dict(id=viejo, fecha="2026-03-01", modalidad="Road", coste=40.0, componentes="cadena", num_componentes=1)]


def test_actualizar_paso_taller(app, db):
    id_paso = app.db.registrarPasoTaller(USUARIO, "2026-03-01", "Road", [componente("cadena")])
    assert app.db.actualizarPasoTaller(id_paso, "2026-03-02", "Gravel", 12.5) is True
    assert app.db.pasoTallerPorId(id_paso) == dict(id=id_paso, usuario=USUARIO, fecha="2026-03-02",
                                                   modalidad="Gravel", coste=12.5, componentes="cadena")


@pytest.mark.parametrize("modalidad, coste", [("Trail", 10), ("Road", -3)])
def test_actualizar_paso_taller_no_valido(app, db, modalidad, coste):
    id_paso = app.db.registrarPasoTaller(USUARIO, "2026-03-01", "Road", [componente("cadena")], coste=5)
    assert app.db.actualizarPasoTaller(id_paso, "2026-03-02", modalidad, coste) is False
    assert db.execute("SELECT fecha, modalidad, coste FROM PasosTaller").fetchone() == ("2026-03-01", "Road", 5.0)


def test_actualizar_paso_que_no_existe(app):
    assert app.db.actualizarPasoTaller(999, "2026-03-02", "Road", None) is False
    assert app.db.pasoTallerPorId(999) is None
