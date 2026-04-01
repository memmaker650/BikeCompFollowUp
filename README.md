# PyiOS BikeCompFollowApp

# Guía para compilar con Briefcase y que funcione en MAC o en iOS.

# Instalar pyinstaller.
pip install -U pyinstaller

# Crear paquete App de OS X
pyinstaller --onefile --windowed --icon=Resources/bici2.icns BikeCompFollowApp.py
pyinstaller --windowed --name BikeCompFollowApp --icon=Resources/bici2.icns BikeCompFollowApp.py
pyinstaller --windowed --name BikeCompFollowApp --icon=Resources/bici2.icns --collect-all toga BikeCompFollowApp.py

# Otra opción : Briefcase
pip install briefcase

briefcase --version

briefcase create macOS

# Crear estructura del proyecto.
briefcase new

briefcase new macOS
briefcase new iOS


briefcase update
# Para rengerar todo.
briefcase clean # Para rengerar todo.
briefcase build macOS

briefcase clean
briefcase build macOS

# Activar Xcode
sudo xcode-select --switch /Applications/Xcode.app

# Generar el proyecto iOS
briefcase create iOS

briefcase build iOS

briefcase run iOS
briefcase run iOS -d "iPhone 17 Pro::iOS 26.4"

# Ubicación base de datos.
/Users/memmaker650/Library/Application Support/org.ejemplo.holamundo/

# Actualizar la compilación
briefcase update iOS && briefcase build iOS && briefcase run iOS -d "iPhone 17 Pro::iOS 26.4"


# Abrir ruta actual del Terminal
open .

# Abrir ruta pegada en el Terminal
open /ruta/a/tu/carpeta

# Abrir ruta pegada de un fichero desde el Terminal
open -R /ruta/a/tu/archivo.txt
