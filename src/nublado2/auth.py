"""Authenticator for the Nublado 2 instantiation of JupyterHub."""

from __future__ import annotations

from typing import TYPE_CHECKING

from jupyterhub.auth import Authenticator
from jupyterhub.handlers import BaseHandler
from jupyterhub.utils import url_path_join
from tornado import web

from nublado2.nublado_config import NubladoConfig
from nublado2.options import session

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Tuple, Type, Union

    from jupyterhub.app import JupyterHub
    from tornado.httputil import HTTPHeaders
    from tornado.web import RequestHandler

    Route = Tuple[str, Type[BaseHandler]]


class GafaelfawrAuthenticator(Authenticator):
    """JupyterHub authenticator using Gafaelfawr headers.

    Rather than implement any authentication logic inside of JupyterHub,
    authentication is done via an ``auth_request`` handler made by the NGINX
    ingress controller.  JupyterHub then only needs to read the authentication
    results from the headers of the incoming request.

    Normally, the authentication flow for JupyterHub is to send the user to
    ``/hub/login`` and display a login form.  The submitted values to the form
    are then passed to the ``authenticate`` method of the authenticator, which
    is responsible for returning authentication information for the user.
    That information is then stored in an authentication session and the user
    is redirected to whatever page they were trying to go to.

    We however do not want to display an interactive form, since the
    authentication information is already present in the headers.  We just
    need JupyterHub to read it.

    The documented way to do this is to register a custom login handler on a
    new route not otherwise used by JupyterHub, and then enable the
    ``auto_login`` setting on the configured authenticator.  This setting
    tells the built-in login page to, instead of presenting a login form,
    redirect the user to whatever URL is returned by ``login_url``.  In our
    case, this will be ``/hub/gafaelfawr/login``, served by the
    `GafaelfawrLoginHandler` defined below.  This simple handler will read the
    token from the header, retrieve its metadata, create the session and
    cookie, and then make the same redirect call the login form handler would
    normally have made after the ``authenticate`` method returned.

    In this model, the ``authenticate`` method is not used, since the login
    handler never receives a form submission.

    Notes
    -----
    A possible alternative implementation that seems to be supported by the
    JupyterHub code would be to not override ``login_url``, set
    ``auto_login``, and then override ``get_authenticated_user`` in the
    authenticator to read authentication information directly from the request
    headers.  It looks like an authenticator configured in that way would
    authenticate the user "in place" in the handler of whatever page the user
    first went to, without any redirects.  This would be slightly more
    efficient and the code appears to handle it, but the current documentation
    (as of 1.1.0) explicitly says to not override ``get_authenticated_user``.

    This implementation therefore takes the well-documented path of a new
    handler and a redirect from the built-in login handler, on the theory that
    a few extra redirects is a small price to pay for staying within the
    supported and expected interface.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # Automatically log in rather than prompting the user with a link.
        self.auto_login = True

        # Enable secure storage of auth state, which we'll use to stash the
        # user's token and pass it to the spawned pod.
        self.enable_auth_state = True

        # Refresh the auth state before spawning to ensure we have the user's
        # most recent token and group information.
        self.refresh_pre_spawn = True

    async def authenticate(
        self, handler: RequestHandler, data: Dict[str, str]
    ) -> Optional[Union[str, Dict[str, Any]]]:
        """Login form authenticator.

        This is not used in our authentication scheme.
        """
        raise NotImplementedError()

    def get_handlers(self, app: JupyterHub) -> List[Route]:
        """Register the header-only login handler."""
        return [("/gafaelfawr/login", GafaelfawrLoginHandler)]

    def login_url(self, base_url: str) -> str:
        """Override the login URL.

        This must be changed to something other than ``/login`` to trigger
        correct behavior when ``auto_login`` is set to true (as it is in our
        case).
        """
        return url_path_join(base_url, "gafaelfawr/login")


class GafaelfawrLoginHandler(BaseHandler):
    """Login handler for Gafaelfawr authentication.

    This retrieves the authentication token from the headers, makes an API
    call to get its metadata, constructs an authentication state, and then
    redirects to the next URL.
    """

    async def get(self) -> None:
        """Handle GET to the login page."""
        auth_info = await self._build_auth_info(self.request.headers)

        # Store the ancillary user information in the user database and create
        # or return the user object.  This call is unfortunately undocumented,
        # but it's what BaseHandler calls to record the auth_state information
        # after a form-based login.  Hopefully this is a stable interface.
        user = await self.auth_to_user(auth_info)

        # Tell JupyterHub to set its login cookie (also undocumented).
        self.set_login_cookie(user)

        # Redirect to the next URL, which is under the control of JupyterHub
        # and opaque to the authenticator.  In practice, it will normally be
        # whatever URL the user was trying to go to when JupyterHub decided
        # they needed to be authenticated.
        self.redirect(self.get_next_url(user))

    @staticmethod
    async def _build_auth_info(headers: HTTPHeaders) -> Dict[str, Any]:
        """Construct the authentication information for a user.

        Retrieve the token from the headers, use that token to retrieve the
        metadata for the token, and use that data to build an auth info dict
        in the format expected by JupyterHub.  This is in a separate method so
        that it can be unit-tested.
        """
        token = headers.get("X-Auth-Request-Token")
        if not token:
            raise web.HTTPError(401, "No request token")

        # Retrieve the token metadata.
        base_url = NubladoConfig().base_url
        if not base_url:
            raise web.HTTPError(500, "base_url not set in configuration")
        api_url = url_path_join(base_url, "/auth/analyze")
        resp = await session.post(api_url, data={"token": token})
        if resp.status != 200:
            raise web.HTTPError(500, "Cannot reach token analysis API")
        try:
            analyze_data = await resp.json()
            valid = analyze_data["token"]["valid"]
            token_data = analyze_data["token"].get("data")
        except Exception:
            raise web.HTTPError(500, "Cannot analyze token")
        if not valid or not token_data or "uid" not in token_data:
            raise web.HTTPError(403, "Request token is invalid")

        # Construct an auth_info structure with the additional details about
        # the user.  We want only the groups that have GIDs (NCSA generates
        # some groups that have names but no GID).
        uid = token_data.get("uidNumber")
        try:
            groups = [
                {"name": g["name"], "id": int(g["id"])}
                for g in token_data.get("isMemberOf", [])
                if "id" in g
            ]
        except Exception:
            raise web.HTTPError(403, "Token data is not in a valid format")
        return {
            "name": token_data["uid"],
            "auth_state": {
                "uid": int(uid) if uid else None,
                "token": token,
                "groups": groups,
            },
        }
