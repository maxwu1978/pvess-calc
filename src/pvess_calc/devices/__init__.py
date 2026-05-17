"""Device datasheet registry."""
from .batteries import BATTERIES, BATTERY_PRICES_USD, get_battery
from .inverters import INVERTERS, INVERTER_PRICES_USD, get_inverter
from .modules import MODULES, get_module
from .optimizers import OPTIMIZERS, get_optimizer

__all__ = [
    "MODULES", "INVERTERS", "BATTERIES", "OPTIMIZERS",
    "INVERTER_PRICES_USD", "BATTERY_PRICES_USD",
    "get_module", "get_inverter", "get_battery", "get_optimizer",
]
