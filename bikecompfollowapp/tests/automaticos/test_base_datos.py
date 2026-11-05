"""Tests de creación e inicialización de la base de datos (arrancarDB / crearDBBasica)."""

import sqlite3

from bikecompfollowapp.app import (
    AppPaths,
    BikeCompFollowApp,
)

TABLAS_ESPERADAS = {
    "datosComponente",
    "Componente",
    "stravaValores",
    "EntradasUsers",
    "linked_elements",
    "tipo_vehiculo",
    "archivoscomponentes",
    "LimitesAlerta",
}


def test_appaths_usa_carpeta_de_datos_de_la_app(app_paths):
    ruta = AppPaths.get("data", "BikeCFU", "dbbcfu.db")
    assert ruta == app_paths / "BikeCFU" / "dbbcfu.db"
    assert ruta.parent.is_dir(), "AppPaths.get debe crear la carpeta contenedora"


def test_appaths_sin_parts_devuelve_base(app_paths):
    assert AppPaths.get("data") == app_paths


def test_bd_nueva_crea_todas_las_tablas(app, tablas):
    assert TABLAS_ESPERADAS <= tablas(app.sqliteConnection)


def test_bd_se_crea_en_carpeta_bikecfu(app, app_paths):
    assert app.db_path == app_paths / "BikeCFU" / "dbbcfu.db"
    assert app.db_path.exists()


def test_bd_nueva_carga_datos_basicos(db):
    vehiculos = [f[0] for f in db.execute("SELECT vehiculo FROM tipo_vehiculo ORDER BY id")]
    assert vehiculos == ["Coche", "Bici Carretera", "Bici Gravel", "Bici MTB", "Tractor"]

    elementos = {f[0] for f in db.execute("SELECT nombre FROM Componente")}
    assert len(elementos) == 10
    assert {"cadena", "Cubierta", "Cambio Trasero"} <= elementos


def test_datos_basicos_se_guardan_en_disco(app):
    """Los datos sembrados deben estar confirmados (commit) y verse desde otra conexión."""
    otra = sqlite3.connect(app.db_path)
    try:
        assert otra.execute("SELECT COUNT(*) FROM tipo_vehiculo").fetchone()[0] == 5
        assert otra.execute("SELECT COUNT(*) FROM Componente").fetchone()[0] == 10
    finally:
        otra.close()


def test_rearrancar_no_duplica_datos_basicos(app):
    app.sqliteConnection.close()
    app.arrancarDB()
    db = app.sqliteConnection
    assert db.execute("SELECT COUNT(*) FROM tipo_vehiculo").fetchone()[0] == 5
    assert db.execute("SELECT COUNT(*) FROM Componente").fetchone()[0] == 10


def test_bd_existente_no_se_vuelve_a_sembrar(app_paths):
    """Con una BD que ya tiene EntradasUsers no se insertan los datos básicos."""
    ruta = AppPaths.get("data", "BikeCFU", "dbbcfu.db")
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE EntradasUsers (id integer PRIMARY KEY, fecha Date, nombre text NOT NULL, "
        "usuario text, tipov integer NOT NULL, descripcion TEXT NOT NULL)"
    )
    con.execute("CREATE TABLE tipo_vehiculo (id INTEGER PRIMARY KEY, vehiculo TEXT)")
    con.execute("INSERT INTO tipo_vehiculo (vehiculo) VALUES ('Mi bici')")
    con.commit()
    con.close()

    instancia = object.__new__(BikeCompFollowApp)
    instancia.arrancarDB()
    try:
        vehiculos = [f[0] for f in instancia.cursor.execute("SELECT vehiculo FROM tipo_vehiculo")]
        assert vehiculos == ["Mi bici"]
    finally:
        instancia.sqliteConnection.close()


def test_tipo_vehiculo_vacio_se_rellena_con_valores_por_defecto(app_paths):
    ruta = AppPaths.get("data", "BikeCFU", "dbbcfu.db")
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE EntradasUsers (id integer PRIMARY KEY, fecha Date, nombre text NOT NULL, "
        "usuario text, tipov integer NOT NULL, descripcion TEXT NOT NULL)"
    )
    con.commit()
    con.close()

    instancia = object.__new__(BikeCompFollowApp)
    instancia.arrancarDB()
    try:
        vehiculos = [f[0] for f in instancia.cursor.execute("SELECT vehiculo FROM tipo_vehiculo ORDER BY id")]
        assert vehiculos == ["Carretera", "Montaña", "Híbrida"]
    finally:
        instancia.sqliteConnection.close()


def test_integridad_bd(app, capsys):
    app.db.chequearIntegrarDB()
    assert "DB íntegra" in capsys.readouterr().out


def test_crear_tabla_limites_es_idempotente(app):
    assert app.db.crearTablaAlertThresholds() is True
    assert app.db.crearTablaAlertThresholds() is True


def test_columnas_limites_alerta(db):
    columnas = [f[1] for f in db.execute("PRAGMA table_info(LimitesAlerta)")]
    assert columnas == ["id", "componente", "tipo_limite", "valor", "usuario", "vehiculo"]


def test_columnas_archivoscomponentes(db):
    columnas = [f[1] for f in db.execute("PRAGMA table_info(archivoscomponentes)")]
    assert columnas == [
        "id", "usuario", "elemento", "descripcion", "marca",
        "fechaInsercion", "distanciaLimite", "tiempoLimite", "activo", "mesesLimite",
    ]


def test_archivoscomponentes_sin_meses_se_migra_conservando_filas(app, db):
    from bikecompfollowapp.DB_Operations import asegurarColumnasArchivosComponentes
    con = app.sqliteConnection
    con.execute("DROP TABLE archivoscomponentes")
    con.execute("CREATE TABLE archivoscomponentes (id INTEGER PRIMARY KEY, usuario NOT NULL, elemento TEXT NOT NULL, "
                "descripcion TEXT, marca TEXT, fechaInsercion Date NOT NULL, distanciaLimite integer, "
                "tiempoLimite integer, activo BOOLEAN DEFAULT True)")
    con.execute("INSERT INTO archivoscomponentes (usuario, elemento, fechaInsercion) VALUES ('u', 'Plato', '2026-01-01')")
    asegurarColumnasArchivosComponentes(con)
    asegurarColumnasArchivosComponentes(con)          # idempotente
    assert db.execute("SELECT elemento, mesesLimite FROM archivoscomponentes").fetchall() == [("Plato", None)]


def test_cerrar_db(app):
    app.db.cerrarDB()
    try:
        app.sqliteConnection.execute("SELECT 1")
        assert False, "La conexión debería estar cerrada"
    except sqlite3.ProgrammingError:
        pass
    # La fixture vuelve a cerrar; reabrimos para que no falle.
    app.sqliteConnection = sqlite3.connect(app.db_path)


# ---- Renombrado datos -> datosComponente y Elemento -> Componente ----

def _bd_con_tablas_antiguas(ruta):
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE EntradasUsers (id integer PRIMARY KEY, fecha Date, nombre text NOT NULL, "
        "usuario text, tipov integer NOT NULL, descripcion TEXT NOT NULL)"
    )
    con.execute("CREATE TABLE datos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, fecha TEXT, activo BOOLEAN)")
    con.execute("INSERT INTO datos (nombre, fecha, activo) VALUES ('dato', '2026-01-01', 1)")
    con.execute("CREATE TABLE Elemento (id INTEGER PRIMARY KEY, nombre TEXT)")
    con.executemany("INSERT INTO Elemento (nombre) VALUES (?)", [("cadena",), ("Plato",), ("Mi pieza",)])
    con.execute(
        "CREATE TABLE linked_elements (id integer PRIMARY KEY, fecha Date, Entrada_num integer, num_elemento, "
        "FOREIGN KEY (num_Elemento) REFERENCES Elemento(id))"
    )
    con.commit()
    con.close()


def test_bd_existente_renombra_tablas_conservando_filas(app_paths, tablas):
    ruta = AppPaths.get("data", "BikeCFU", "dbbcfu.db")
    _bd_con_tablas_antiguas(ruta)

    instancia = object.__new__(BikeCompFollowApp)
    instancia.arrancarDB()
    try:
        db = instancia.sqliteConnection
        nombres = tablas(db)
        assert {"datosComponente", "Componente"} <= nombres
        assert not {"datos", "Elemento"} & nombres
        assert [f[0] for f in db.execute("SELECT nombre FROM Componente ORDER BY id")] == ["cadena", "Plato", "Mi pieza"]
        assert db.execute("SELECT nombre, fecha, activo FROM datosComponente").fetchall() == [("dato", "2026-01-01", 1)]
        sql = db.execute("SELECT sql FROM sqlite_master WHERE name = 'linked_elements'").fetchone()[0]
        assert "Componente" in sql and "Elemento(" not in sql, "La FOREIGN KEY debe apuntar a Componente"
    finally:
        instancia.sqliteConnection.close()


def test_renombrar_es_idempotente(app):
    assert app.db.renombrarTablasAntiguas() is True
    assert app.db.renombrarTablasAntiguas() is True
    assert app.sqliteConnection.execute("SELECT COUNT(*) FROM Componente").fetchone()[0] == 10


def test_renombrar_si_la_tabla_nueva_esta_vacia(app, tablas):
    db = app.sqliteConnection
    db.execute("DELETE FROM Componente")
    db.execute("CREATE TABLE Elemento (id INTEGER PRIMARY KEY, nombre TEXT)")
    db.execute("INSERT INTO Elemento (nombre) VALUES ('antiguo')")
    db.commit()
    assert app.db.renombrarTablasAntiguas() is True
    assert "Elemento" not in tablas(db)
    assert db.execute("SELECT nombre FROM Componente").fetchall() == [("antiguo",)]


def test_renombrar_no_pisa_una_tabla_nueva_con_datos(app, tablas):
    db = app.sqliteConnection
    db.execute("CREATE TABLE Elemento (id INTEGER PRIMARY KEY, nombre TEXT)")
    db.execute("INSERT INTO Elemento (nombre) VALUES ('antiguo')")
    db.commit()
    assert app.db.renombrarTablasAntiguas() is True
    assert "Elemento" in tablas(db), "Se deja la antigua para no perder datos"
    assert db.execute("SELECT COUNT(*) FROM Componente").fetchone()[0] == 10
