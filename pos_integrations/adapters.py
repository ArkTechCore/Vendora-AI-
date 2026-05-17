from dataclasses import dataclass


@dataclass
class NormalizedSaleItem:
    external_item_id: str
    item_name: str
    quantity: str
    unit_price: str
    mapped_menu_item_id: int | None = None


@dataclass
class NormalizedSale:
    external_order_id: str
    business_date: str
    total_amount: str
    cash_amount: str
    card_amount: str
    items: list[NormalizedSaleItem]


class BasePOSAdapter:
    provider = "other"

    def __init__(self, connection):
        self.connection = connection

    def fetch_sales(self, start_date=None, end_date=None):
        raise NotImplementedError("Provider sync is configured but not implemented for this adapter yet.")


class CloverAdapter(BasePOSAdapter):
    provider = "clover"


class SquareAdapter(BasePOSAdapter):
    provider = "square"


class ToastAdapter(BasePOSAdapter):
    provider = "toast"


class CSVAdapter(BasePOSAdapter):
    provider = "csv"

    def fetch_sales(self, start_date=None, end_date=None):
        return []


class OtherAdapter(BasePOSAdapter):
    provider = "other"


ADAPTERS = {
    "clover": CloverAdapter,
    "square": SquareAdapter,
    "toast": ToastAdapter,
    "csv": CSVAdapter,
    "other": OtherAdapter,
}


def get_adapter(connection):
    return ADAPTERS.get(connection.provider, OtherAdapter)(connection)
