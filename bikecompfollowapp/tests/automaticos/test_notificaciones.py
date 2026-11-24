"""Tests de las notificaciones (sin lanzar notificaciones reales)."""

import subprocess

import pytest

from bikecompfollowapp import notificaciones


@pytest.fixture
def osascript(monkeypatch):
    llamadas = []
    monkeypatch.setattr(notificaciones.sys, "platform", "darwin")
    monkeypatch.setattr(notificaciones.subprocess, "run", lambda cmd, **kw: llamadas.append(cmd))
    return llamadas


def test_macos_usa_osascript_y_no_plyer(osascript, monkeypatch):
    monkeypatch.setattr(notificaciones, "_notificar_plyer", lambda *a: pytest.fail("plyer no funciona en macOS"))
    assert notificaciones.notificar("Título", "Mensaje") is True
    assert osascript == [["osascript", "-e", 'display notification "Mensaje" with title "Título"']]


def test_comillas_y_barras_se_escapan(osascript):
    notificaciones.notificar('Di "hola"', "a\\b")
    assert osascript[0][2] == 'display notification "a\\\\b" with title "Di \\"hola\\""'


def test_otras_plataformas_usan_plyer(monkeypatch):
    monkeypatch.setattr(notificaciones.sys, "platform", "win32")
    usadas = []
    monkeypatch.setattr(notificaciones, "_notificar_plyer", lambda *a: usadas.append(a))
    assert notificaciones.notificar("T", "M") is True
    assert usadas == [("T", "M", "BikeCompFollowApp")]


@pytest.mark.parametrize("error", [
    NotImplementedError("No usable implementation found!"),   # el error de plyer
    ImportError("no plyer"),
])
def test_sin_implementacion_no_rompe_la_app(monkeypatch, error):
    monkeypatch.setattr(notificaciones.sys, "platform", "ios")

    def falla(*a):
        raise error

    monkeypatch.setattr(notificaciones, "_notificar_plyer", falla)
    assert notificaciones.notificar("T", "M") is False


def test_osascript_falla_no_rompe_la_app(monkeypatch):
    monkeypatch.setattr(notificaciones.sys, "platform", "darwin")

    def falla(*a, **kw):
        raise subprocess.CalledProcessError(1, "osascript")

    monkeypatch.setattr(notificaciones.subprocess, "run", falla)
    assert notificaciones.notificar("T", "M") is False
