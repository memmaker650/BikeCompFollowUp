"""Traducciones de la interfaz, cargadas desde ``resources/translations_data.xml``.

Uso: ``t("menu.estadisticas")`` o ``t("menu.usuario", usuario="Ana")``. El idioma activo es
global a la app (``set_language``). Si falta un texto en el idioma activo se usa el del idioma
por defecto y, si tampoco existe, se muestra la propia clave para que el fallo sea visible.
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

XML_PATH = Path(__file__).parent / "resources" / "translations_data.xml"


@dataclass
class Language:
    code: str
    name: str
    flag: str
    texts: dict = field(default_factory=dict)


_languages: dict[str, Language] = {}   # en el orden del XML
_default = "es"
_current = "es"


def load(path=XML_PATH) -> None:
    """Lee el XML de traducciones. Se llama al arrancar; volver a llamarlo recarga."""
    global _default, _current
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        log.exception("No se pudo leer el fichero de traducciones %s", path)
        raise
    languages = {}
    for node in root.findall("language"):
        code = node.get("code")
        if not code:
            log.error("Bloque <language> sin atributo 'code' en %s; se ignora", path)
            continue
        lang = Language(code, node.get("name", code), node.get("flag", code))
        for text in node.findall("text"):
            key = text.get("key")
            if not key:
                log.warning("Texto sin 'key' en el idioma %s; se ignora", code)
                continue
            if key in lang.texts:
                log.warning("Clave duplicada %r en el idioma %s", key, code)
            lang.texts[key] = text.text or ""
        languages[code] = lang
    if not languages:
        raise ValueError(f"{path} no define ningún idioma")
    _languages.clear()
    _languages.update(languages)
    _default = root.get("default", next(iter(languages)))
    if _default not in _languages:
        log.warning("Idioma por defecto %r no definido; se usa %r", _default, next(iter(languages)))
        _default = next(iter(languages))
    _current = _default
    _check_missing_keys()
    log.info("Traducciones cargadas: %s (por defecto %s)", ", ".join(_languages), _default)


def _check_missing_keys() -> None:
    reference = set(_languages[_default].texts)
    for lang in _languages.values():
        missing = reference - set(lang.texts)
        if missing:
            log.warning("Al idioma %s le faltan %d textos: %s",
                        lang.code, len(missing), ", ".join(sorted(missing)))


def _ensure_loaded() -> None:
    if not _languages:
        load()


def languages() -> list[Language]:
    _ensure_loaded()
    return list(_languages.values())


def current() -> Language:
    _ensure_loaded()
    return _languages[_current]


def set_language(code: str) -> None:
    global _current
    _ensure_loaded()
    if code not in _languages:
        log.warning("Idioma desconocido %r; se mantiene %s", code, _current)
        return
    if code != _current:
        log.info("Idioma cambiado: %s -> %s", _current, code)
    _current = code


def next_language() -> Language:
    """Idioma siguiente en el orden del XML (vuelve al primero tras el último)."""
    codes = [lang.code for lang in languages()]
    return _languages[codes[(codes.index(_current) + 1) % len(codes)]]


def _format(key: str, text: str, params: dict) -> str:
    try:
        return text.format(**params)
    except (KeyError, IndexError, ValueError):
        log.error("Marcadores incorrectos en %r (%s): %r con %s", key, _current, text, params)
        return text


def t(key: str, **params) -> str:
    _ensure_loaded()
    text = _languages[_current].texts.get(key)
    if text is None:
        text = _languages[_default].texts.get(key)
        if text is None:
            log.error("Texto %r no definido en ningún idioma", key)
            return key
        log.warning("Texto %r no traducido a %s; se usa %s", key, _current, _default)
    return _format(key, text, params)


def default_text(key: str, **params) -> str:
    """Texto en el idioma por defecto, sea cual sea el activo (p. ej. para guardarlo en la BD)."""
    _ensure_loaded()
    text = _languages[_default].texts.get(key)
    if text is None:
        log.error("Texto %r no definido en el idioma por defecto", key)
        return key
    return _format(key, text, params)
