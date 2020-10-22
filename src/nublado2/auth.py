"""Authenticator for the Nublado 2 instantiation of JupyterHub."""

from __future__ import annotations

from typing import TYPE_CHECKING

from jupyterhub.auth import Authenticator
from jupyterhub.handlers import BaseHandler
from jupyterhub.utils import url_path_join
from tornado import web

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Tuple, Type, Union

    from jupyterhub.app import JupyterHub
    from tornado.web import RequestHandler

    Route = Tuple[str, Type[BaseHandler]]


class GafaelfawrAuthenticator(Authenticator):
    """JupyterHub authenticator using Gafaelfawr headers.

    Rather than implement any authentication logic inside of JupyterHub,
    authentication is done via an ``auth_request`` handler at the NGINX
    level.  JupyterHub then only needs to read the authentication results from
    the headers of the incoming request.

    To support this, register a custom login handler that will parse the
    headers and enable ``auto_login``.  ``authenticate``, which handles the
    results of a form submission to the normal ``/login`` route, is not used
    in this model.

    Notes
    -----
    A possible alternative implementation that seems to be supported by the
    JupyterHub code would be to not override ``login_url``, set
    ``auto_login``, and then override ``get_authenticated_user`` in the
    authenticator to read authentication information directly from the request
    headers.  This would avoid a redirect and the code appears to be there to
    support it, but the current documentation (as of 1.1.0) explicitly says to
    not override ``get_authenticated_user``.

    This implementation therefore takes the well-documented path on the theory
    that an extra redirect is a small price to pay for staying within the
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

    This retrieves authentication information from the headers, constructs an
    authentication state, and then redirects to the next URL.
    """

    async def get(self) -> None:
        """Handle GET to the login page."""
        username = self.request.headers.get("X-Auth-Request-User")
        if not username:
            raise web.HTTPError(401)

        # Construct an auth_info structure with the additional details about
        # the user.
        groups_str = self.request.headers.get("X-Auth-Request-Groups")
        if groups_str:
            groups = [g.strip() for g in groups_str.split(",")]
        else:
            groups = []
        uid = self.request.headers.get("X-Auth-Request-Uid")
        auth_info = {
            "name": username,
            "auth_state": {
                "uid": int(uid) if uid else None,
                "token": self.request.headers.get("X-Auth-Request-Token"),
                "groups": groups,
            },
        }

        # Store the ancillary user information in the user database and create
        # or return the user object.  This call is unfortunately undocumented,
        # but it's what BaseHandler calls to record the auth_state information
        # after a form-based login.  Hopefully this is a stable interface.
        user = await self.auth_to_user(auth_info)

        # Tell JupyterHub to set its login cookie (also undocumented).
        self.set_login_cookie(user)

        # Redirect to the next URL.
        self.redirect(self.get_next_url(user))
