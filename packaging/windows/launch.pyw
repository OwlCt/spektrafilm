import os

os.environ.setdefault("QT_API", "pyside6")
os.environ.setdefault("PYTHONNOUSERSITE", "1")

from spektrafilm_gui.app import main

main()
