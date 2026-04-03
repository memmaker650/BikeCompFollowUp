BEGIN TRANSACTION;

-- Tabla Tipo Vehículo
CREATE TABLE tipo_vehiculo_new  (
	"id"	INTEGER PRIMARY KEY,
	"vehiculo"	TEXT
);

INSERT INTO tipo_vehiculo_new  (id,  vehiculo)
SELECT id,  vehiculo
FROM  tipo_vehiculo;

DROP TABLE tipo_vehiculo;

ALTER TABLE tipo_vehiculo_new RENAME TO tipo_vehiculo;


-- Tabla Elemento
CREATE TABLE "Elemento" (
	"id"	INTEGER PRIMARY KEY,
	"nombre"	TEXT
)

CREATE TABLE "Elemento_new" (
	"id"	INTEGER PRIMARY KEY,
	"nombre"	TEXT
);

INSERT INTO Elemento_new (id, nombre)
SELECT id, nombre
FROM Elemento;

DROP TABLE Elemento;

ALTER TABLE Elemento_new RENAME TO Elemento;

-- Tabla StravaValores
CREATE TABLE IF NOT EXISTS stravaValores  (id integer PRIMARY KEY,  fecha date not NULL, valor INTEGER not NULL,  ascenso INTEGER, tipo TEXT not null, num_actividades INTEGER, horas INTEGER)

-- Tabla Token Guardado
CREATE TABLE IF NOT EXISTS token (refresh_token TEXT, expires_at date)

-- Tabla Datos
CREATE TABLE IF NOT EXISTS datos (id integer PRIMARY KEY, fecha Date, datos text NOT NULL, km integer NOT NULL, activo BOOLEAN NOT NULL);

-- Tabla Entradas
CREATE TABLE IF NOT EXISTS Entradas (id integer PRIMARY KEY,  fecha Date,  nombre text NOT NULL,  usuario text,  tipov integer NOT NULL, descripcion  TEXT NOT NULL, FOREIGN KEY (tipov) REFERENCES tipo_vehiculo(id))

-- Tabla Elementos lincados por Entrada
CREATE TABLE IF NOT EXISTS linked_elements (id integer PRIMARY KEY, fecha Date, Entrada_num integer, num_elemento, FOREIGN KEY (Entrada_num) REFERENCES Entradas(id), FOREIGN KEY (num_Elemento) REFERENCES Elemento(id));

-- Tabla  Estadísticas
CREATE TABLE IF NOT EXISTS estadisticas (id interger PRIMARY KEY, jugador text NOT NULL, partida integer, disparos integer, nivelmax integer NOT NULL, enemigosmuertos integer, vidasusadas integer)

-- Tabla Componentes
DROP TABLE archivoscomponentes
CREATE TABLE IF NOT EXISTS archivoscomponentes (id INTEGER PRIMARY KEY, usuario NOT NULL, elemento TEXT NOT NULL, descripcion TEXT, marca TEXT, fechaInsercion Date NOT NULL, distanciaLímite integer, tiempoLímite integer, activo BOOLEAN DEFAULT True)



-- Escribir valores por defecto en las tablas.
INSERT INTO "main"."Elemento" ("nombre") VALUES ('cadena');
INSERT INTO "main"."Elemento" ("nombre") VALUES ('pastillas freno');
INSERT INTO "main"."Elemento" ("nombre") VALUES ('Cubierta');
INSERT INTO "main"."Elemento" ("nombre") VALUES ('Cinta Manillar');
INSERT INTO "main"."Elemento" ("nombre") VALUES ('Piñonera');
INSERT INTO "main"."Elemento" ("nombre") VALUES ('Plato');
INSERT INTO "main"."Elemento" ("nombre") VALUES ('Cambio Trasero');
INSERT INTO "main"."Elemento" ("nombre") VALUES ('Líquido Frenos');
INSERT INTO "main"."Elemento" ("nombre") VALUES ('Maneta Cambio');
INSERT INTO "main"."Elemento" ("nombre") VALUES ('Cámara');

INSERT INTO "main"."tipo_vehiculo" ("vehiculo") VALUES ('Coche');
INSERT INTO "main"."tipo_vehiculo" ("vehiculo") VALUES ('Bici Carretera');
INSERT INTO "main"."tipo_vehiculo" ("vehiculo") VALUES ('Bici Gravel');
INSERT INTO "main"."tipo_vehiculo" ("vehiculo") VALUES ('Bici MTB');
INSERT INTO "main"."tipo_vehiculo" ("vehiculo") VALUES ('Tractor');
