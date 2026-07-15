"""
Configuración centralizada de logging para las pruebas de banco: registra en
consola y en un archivo rotativo los eventos relevantes del pipeline (conexión
serial, inicio/fin de captura, errores), sin acoplar cada módulo a los
detalles de formato o destino de los logs.
"""
import logging
from logging.handlers import RotatingFileHandler

CARPETA_LOGS = "logs"
ARCHIVO_LOG = "espirometro.log"


def configurar_logging(nivel=logging.INFO):
    import os

    os.makedirs(CARPETA_LOGS, exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    manejador_archivo = RotatingFileHandler(
        os.path.join(CARPETA_LOGS, ARCHIVO_LOG), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    manejador_archivo.setFormatter(formato)

    manejador_consola = logging.StreamHandler()
    manejador_consola.setFormatter(formato)

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    raiz.addHandler(manejador_archivo)
    raiz.addHandler(manejador_consola)
