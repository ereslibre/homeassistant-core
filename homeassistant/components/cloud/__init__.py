"""Component to integrate the Home Assistant cloud."""
import logging

import voluptuous as vol

from homeassistant.components.alexa import smart_home as alexa_sh
from homeassistant.components.google_assistant import const as ga_c
from homeassistant.const import (
    CONF_MODE, CONF_NAME, CONF_REGION, EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entityfilter
from homeassistant.loader import bind_hass
from homeassistant.util.aiohttp import MockRequest

from . import http_api
from .const import (
    CONF_ACME_DIRECTORY_SERVER, CONF_ALEXA, CONF_ALIASES,
    CONF_CLOUDHOOK_CREATE_URL, CONF_COGNITO_CLIENT_ID, CONF_ENTITY_CONFIG,
    CONF_FILTER, CONF_GOOGLE_ACTIONS, CONF_GOOGLE_ACTIONS_SYNC_URL,
    CONF_RELAYER, CONF_REMOTE_API_URL, CONF_SUBSCRIPTION_INFO_URL,
    CONF_USER_POOL_ID, DOMAIN, MODE_DEV, MODE_PROD)
from .prefs import CloudPreferences

REQUIREMENTS = ['hass-nabucasa==0.3']
DEPENDENCIES = ['http']

_LOGGER = logging.getLogger(__name__)

DEFAULT_MODE = MODE_PROD

SERVICE_REMOTE_CONNECT = 'remote_connect'
SERVICE_REMOTE_DISCONNECT = 'remote_disconnect'


ALEXA_ENTITY_SCHEMA = vol.Schema({
    vol.Optional(alexa_sh.CONF_DESCRIPTION): cv.string,
    vol.Optional(alexa_sh.CONF_DISPLAY_CATEGORIES): cv.string,
    vol.Optional(alexa_sh.CONF_NAME): cv.string,
})

GOOGLE_ENTITY_SCHEMA = vol.Schema({
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_ALIASES): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ga_c.CONF_ROOM_HINT): cv.string,
})

ASSISTANT_SCHEMA = vol.Schema({
    vol.Optional(CONF_FILTER, default=dict): entityfilter.FILTER_SCHEMA,
})

ALEXA_SCHEMA = ASSISTANT_SCHEMA.extend({
    vol.Optional(CONF_ENTITY_CONFIG): {cv.entity_id: ALEXA_ENTITY_SCHEMA}
})

GACTIONS_SCHEMA = ASSISTANT_SCHEMA.extend({
    vol.Optional(CONF_ENTITY_CONFIG): {cv.entity_id: GOOGLE_ENTITY_SCHEMA},
})

# pylint: disable=no-value-for-parameter
CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_MODE, default=DEFAULT_MODE):
            vol.In([MODE_DEV, MODE_PROD]),
        # Change to optional when we include real servers
        vol.Optional(CONF_COGNITO_CLIENT_ID): str,
        vol.Optional(CONF_USER_POOL_ID): str,
        vol.Optional(CONF_REGION): str,
        vol.Optional(CONF_RELAYER): str,
        vol.Optional(CONF_GOOGLE_ACTIONS_SYNC_URL): vol.Url(),
        vol.Optional(CONF_SUBSCRIPTION_INFO_URL): vol.Url(),
        vol.Optional(CONF_CLOUDHOOK_CREATE_URL): vol.Url(),
        vol.Optional(CONF_REMOTE_API_URL): vol.Url(),
        vol.Optional(CONF_ACME_DIRECTORY_SERVER): vol.Url(),
        vol.Optional(CONF_ALEXA): ALEXA_SCHEMA,
        vol.Optional(CONF_GOOGLE_ACTIONS): GACTIONS_SCHEMA,
    }),
}, extra=vol.ALLOW_EXTRA)


class CloudNotAvailable(HomeAssistantError):
    """Raised when an action requires the cloud but it's not available."""


@bind_hass
@callback
def async_is_logged_in(hass) -> bool:
    """Test if user is logged in."""
    return DOMAIN in hass.data and hass.data[DOMAIN].is_logged_in


@bind_hass
@callback
def async_active_subscription(hass) -> bool:
    """Test if user has an active subscription."""
    return \
        async_is_logged_in(hass) and not hass.data[DOMAIN].subscription_expired


@bind_hass
async def async_create_cloudhook(hass, webhook_id: str) -> str:
    """Create a cloudhook."""
    if not async_is_logged_in(hass):
        raise CloudNotAvailable

    hook = await hass.data[DOMAIN].cloudhooks.async_create(webhook_id)
    return hook['cloudhook_url']


@bind_hass
async def async_delete_cloudhook(hass, webhook_id: str) -> None:
    """Delete a cloudhook."""
    if DOMAIN not in hass.data:
        raise CloudNotAvailable

    await hass.data[DOMAIN].cloudhooks.async_delete(webhook_id)


def is_cloudhook_request(request):
    """Test if a request came from a cloudhook.

    Async friendly.
    """
    return isinstance(request, MockRequest)


async def async_setup(hass, config):
    """Initialize the Home Assistant cloud."""
    from hass_nabucasa import Cloud
    from .client import CloudClient

    # Process configs
    if DOMAIN in config:
        kwargs = dict(config[DOMAIN])
    else:
        kwargs = {CONF_MODE: DEFAULT_MODE}

    alexa_conf = kwargs.pop(CONF_ALEXA, None) or ALEXA_SCHEMA({})
    google_conf = kwargs.pop(CONF_GOOGLE_ACTIONS, None) or GACTIONS_SCHEMA({})

    prefs = CloudPreferences(hass)
    await prefs.async_initialize()

    websession = hass.helpers.aiohttp_client.async_get_clientsession()
    client = CloudClient(hass, prefs, websession, alexa_conf, google_conf)
    cloud = hass.data[DOMAIN] = Cloud(client, **kwargs)

    async def _startup(event):
        """Startup event."""
        await cloud.start()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _startup)

    async def _shutdown(event):
        """Shutdown event."""
        await cloud.stop()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown)

    async def _service_handler(service):
        """Handle service for cloud."""
        if service.service == SERVICE_REMOTE_CONNECT:
            await cloud.remote.connect()
        elif service.service == SERVICE_REMOTE_DISCONNECT:
            await cloud.remote.disconnect()

    hass.services.async_register(
        DOMAIN, SERVICE_REMOTE_CONNECT, _service_handler)
    hass.services.async_register(
        DOMAIN, SERVICE_REMOTE_DISCONNECT, _service_handler)

    await http_api.async_setup(hass)
    return True
