import logging
import http.client
import json
import threading
import socket
import time
from homeassistant.components.rest.data import RestData

# from datetime import datetime, timedelta
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
import httpx
from pydantic import NoneBytes
from sqlalchemy import false
from .barneymanconst import LISTENING_PORT, AUTH_TOKEN, BARNEYMAN_DOMAIN

# import asyncio


_LOGGER = logging.getLogger(__name__)
DOMAIN = BARNEYMAN_DOMAIN


def chopLocal(hostname):
    if str(hostname).endswith(".local."):
        hostname = hostname[: -len(".local.")]
    return hostname


def do_exists(hostname):

    json_ret = do_query(hostname, "/json/config", True, timeout=2)

    _LOGGER.info("do_exists %s ", hostname)

    if json_ret is None:
        return False

    if "version" not in json_ret:
        return False

    return True


async def async_do_exists(hostname):
    json_ret = await async_do_query(hostname, "/json/config", True, timeout=2)

    _LOGGER.info("do_exists %s ", hostname)

    if json_ret is None:
        return False

    if "version" not in json_ret:
        return False

    return True


def do_query(
    hostname, url, return_json=False, httpmethod="GET", timeout=10, json_body=None
):
    hostname = chopLocal(hostname)

    try:
        _LOGGER.info("do_query %s%s %s", hostname, url, httpmethod)
        conn = http.client.HTTPConnection(hostname, timeout=timeout)
        conn.request(url=url, method=httpmethod, body=json_body)
        response = conn.getresponse()
        if return_json:
            json_done = response.read().decode("utf-8")
            _LOGGER.debug(json_done)
            response.close()
            conn.close()
            return json.loads(json_done)
        response.close()
        conn.close()
        return True
    except Exception as exception:
        _LOGGER.error("barneyman do_query exception %s %s %s", exception, hostname, url)

    return None


def do_post(
    hostname, url, json_body=None, return_json=False, httpmethod="POST", timeout=5
):
    return do_query(hostname, url, return_json, httpmethod, timeout, json_body)


async def async_do_post(
    hostname, url, json_body=None, return_json=False, httpmethod="POST", timeout=5
):
    return async_do_query(hostname, url, return_json, httpmethod, timeout, json_body)


async def async_do_query(
    hostname, url, return_json=False, httpmethod="GET", timeout=30, json_body=None
):
    #     """Get the latest data from REST service with provided method."""
    hostname = chopLocal(hostname)

    built_url = "http://" + hostname + url

    _LOGGER.info("barneyman async_do_query to %s", built_url)

    try:

        async with httpx.AsyncClient() as client:
            response = await client.request(
                httpmethod,
                built_url,
                headers=None,
                params=None,
                auth=None,
                data=json_body,
                timeout=timeout,
            )
            response.raise_for_status()
            if return_json:
                _LOGGER.info("barneyman async_do_query returned  %s", response.text)
                return json.loads(response.text)
            else:
                return True

    except httpx.HTTPStatusError as exc:
        _LOGGER.error(
            "Error response '%s' while requesting %s.",
            str(exc.response.status_code),
            exc.request.url,
        )

    except httpx.RequestError as exc:
        _LOGGER.error(
            "An error '%s' occurred while requesting %s.", exc, exc.request.url
        )

    except Exception as exception:
        _LOGGER.error(
            "barneyman async_do_query exception '%s' host '%s' url '%s'",
            str(exception),
            hostname,
            url,
        )

    return None


class BJFDeviceInfo:
    def __init__(self, config, mac):
        self._config = config
        self._mac = mac

    # https://developers.home-assistant.io/docs/device_registry_index/
    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (CONNECTION_NETWORK_MAC, self._mac)
            },
            "name": self._config["name"],
            "model": self._config["version"].split("|")[0],
            "manufacturer": BARNEYMAN_DOMAIN,
            "sw_version": self._config["version"].split("|")[1],
            "configuration_url": "http://" + self._config["ip"],
        }


class BJFChildDeviceInfo:
    def __init__(self, config, mac, parent):
        self._config = config
        self._mac = mac
        self._parent = parent.device_info["identifiers"]

    # https://developers.home-assistant.io/docs/device_registry_index/
    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (CONNECTION_NETWORK_MAC, self._mac)
            },
            "name": self._config["name"],
            "manufacturer": BARNEYMAN_DOMAIN,
            "model": self._config["version"].split("|")[0],
            "sw_version": self._config["version"].split("|")[1],
            "via_device": self._parent,
        }


class BJFFinder:
    def __init__(self, hass, hostname) -> None:
        self._hass = hass
        self._hostname = hostname

    def get_ip_address(self):

        _LOGGER.debug("async_get_ip_address for %s", (self._hostname))

        return self._hostname


# this can be reused by a single sensor
# when it's async, the logic is a bit more complex


class BJFRestData(RestData, BJFFinder):
    def __init__(self, hass, hostname, method, auth, headers, data, verify_ssl=False):
        RestData.__init__(
            self, hass, method, None, auth, headers, None, data, verify_ssl
        )

        BJFFinder.__init__(self, hass, hostname)

        self._hass = hass
        self._hostname = hostname

    def get_url(self):

        endip = self.get_ip_address()
        if endip is None:
            return None

        url = "http://" + endip + "/json/state"

        _LOGGER.debug("url for %s", (url))

        return url

    async def async_bjfupdate(self):

        _LOGGER.debug("async_update for %s %s", self._hostname, str(self._verify_ssl))
        # change _resource ** in the parent **
        # super(BJFRestData,self)._resource=self.get_url()
        self._resource = self.get_url()

        await RestData.async_update(self)


class BJFListener:
    def __init__(self, transport, hass, hostname):

        self._last_subscribed = None
        self._subscribe_timeout_minutes = 5
        self._hass = hass
        self._hostname = hostname
        self.entity_id = None
        self._finder = BJFFinder(hass, hostname)
        self._ordinal = 0
        self._run_listener = false

        # spin up a thread, tell it the udp
        if transport == "tcp":
            self._listen_thread = threading.Thread(target=self.tcp_listener)
            _LOGGER.info("BJFListener called with tcp transport")
        elif transport == "udp":
            self._listen_thread = threading.Thread(target=self.udp_listener)
            _LOGGER.info("BJFListener called with udp transport")
        elif transport == "rest":
            self._listen_thread = None
            self._port = 8123
            _LOGGER.info("BJFListener called with http transport")
        elif transport is None:
            self._listen_thread = None
            self._port = None
            _LOGGER.info("BJFListener called with none transport")
        else:
            self._port = None
            self._listen_thread = None
            _LOGGER.error("BJFListener called with unknown transport %s", transport)

        self._transport = transport

        # get the available port
        if self._listen_thread is not None:
            self._port = hass.data[DOMAIN][LISTENING_PORT]
            # and inc it
            hass.data[DOMAIN][LISTENING_PORT] = self._port + 1

    def udp_listener(self):
        _LOGGER.info("udp_listener started port %d ...", self._port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # yes, a tuple '' is 'all local addrs'
        sock.bind(("", self._port))

        while self._run_listener:
            data, address = sock.recvfrom(1024)  # pylint: disable=unused-variable
            # buffer size is 1024 bytes

            self.handle_incoming_packet(data)

    def tcp_listener(self):

        _LOGGER.info("tcp_listener started port %d ...", self._port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # yes, a tuple '' is 'all local addrs'
        sock.bind(("", self._port))

        sock.listen(2)

        while self._run_listener:

            try:
                (
                    clientsocket,
                    address,  # pylint: disable=unused-variable
                ) = sock.accept()

                data = clientsocket.recv(1024)
                _LOGGER.debug("recv out %d", len(data))
                # deserialise
                _LOGGER.debug(data)

                clientsocket.close()

                self.handle_incoming_packet(data)

            except Exception as exception:
                _LOGGER.warning("tcp_listener exception %s", exception)

    def handle_incoming_packet(self, data):
        raise NotImplementedError()

    def get_port(self):
        return self._port

    async def async_added_to_hass(self):
        _LOGGER.info("async_added_to_hass %s", self.entity_id)
        # we don't get an entity id until we're added, so don't start the thread until we are
        if self._listen_thread is not None:
            self._run_listener = True
            self._listen_thread.start()
        else:
            _LOGGER.info(
                "async_added_to_hass %s No Transport Thread started", self.entity_id
            )

    def subscribe(self, device_type):

        _LOGGER.info(
            "Subscribing %s '%s' @ %s", device_type, self.entity_id, self._hostname
        )

        # we do this periodicall, in case the remote device has been rebooted
        # and forgotten we love them
        if self._last_subscribed is None or (
            (time.time() - self._last_subscribed) > self._subscribe_timeout_minutes * 60
        ):

            _LOGGER.info(
                "Proceeding %s '%s' '%s'", device_type, self.entity_id, self._hostname
            )

            recipient = self.build_recipient(device_type)

            if recipient is None:
                return

            # advise the sensor we're listening
            do_post(
                self._finder.get_ip_address(), "/json/listen", json.dumps(recipient)
            )

            self._last_subscribed = time.time()

        else:
            _LOGGER.info("subscribe ignored")

    async def async_subscribe(self, device_type):

        _LOGGER.info(
            "AsyncSubscribing %s '%s' @ '%s'",
            device_type,
            self.entity_id,
            self._hostname,
        )
        # we do this periodicall, in case the remote device has been rebooted
        # and forgotten we love them
        if self._last_subscribed is None or (
            (time.time() - self._last_subscribed) > self._subscribe_timeout_minutes * 60
        ):

            _LOGGER.info(
                "Proceeding %s '%s' '%s'", device_type, self.entity_id, self._hostname
            )

            recipient = self.build_recipient(device_type)

            if recipient is None:
                return

            # advise the sensor we're listening
            async_do_post(
                self._finder.get_ip_address(), "/json/listen", json.dumps(recipient)
            )

            self._last_subscribed = time.time()

        else:
            _LOGGER.info("subscribe ignored")

    def build_recipient(self, device_type):

        if self.entity_id is None:
            return None

        recipient = {}
        if self.get_port() is not None:
            recipient["port"] = self.get_port()
        recipient[device_type] = self._ordinal
        recipient["endpoint"] = "/api/states/" + self.entity_id  #  light.study_light
        recipient["auth"] = self._hass.data[DOMAIN][AUTH_TOKEN]

        _LOGGER.debug(recipient)

        return recipient
