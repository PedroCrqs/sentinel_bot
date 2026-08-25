"""Adapter for the external/shared public.imoveis inventory contract.

The Sentinel consumes this schema and does not own or alter its tables. Rows
are converted here so the rest of the engine does not depend on physical
column names from the real-estate system.
"""


class InventoryAdapterError(ValueError):
    """Raised when an external inventory row cannot satisfy the domain contract."""


_AVAILABLE_STATUS = {"disponivel", "available"}
_UNAVAILABLE_STATUS = {
    "indisponivel",
    "unavailable",
    "vendido",
    "reservado",
    "inativo",
    "inactive",
}


def _required(value, field_name):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise InventoryAdapterError(
            f"Inventory field '{field_name}' is required"
        )
    return value


def _normalize_status(value):
    status = _required(value, "imovelstatus")
    normalized = str(status).strip().casefold()
    normalized = normalized.replace("í", "i").replace("ã", "a")
    if normalized in _AVAILABLE_STATUS:
        return "available"
    if normalized in _UNAVAILABLE_STATUS:
        return "unavailable"
    raise InventoryAdapterError(f"Unknown inventory status: {value!r}")


def map_inventory_row(row: dict) -> dict:
    """Map one physical ``public.imoveis`` row to the Sentinel contract."""
    property_id = _required(row.get("imovelid"), "imovelid")
    _required(row.get("bairroid"), "bairroid")
    neighborhood = _required(row.get("bairro_nome"), "bairroid/bairros.nome")

    return {
        "property_id": property_id,
        "property_type": _required(row.get("tipologia"), "tipologia"),
        "bedrooms": row.get("quartos"),
        "parking_spots": row.get("vagas"),
        "price": row.get("valor"),
        "area": row.get("metragem"),
        "sun_type": row.get("sol"),
        "neighborhood": neighborhood,
        "status": _normalize_status(row.get("imovelstatus")),
        "description": row.get("descricao"),
        "created_at": row.get("datacadastro"),
    }
