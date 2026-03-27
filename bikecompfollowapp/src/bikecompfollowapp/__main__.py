import locale
import os

try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    os.environ["LANG"] = "en_US.UTF-8"
    os.environ["LC_ALL"] = "en_US.UTF-8"
    try:
        locale.setlocale(locale.LC_ALL, "en_US.UTF-8")
    except locale.Error:
        locale.setlocale(locale.LC_ALL, "C.UTF-8")

from bikecompfollowapp.app import main

if __name__ == "__main__":
    main().main_loop()
