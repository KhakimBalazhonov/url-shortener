from sqids import Sqids

from app.core.config import get_settings

settings = get_settings()

# Настраивает генератор коротких кодов: алфавит (набор допустимых символов) и минимальную длину 6 символов
sqids = Sqids(alphabet=settings.SQIDS_ALPHABET.get_secret_value(), min_length=6)


def encode_id(db_id: int) -> str:
    """Преобразует ID записи из БД, например 123, в строку вроде '86Rf07' (Base62)"""
    return sqids.encode([db_id])
