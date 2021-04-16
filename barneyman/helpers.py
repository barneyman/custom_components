import logging
import http.client
import json
from homeassistant.components.rest.data import RestData
from datetime import datetime, timedelta
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
import threading
import socket
import time
import httpx
from .barneymanconst import (
    BARNEYMAN_HOST,
    LISTENING_PORT,
    AUTH_TOKEN
)

import asyncio


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

async def async_doPost(
    hostname, url, jsonBody=None, returnJson=False, httpmethod="POST", timeout=5
):
    return async_doQuery(hostname, url, returnJson, httpmethod, timeout, jsonBody)


async def async_doQuery(hostname, url, returnJson=False, httpmethod="GET", timeout=10, jsonBody=None):
#     """Get the latest data from REST service with provided method."""

    builtUrl="http://"+hostname+url

    _LOGGER.warning("barneyman async_doQuery to %s", builtUrl)

    async with httpx.AsyncClient() as client:
        response = await client.request(
            httpmethod,
            builtUrl,
            headers=None,
            params=None,
            auth=None,
            data=jsonBody,
            timeout=timeout,
        )
        if returnJson:
            _LOGGER.warning("barneyman async_doQuery returned  %s", response.text)
            return json.loads(response.text)
        else:
            return True



class BJFDeviceInfo:
    def __init__(self, config):
        self._config = config

    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (CONNECTION_NETWORK_MAC, self._mac)
            },
            "name": self._config["name"],
            "manufacturer": "barneyman",
            "sw_version": self._config["version"],
        }


class BJFChildDeviceInfo:
    def __init__(self, config, parent):
        self._config = config
        self._parent=parent.device_info["identifiers"]

    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (CONNECTION_NETWORK_MAC, self._mac)
            },
            "name": self._config["name"],
            "manufacturer": "barneyman",
            "sw_version": self._config["version"],
            "via_device": self._parent
        }






# this can be reused by a single sensor
# when it's async, the logic is a bit more comples


class BJFRestData(RestData):
    def __init__(
        self,
        hass,
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
            self, hass, method, resource, auth, headers,None, data, verify_ssl, httptimeout
        )

        self._lastUpdate = None
        self._cacheTimeout = cacheTimeout
        self._hass = hass
        self._isUpdating=False

    def resetCache(self):
        self._lastUpdate = None

    def updateRestData(self):
        # changed to async, update deprecated
        # RestData.update(self)
        try:
            asyncio.run_coroutine_threadsafe(RestData.async_update(self), self._hass.loop).result(5)
            self._lastUpdate = datetime.now()
        except Exception as e:
            _LOGGER.warning("updateRestData exception %s", e)


    async def async_updateRestData(self):
        # changed to async, update deprecated
        # RestData.update(self)
        await RestData.async_update(self)
        self._lastUpdate = datetime.now()


    async def async_update(self):

        doAnUpdate=False

        if self._lastUpdate is None or self.data is None:
            _LOGGER.debug("BJFRestData - first update")
            doAnUpdate=True
        else:
            now = datetime.now()
            if (now - self._lastUpdate).total_seconds() > self._cacheTimeout:
                _LOGGER.debug(
                    "BJFRestData - data is stale %d secs",
                    (now - self._lastUpdate).total_seconds(),
                )
                doAnUpdate=True
            else:
                _LOGGER.debug("BJFRestData - cache hit")

        if doAnUpdate:

            if self._isUpdating != True:
                self._isUpdating=True

                # changed to async, update deprecated
                await self.async_updateRestData()

                self._isUpdating=False
            
            else:
                _LOGGER.debug("BJFRestData - Waiting on another async ...")

                # just spin until it's been updated
                while self._isUpdating:
                    await asyncio.sleep(0.01)

    def update(self):

        if self._lastUpdate is None or self.data is None:
            _LOGGER.debug("BJFRestData - first update")
            # changed to async, update deprecated
            self.updateRestData()

        else:
            now = datetime.now()
            if (now - self._lastUpdate).total_seconds() > self._cacheTimeout:
                _LOGGER.debug(
                    "BJFRestData - data is stale %d secs",
                    (now - self._lastUpdate).total_seconds(),
                )
                self.updateRestData()
            else:
                _LOGGER.debug("BJFRestData - cache hit")


class BJFListener:
    def __init__(self, transport, hass):

        self._lastSubscribed=None
        self._subscribeTimeoutMinutes=5

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
            self._port = hass.data[DOMAIN][LISTENING_PORT]
            # and inc it
            hass.data[DOMAIN][LISTENING_PORT] = self._port + 1

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
                _LOGGER.warning("tcpListener exception %s", e)

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

    def subscribe(self, deviceType):

        # we do this periodicall, in case the remote device has been rebooted
        # and forgotten we love them
        if self._lastSubscribed is None or ((time.time()-self._lastSubscribed)>self._subscribeTimeoutMinutes*60):

            _LOGGER.debug("Subscribing %s '%s'",deviceType, self.entity_id)

            recipient = self.build_recipient(deviceType)

            # advise the sensor we're listening
            doPost(self._hostname, "/json/listen", json.dumps(recipient))

            self._lastSubscribed=time.time()

        else:
            _LOGGER.debug("subscribe ignored")


    async def async_subscribe(self, deviceType):

        # we do this periodicall, in case the remote device has been rebooted
        # and forgotten we love them
        if self._lastSubscribed is None or ((time.time()-self._lastSubscribed)>self._subscribeTimeoutMinutes*60):

            _LOGGER.debug("Subscribing %s '%s'",deviceType, self.entity_id)

            recipient = self.build_recipient(deviceType)

            # advise the sensor we're listening
            await async_doPost(self._hostname, "/json/listen", json.dumps(recipient))

            self._lastSubscribed=time.time()

        else:
            _LOGGER.debug("subscribe ignored")

    def build_recipient(self,deviceType):
        recipient = {}
        if self.getPort() is not None:
            recipient["port"] = self.getPort()
        recipient[deviceType] = self._ordinal
        recipient["endpoint"] = "/api/states/" + self.entity_id  #  light.study_light
        recipient["auth"] = self.hass.data[DOMAIN][AUTH_TOKEN]

        _LOGGER.debug(recipient)

        return recipient
