import hashlib
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "imoveis-database"
    / "data"
    / "imoveis.db"
)
DATA_PATH = BASE_DIR / "data"
DRIVE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "majesto-drive"


def get_available_properties() -> list[sqlite3.Row]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM Imoveis WHERE ImovelStatus = 'Disponível'")
        return cursor.fetchall()


def get_property_details() -> list[dict]:
    """
    Retorna os imóveis próprios já no formato esperado pelo pipeline
    (mesma "forma" de um message_data vindo do WhatsApp), para que
    run_self_normalizer e o matcher funcionem sem tratamento especial.
    """
    properties_available = get_available_properties()
    properties_details = []
    for property in properties_available:
        description = property["Descricao"]
        if not description:
            continue
        properties_details.append(
            {
                "message_id": f"self-{hashlib.md5(description.encode()).hexdigest()}",
                "message": description,
                "author_name": "Majesto",
                "author_phone": None,
            }
        )
    return properties_details
