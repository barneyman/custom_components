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
        _LOGGER.info("zeroconfig  found %s %s %s", type_, name, zc)
        info = zc.get_service_info(type_, name)
        _LOGGER.info("%s", info)
        self.hosts.append(info)

        dispatcher_send(self._hass, SIGNAL_BARNEYMAN_DISCOVERED, info)

    def remove_service(self, zc: zeroconf.HaZeroconf, type_: str, name: str) -> None:
        pass

    def update_service(self, zc: zeroconf.HaZeroconf, type_: str, name: str) -> None:
        pass


class barneymanBrowser:
    def __init__(self, hass: HomeAssistant, zeroc: zeroconf.HaZeroconf):
        self._zeroc = zeroc
        self._browser = barneymanListener(hass)
        self._zeroc.add_service_listener(BARNEYMAN_SERVICES, self._browser)

    def getHosts(self):
        return self._browser.hosts
