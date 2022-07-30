import logging
import asyncio
from datetime import timedelta

from homeassistant import auth
from homeassistant.helpers.dispatcher import dispatcher_send

from .barneymanconst import (
    DEVICES_LIGHT,
    DEVICES_SENSOR,
    DEVICES_CAMERA,
    LISTENING_PORT,
    AUTH_TOKEN,
    BARNEYMAN_DEVICES_SEEN,
    BARNEYMAN_DOMAIN,
    BARNEYMAN_USER_ID,
    BARNEYMAN_USER,
    BARNEYMAN_ID,
    BARNEYMAN_ANNOUNCE_CLIENT,
    SIGNAL_AUTHTOKEN_CHANGED,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = BARNEYMAN_DOMAIN


async def async_cleanupTokens(hass, user, client_name):

    _LOGGER.debug("async_cleanupTokens")

    tokensToKill = [
        user.refresh_tokens.get(token)
        for token in user.refresh_tokens
        if user.refresh_tokens.get(token).client_name == client_name
    ]

    for token in tokensToKill:
        _LOGGER.info("removing refresh_token '%s'", token.client_name)
        await hass.auth.async_remove_refresh_token(token)


async def async_prepareMemoryData(hass, myAuthToken, listeningPort, uniqueid):
    # create my 'i've created these' array
    hass.data[DOMAIN] = {
        AUTH_TOKEN: myAuthToken,
        LISTENING_PORT: listeningPort,
        BARNEYMAN_ID: uniqueid,
        BARNEYMAN_DEVICES_SEEN + DEVICES_LIGHT: [],
        BARNEYMAN_DEVICES_SEEN + DEVICES_SENSOR: [],
        BARNEYMAN_DEVICES_SEEN + DEVICES_CAMERA: [],
    }


# cribbed from https://github.com/home-assistant/core/blob/7cd68381f1d4f58930ffd631dfbfc7159d459832/tests/auth/test_init.py

llat_lifetime = timedelta(minutes=5)

# called by async_setup_entry
async def async_prepareUserAuth(hass, entry):

    _LOGGER.debug("async_prepareUserAuth")

    # clean up
    # # TODO kill this BEGIN
    # users = await hass.auth.async_get_users()
    # for user in users:
    #     if user.name.startswith("barneyman"):
    #         _LOGGER.warning("removing %s", user.name)
    #         await hass.auth.async_remove_user(user)
    # # TODO kill this END

    # get my (previous) userid, or None if this is first time
    my_user_id = entry.data.get(BARNEYMAN_USER_ID, None)
    my_user = None

    # get user if we have an id
    if my_user_id is not None:
        # oooh get my user
        my_user = await hass.auth.async_get_user(my_user_id)
        _LOGGER.info("found user %s", my_user)

    # bootstrap - create a user
    if my_user is None:
        # create standard user (sys users cant have LLAT)
        my_user = await hass.auth.async_create_user(
            BARNEYMAN_USER, group_ids=[auth.const.GROUP_ID_USER]
        )
        _LOGGER.info("created user %s with id %s", my_user.name, my_user.id)

        # update the config entry
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, BARNEYMAN_USER_ID: my_user.id}
        )

    # kill any of my refresh_tokens, that will invalidate any access tokens it has
    await async_cleanupTokens(hass, my_user, BARNEYMAN_ANNOUNCE_CLIENT)

    # if this user has refresh tokens (they shouldn't, above just killed them)
    if my_user.refresh_tokens:
        refresh_token = list(my_user.refresh_tokens.values())[0]
    else:
        # otherwise create one
        _LOGGER.info("creating refresh token '%s'", BARNEYMAN_ANNOUNCE_CLIENT)
        refresh_token = await hass.auth.async_create_refresh_token(
            user=my_user,
            client_name=BARNEYMAN_ANNOUNCE_CLIENT,
            token_type=auth.models.TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN,
            access_token_expiration=llat_lifetime,
        )

    async def async_remove_llat(offset_from_now: timedelta):
        _LOGGER.debug(
            "async_remove_llat sleeping for %ld secs", offset_from_now.total_seconds()
        )
        await asyncio.sleep(offset_from_now.total_seconds())
        _LOGGER.debug("async_remove_llat awake")
        await async_prepareUserAuth(hass, entry)

    # create a task that will sleep until the LLAT expires and remote it
    hass.async_create_task(async_remove_llat(llat_lifetime))

    # generate an LLAT
    _LOGGER.info("creating LLAT")
    llat = hass.auth.async_create_access_token(refresh_token)

    # TODO remove this log
    _LOGGER.debug("got token %s", llat)

    # TODO
    # revoke this refresh token on unload and/or restart so that the
    # LLAT is also revoked

    # get my uniqueid from the entry
    uuid = entry.unique_id

    # set my memory data up
    await async_prepareMemoryData(hass, llat, 49152, uuid)
    dispatcher_send(hass, SIGNAL_AUTHTOKEN_CHANGED, llat)
