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
CREATE TABLE "Elemento_new" (
	"id"	INTEGER PRIMARY KEY,
	"nombre"	TEXT
);

INSERT INTO Elemento_new (id, nombre)
SELECT id, nombre
FROM Elemento;

DROP TABLE Elemento;

ALTER TABLE Elemento_new RENAME TO Elemento;

-- Tabla Datos

CREATE TABLE datos (id integer PRIMARY KEY, fecha Date, datos text NOT NULL, km integer NOT NULL, activo BOOLEAN NOT NULL);

-- Tabla Entradas
CREATE TABLE Entradas (id integer PRIMARY KEY, fecha Date, nombre text NOT NULL, usuario text, tipov integer NOT NULL, FOREIGN KEY (tipov) REFERENCES tipo_vehiculo(id));

-- Tabla Elementos lincados por Entrada
CREATE TABLE linked_elements (id integer PRIMARY KEY, fecha Date, Entrada_num integer, num_elemento, FOREIGN KEY (Entrada_num) REFERENCES Entradas(id), FOREIGN KEY (num_Elemento) REFERENCES Elemento(id));
