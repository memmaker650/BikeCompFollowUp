"""Genera el icono de la app: cuadrado color crema con bordes redondeados y, detrás de la bici, una llave allen y un
tick cruzados.

Uso (desde bikecompfollowapp/):
    python3.14 tools/generar_icono.py tools/bici_icono_original.png /tmp/icono
    iconutil -c icns /tmp/icono/icon.iconset -o /tmp/icono/icon.icns
y copiar icon*.png e icon.icns a src/bikecompfollowapp/resources/.
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

BICI = Path(sys.argv[1]); SALIDA = Path(sys.argv[2])
N = 1024; SS = 4                       # se dibuja a 4x y se reduce: bordes suaves
W = N * SS
img = Image.new("RGBA", (W, W), (0, 0, 0, 0))

def s(v): return int(v * SS)

FONDO = (255, 244, 220, 255)        # crema / marfil (#FFF4DC)
BORDE = (232, 215, 178, 255)        # borde fino, del mismo tono algo más oscuro
# Sombra suave y cuadrado crema (marfil) con bordes redondeados (plantilla de iconos de macOS: 824 px, radio ~185)
x0, x1, radio = 100, 924, 185
sombra = Image.new("RGBA", (W, W), (0, 0, 0, 0))
ImageDraw.Draw(sombra).rounded_rectangle([s(x0), s(x0 + 12), s(x1), s(x1 + 12)], s(radio), fill=(0, 0, 0, 90))
sombra = sombra.filter(ImageFilter.GaussianBlur(s(14)))
img.alpha_composite(sombra)
d = ImageDraw.Draw(img)
d.rounded_rectangle([s(x0), s(x0), s(x1), s(x1)], s(radio), fill=FONDO,
                    outline=BORDE, width=s(5))

NEGRO = (20, 20, 20, 255)
def trazo(puntos, color, ancho, contorno=14):
    """Línea gruesa con extremos y codos redondeados y contorno negro (como la bici)."""
    for c, a in ((NEGRO, ancho + 2 * contorno), (color, ancho)):
        pts = [(s(x), s(y)) for x, y in puntos]
        d.line(pts, fill=c, width=s(a), joint="curve")
        for x, y in pts:
            r = s(a) / 2
            d.ellipse([x - r, y - r, x + r, y + r], fill=c)

# Llave allen (L) en la diagonal '\\': de la esquina de abajo a la derecha a la de arriba a la izquierda, donde
# hace el codo y el brazo corto mira hacia afuera (hacia el borde izquierdo). Barra hexagonal de acero: se ven
# tres de sus seis caras (clara, media y oscura) con aristas marcadas, un brillo especular y las bocas hexagonales.
import math
CARA_CLARA, CARA_MEDIA, CARA_OSCURA = (232, 236, 241, 255), (168, 177, 188, 255), (96, 104, 115, 255)
BRILLO, ARISTA = (255, 255, 255, 255), (58, 63, 70, 255)


def _vec(p0, p1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    largo = math.hypot(dx, dy)
    return dx / largo, dy / largo


def barra_hex(extremo, codo, otro_extremo, ancho):
    """Brazo de la llave de `extremo` a `codo`, vista de lado: contorno negro y tres caras en bandas a lo largo.
    En el codo se corta en inglete (por la bisectriz con el otro brazo, que va hacia `otro_extremo`), como una
    llave doblada de verdad. La cara clara es la que mira hacia arriba (luz desde arriba a la izquierda)."""
    ux, uy = _vec(extremo, codo)
    nx, ny = -uy, ux
    if ny > 0 or (ny == 0 and nx > 0):                 # normal hacia arriba / izquierda: ahí va la cara clara
        nx, ny = -nx, -ny
    vx, vy = _vec(codo, otro_extremo)
    bx, by = (-ux + vx), (-uy + vy)                    # bisectriz del codo
    largo_b = math.hypot(bx, by)
    bx, by = bx / largo_b, by / largo_b

    def en_codo(o):
        """Punto de la línea desplazada `o` (paralela al brazo) que cae sobre la bisectriz del codo."""
        px, py = codo[0] + nx * o, codo[1] + ny * o
        # px + t*ux = codo + k*b  ->  resolver t
        det = ux * (-by) - uy * (-bx)
        t = ((codo[0] - px) * (-by) - (codo[1] - py) * (-bx)) / det
        return px + ux * t, py + uy * t

    def banda(o0, o1, color):
        pts = [(extremo[0] + nx * o0, extremo[1] + ny * o0), en_codo(o0), en_codo(o1),
               (extremo[0] + nx * o1, extremo[1] + ny * o1)]
        d.polygon([(s(x), s(y)) for x, y in pts], fill=color)

    h = ancho / 2
    banda(-h - 13, h + 13, NEGRO)                      # contorno
    banda(h / 3, h, CARA_CLARA)                        # cara que da a la luz
    banda(-h / 3, h / 3, CARA_MEDIA)
    banda(-h, -h / 3, CARA_OSCURA)
    banda(h * 0.62, h * 0.80, BRILLO)                  # brillo especular
    for o in (-h / 3, h / 3):                          # aristas entre caras
        banda(o - 2.5, o + 2.5, ARISTA)


def boca_hex(centro, direccion, radio):
    """Extremo de la llave: hexágono (sección de la barra) con sus caras sombreadas."""
    ux, uy = direccion
    ang0 = math.atan2(uy, ux)
    pts = [(centro[0] + radio * math.cos(ang0 + math.pi / 6 + k * math.pi / 3),
            centro[1] + radio * math.sin(ang0 + math.pi / 6 + k * math.pi / 3)) for k in range(6)]
    grande = [(centro[0] + (x - centro[0]) * (radio + 13) / radio, centro[1] + (y - centro[1]) * (radio + 13) / radio)
              for x, y in pts]
    d.polygon([(s(x), s(y)) for x, y in grande], fill=NEGRO)
    colores = [CARA_MEDIA, CARA_CLARA, CARA_CLARA, CARA_MEDIA, CARA_OSCURA, CARA_OSCURA]
    for k in range(6):                                 # 6 triángulos desde el centro: aspecto de punta tallada
        tri = [centro, pts[k], pts[(k + 1) % 6]]
        d.polygon([(s(x), s(y)) for x, y in tri], fill=colores[k], outline=ARISTA)
    d.polygon([(s(x), s(y)) for x, y in pts], outline=ARISTA, width=s(3))


# Brazo corto a 90 grados del largo (como una llave allen de verdad), hacia el borde izquierdo
CODO, FIN_LARGO, FIN_CORTO, ANCHO_LLAVE = (262, 262), (800, 800), (165, 359), 64
barra_hex(FIN_CORTO, CODO, FIN_LARGO, ANCHO_LLAVE)       # brazo corto (hacia afuera)
barra_hex(FIN_LARGO, CODO, FIN_CORTO, ANCHO_LLAVE)       # brazo largo

boca_hex(FIN_LARGO, _vec(CODO, FIN_LARGO), ANCHO_LLAVE / 2 + 4)
boca_hex(FIN_CORTO, _vec(CODO, FIN_CORTO), ANCHO_LLAVE / 2 + 4)

# Tick verde en la otra diagonal '/', cruzando la llave: trazo corto abajo a la izquierda, largo hasta arriba
VERDE = (46, 170, 79, 255)
trazo([(205, 620), (335, 750), (800, 250)], VERDE, 76)

# Bici delante. El PNG original tiene restos de fondo blanco (un marco semitransparente y zonas opacas, también
# dentro del cuadro) que sobre el fondo crema se verían como parches: los píxeles casi blancos se vuelven
# transparentes. Los claros de la propia bici (manillar, horquilla) son azulados (#E2F9FF) y se quedan.
bici = Image.open(BICI).convert("RGBA")
px = bici.load()
for y in range(bici.size[1]):
    for x in range(bici.size[0]):
        r, g, b, a = px[x, y]
        borde = x in (0, bici.size[0] - 1) or y in (0, bici.size[1] - 1)
        if min(r, g, b) > 235 or (borde and min(r, g, b) > 150):   # en el borde hay además una línea gris
            px[x, y] = (r, g, b, 0)
lado = 600
bici = bici.resize((s(lado), s(lado)), Image.LANCZOS)
img.alpha_composite(bici, (s((N - lado) / 2), s((N - lado) / 2 + 50)))   # un poco por debajo del centro

final = img.resize((N, N), Image.LANCZOS)
SALIDA.mkdir(parents=True, exist_ok=True)
final.save(SALIDA / "icon-1024.png")
for tam, nombre in ((148, "icon.png"), (180, "icon-180.png"), (120, "icon-120.png"), (87, "icon-87.png")):
    final.resize((tam, tam), Image.LANCZOS).save(SALIDA / nombre)
# icon.icns de macOS
iconset = SALIDA / "icon.iconset"; iconset.mkdir(exist_ok=True)
for tam in (16, 32, 128, 256, 512):
    final.resize((tam, tam), Image.LANCZOS).save(iconset / f"icon_{tam}x{tam}.png")
    final.resize((tam * 2, tam * 2), Image.LANCZOS).save(iconset / f"icon_{tam}x{tam}@2x.png")
print("ok")
