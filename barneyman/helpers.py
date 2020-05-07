import logging
import http.client
import json
from homeassistant.components.rest.sensor import RestData
from datetime import datetime, timedelta
import threading
import socket
from .barneymanconst import (
    BEACH_HEAD,
    DEVICES_ADDED,
    DISCOVERY_ROOT,
    DEVICES_FOUND,
    DEVICES_FOUND_SENSOR,
    LISTENING_PORT,
)


_LOGGER = logging.getLogger(__name__)
DOMAIN = "barneyman"


def doExists(hostname):
    jsonRet = doQuery(hostname, "/json/config", True, timeout=2)

    _LOGGER.info("doExists %s ", hostname)

    if jsonRet is None:
        return False

    if "version" not in jsonRet:
        return False

    return True


def doQuery(
    hostname, url, returnJson=False, httpmethod="GET", timeout=10, jsonBody=None
):
    try:
        _LOGGER.info("doQuery %s%s %s", hostname, url, httpmethod)
        conn = http.client.HTTPConnection(hostname, timeout=timeout)
        conn.request(url=url, method=httpmethod, body=jsonBody)
        r = conn.getresponse()
        if returnJson == True:
            jsonDone = r.read().decode("utf-8")
            _LOGGER.debug(jsonDone)
            r.close()
            conn.close()
            return json.loads(jsonDone)
        r.close()
        conn.close()
        return True
    except Exception as e:
        _LOGGER.error("barneyman doQuery exception %s %s %s", e, hostname, url)

    return None


def doPost(
    hostname, url, jsonBody=None, returnJson=False, httpmethod="POST", timeout=5
):
    return doQuery(hostname, url, returnJson, httpmethod, timeout, jsonBody)


class BJFDeviceInfo:
    def __init__(self, config):
        self._config = config

    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                ("mac", self._mac)
            },
            "name": self._config["name"],
            "manufacturer": "barneyman",
            "sw_version": self._config["version"],
        }


class BJFRestData(RestData):
    def __init__(
        self,
        method,
        resource,
        auth,
        headers,
        data,
        verify_ssl=False,
        httptimeout=5,
        cacheTimeout=20,
    ):
        RestData.__init__(
            self, method, resource, auth, headers, data, verify_ssl, httptimeout
        )

        self._lastUpdate = None
        self._cacheTimeout = cacheTimeout

    def resetCache(self):
        self._lastUpdate = None

    def update(self):

        if self._lastUpdate is None or self.data is None:
            _LOGGER.debug("BJFRestData - first update")
            RestData.update(self)
            self._lastUpdate = datetime.now()
        else:
            now = datetime.now()
            if (now - self._lastUpdate).total_seconds() > self._cacheTimeout:
                _LOGGER.debug(
                    "BJFRestData - data is stale %d secs",
                    (now - self._lastUpdate).total_seconds(),
                )
                RestData.update(self)
                self._lastUpdate = now
            else:
                _LOGGER.debug("BJFRestData - cache hit")


class BJFListener:
    def __init__(self, transport, hass):
        # spin up a thread, tell it the udp
        if transport == "tcp":
            self._listenThread = threading.Thread(target=self.tcpListener)
            _LOGGER.info("BJFListener called with tcp transport")
        elif transport == "udp":
            self._listenThread = threading.Thread(target=self.udpListener)
            _LOGGER.info("BJFListener called with udp transport")
        elif transport == "rest":
            self._listenThread = None
            self._port = 8123
            _LOGGER.info("BJFListener called with http transport")
        elif transport is None:            
            self._listenThread = None
            self._port = None
            _LOGGER.info("BJFListener called with none transport")
        else:
            self._port = None
            self._listenThread = None
            _LOGGER.error("BJFListener called with unknown transport %s", transport)

        self._transport = transport

        # get the available port
        if self._listenThread is not None:
            self._port = hass.data[DOMAIN][DISCOVERY_ROOT][LISTENING_PORT]
            # and inc it
            hass.data[DOMAIN][DISCOVERY_ROOT][LISTENING_PORT] = self._port + 1

    def udpListener(self):
        _LOGGER.debug("udpListener started port %d ...", self._port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # yes, a tuple '' is 'all local addrs'
        sock.bind(("", self._port))

        while self._runListener:
            data, addr = sock.recvfrom(1024)  # buffer size is 1024 bytes

            self.HandleIncomingPacket(data)

    def tcpListener(self):

        _LOGGER.debug("tcpListener started port %d ...", self._port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # yes, a tuple '' is 'all local addrs'
        sock.bind(("", self._port))

        sock.listen(2)

        while self._runListener:

            try:
                (clientsocket, address) = sock.accept()
                data = clientsocket.recv(1024)
                _LOGGER.debug("recv out %d", len(data))
                # deserialise
                _LOGGER.debug(data)

                clientsocket.close()

                self.HandleIncomingPacket(data)

            except Exception as e:
                _LOGGER.warning("exception %s", e)

    def HandleIncomingPacket(self, data):
        raise NotImplementedError()

    def getPort(self):
        return self._port

    async def async_added_to_hass(self):
        _LOGGER.info("async_added_to_hass %s", self.entity_id)
        # we don't get an entity id until we're added, so don't start the thread until we are
        if self._listenThread is not None:
            self._runListener = True
            self._listenThread.start()
        else:
            _LOGGER.info("async_added_to_hass %s No Transport Thread started", self.entity_id)

