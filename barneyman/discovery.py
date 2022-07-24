import logging
from homeassistant.components import zeroconf
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import dispatcher_send
from zeroconf import ServiceListener
from .barneymanconst import (
    BARNEYMAN_SERVICES,
    BARNEYMAN_DOMAIN,
    SIGNAL_BARNEYMAN_DISCOVERED,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = BARNEYMAN_DOMAIN


class barneymanListener(ServiceListener):
    def __init__(self, hass: HomeAssistant):
        self.hosts = []
        self._hass = hass

    def add_service(self, zc: zeroconf.HaZeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        _LOGGER.info("zeroconfig added %s %s %s", type_, name, info)
        self.hosts.append(info)

        dispatcher_send(self._hass, SIGNAL_BARNEYMAN_DISCOVERED, info)

    def remove_service(self, zc: zeroconf.HaZeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        _LOGGER.warning("zeroconfig removed %s %s %s", type_, name, info)

    def update_service(self, zc: zeroconf.HaZeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        _LOGGER.warning("zeroconfig updated %s %s %s", type_, name, info)


class barneymanBrowser:
    def __init__(self, hass: HomeAssistant, zeroc: zeroconf.HaZeroconf):
        self._zeroc = zeroc
        self._browser = barneymanListener(hass)
        self._zeroc.add_service_listener(BARNEYMAN_SERVICES, self._browser)

    def getHosts(self):
        return self._browser.hosts
