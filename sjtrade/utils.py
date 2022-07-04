import math
import time
import datetime
from typing import List, Union


def price_ceil(price: float) -> float:
    logp = math.floor(math.log10(price))
    quinary = ((price / 10**logp) // 5) if logp >= 1 else 1
    n = min(10 ** (3 - logp - quinary), 100)
    return round(math.ceil(price * n + (5 - (price * n % 5)) * (1 - quinary)) / n, 2)


def price_floor(price: float) -> float:
    logp = math.floor(math.log10(price))
    quinary = ((price / 10**logp) // 5) if logp >= 1 else 1
    n = min(10 ** (3 - logp - quinary), 100)
    return round(math.floor(price * n - ((price * n % 5) * (1 - quinary))) / n, 2)


def price_round(price: float, up: bool = False):
    roudnf = math.ceil if up else math.floor
    logp = math.floor(math.log10(price))
    quinary = ((price / 10**logp) // 5) if logp >= 1 else 1
    n = min(10 ** (3 - logp - quinary), 100)
    return round(
        roudnf(price * n + ((5 * int(up) - (price * n % 5)) * (1 - quinary))) / n, 2
    )


def quantity_split(quantity: float, threshold: int) -> List[int]:
    return [threshold if quantity > 0 else -threshold] * (
        abs(quantity) // threshold
    ) + [
        (abs(quantity) % threshold) * (1 if quantity > 0 else -1),
    ]


def sleep_until(t: Union[datetime.time, tuple]) -> None:
    if isinstance(t, tuple):
        t = datetime.time(*t)
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    d = datetime.timedelta(days=1) if now.hour > 13 else datetime.timedelta(days=0)
    until_time = (
        datetime.datetime(now.year, now.month, now.day, t.hour, t.minute, t.second) + d
    )
    delta = until_time - now
    delta_sec = delta.total_seconds()
    if delta_sec > 0:
        time.sleep(delta_sec)
