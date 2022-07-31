import logging
import threading
import socket
import time
import json

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.core import callback

from .helpers import BJFFinder, do_post, async_do_post
from .barneymanconst import (
    LISTENING_PORT,
    AUTH_TOKEN,
    BARNEYMAN_DOMAIN,
    BARNEYMAN_ID,
    SIGNAL_AUTHTOKEN_CHANGED,
)

_LOGGER = logging.getLogger(__name__)
DOMAIN = BARNEYMAN_DOMAIN


class BJFListener:
    def __init__(self, transport, hass, hostname):

        self._last_subscribed = None
        self._subscribe_timeout_minutes = 5
        self._hass = hass
        self._hostname = hostname
        self.entity_id = None
        self._finder = BJFFinder(hass, hostname)
        self._ordinal = 0
        self._run_listener = False

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
            # listen for 'device found'
            async_dispatcher_connect(
                hass, SIGNAL_AUTHTOKEN_CHANGED, self.resetSubscription
            )

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

    def resetSubscription(self, token):
        _LOGGER.debug("resetting subscription %s", token)
        self._last_subscribed = None

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

        # subscribe to the event
        self._hass.bus.async_listen("barneyman_" + self.entity_id, self.update_event)
        _LOGGER.info("listening to barneyman_%s event", self.entity_id)

    @callback
    def update_event(self, data):
        pass

    def subscribe(self, device_type):

        _LOGGER.debug(
            "Subscribing %s '%s' @ %s", device_type, self.entity_id, self._hostname
        )

        # we do this periodicall, in case the remote device has been rebooted
        # and forgotten we love them
        if self._last_subscribed is None or (
            (time.time() - self._last_subscribed) > self._subscribe_timeout_minutes * 60
        ):

            _LOGGER.info(
                "Subscribing %s '%s' '%s'", device_type, self.entity_id, self._hostname
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
            _LOGGER.debug("subscribe ignored")

    async def async_subscribe(self, device_type):

        _LOGGER.debug(
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
                "AsyncSubscribing %s '%s' '%s'",
                device_type,
                self.entity_id,
                self._hostname,
            )

            recipient = self.build_recipient(device_type)

            if recipient is None:
                return

            # advise the sensor we're listening
            _LOGGER.debug(
                async_do_post(
                    self._finder.get_ip_address(), "/json/listen", json.dumps(recipient)
                )
            )

            self._last_subscribed = time.time()

        else:
            _LOGGER.debug("subscribe ignored")

    def build_recipient(self, device_type: str) -> dict:

        if self.entity_id is None:
            return None

        recipient = {}
        if self.get_port() is not None:
            recipient["port"] = self.get_port()
        recipient[device_type] = self._ordinal
        #        recipient["endpoint"] = "/api/states/" + self.entity_id  # ie light.study_light
        recipient["endpoint"] = (
            "/api/events/barneyman_" + self.entity_id
        )  # ie light.study_light
        recipient["auth"] = self._hass.data[DOMAIN][
            AUTH_TOKEN
        ]  # created via config_flow
        recipient["instanceid"] = self._hass.data[DOMAIN][
            BARNEYMAN_ID
        ]  # created via config_flow

        _LOGGER.debug(recipient)

        return recipient
