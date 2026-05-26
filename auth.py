from __future__ import annotations

import bcrypt
from typing import Optional

from models import Farmer
from storage import get_farmer_by_username


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def authenticate(username: str, password: str) -> Optional[Farmer]:
    farmer = get_farmer_by_username(username)
    if farmer is None:
        return None
    if not verify_password(password, farmer.password_hash):
        return None
    return farmer
