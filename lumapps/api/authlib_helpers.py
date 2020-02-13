import typing

from httpx import Auth, Client
from httpx.models import Request, Response
from authlib.oauth2.rfc7521 import AssertionClient as _AssertionClient
from authlib.oauth2.rfc7523 import JWTBearerGrant
from authlib.integrations.httpx_client.utils import extract_client_kwargs

from authlib.common.urls import url_decode
from authlib.oauth2.client import OAuth2Client as _OAuth2Client
from authlib.oauth2.auth import ClientAuth, TokenAuth
from authlib.integrations.httpx_client.utils import HTTPX_CLIENT_KWARGS, rebuild_request
from authlib.integrations.base_client import (
    OAuthError,
    InvalidTokenError,
    MissingTokenError,
    UnsupportedTokenTypeError,
)


__all__ = ["AssertionClient", "OAuth2Client"]


class OAuth2Auth(Auth, TokenAuth):
    """Sign requests for OAuth 2.0, currently only bearer token is supported."""

    requires_request_body = True

    def auth_flow(self, request: Request) -> typing.Generator[Request, Response, None]:
        try:
            url, headers, body = self.prepare(
                str(request.url), request.headers, request.content
            )
            yield rebuild_request(request, url, headers, body)
        except KeyError as error:
            description = "Unsupported token_type: {}".format(str(error))
            raise UnsupportedTokenTypeError(description=description)


class OAuth2ClientAuth(Auth, ClientAuth):
    requires_request_body = True

    def auth_flow(self, request: Request) -> typing.Generator[Request, Response, None]:
        url, headers, body = self.prepare(
            request.method, str(request.url), request.headers, request.content
        )
        yield rebuild_request(request, url, headers, body)


class AssertionClient(_AssertionClient, Client):
    token_auth_class = OAuth2Auth
    JWT_BEARER_GRANT_TYPE = JWTBearerGrant.GRANT_TYPE
    ASSERTION_METHODS = {
        JWT_BEARER_GRANT_TYPE: JWTBearerGrant.sign,
    }
    DEFAULT_GRANT_TYPE = JWT_BEARER_GRANT_TYPE

    def __init__(  # nosec
        self,
        token_endpoint,
        issuer,
        subject,
        audience=None,
        grant_type=None,
        claims=None,
        token_placement="header",
        scope=None,
        **kwargs
    ):

        client_kwargs = extract_client_kwargs(kwargs)
        Client.__init__(self, **client_kwargs)

        _AssertionClient.__init__(
            self,
            session=None,
            token_endpoint=token_endpoint,
            issuer=issuer,
            subject=subject,
            audience=audience,
            grant_type=grant_type,
            claims=claims,
            token_placement=token_placement,
            scope=scope,
            **kwargs
        )

    def request(self, method, url, withhold_token=False, auth=None, **kwargs):
        """Send request with auto refresh token feature."""
        if not withhold_token and auth is None:
            if not self.token or self.token.is_expired():
                self.refresh_token()

            auth = self.token_auth
        return super(AssertionClient, self).request(method, url, auth=auth, **kwargs)

    def _refresh_token(self, data):
        resp = self.request("POST", self.token_endpoint, data=data, withhold_token=True)
        self.token = resp.json()
        return self.token


class OAuth2Client(_OAuth2Client, Client):
    SESSION_REQUEST_PARAMS = HTTPX_CLIENT_KWARGS

    client_auth_class = OAuth2ClientAuth
    token_auth_class = OAuth2Auth

    def __init__(  # nosec
        self,
        client_id=None,
        client_secret=None,
        token_endpoint_auth_method=None,
        revocation_endpoint_auth_method=None,
        scope=None,
        redirect_uri=None,
        token=None,
        token_placement="header",
        update_token=None,
        **kwargs
    ):

        # extract httpx.Client kwargs
        client_kwargs = self._extract_session_request_params(kwargs)
        Client.__init__(self, **client_kwargs)

        _OAuth2Client.__init__(
            self,
            session=None,
            client_id=client_id,
            client_secret=client_secret,
            token_endpoint_auth_method=token_endpoint_auth_method,
            revocation_endpoint_auth_method=revocation_endpoint_auth_method,
            scope=scope,
            redirect_uri=redirect_uri,
            token=token,
            token_placement=token_placement,
            update_token=update_token,
            **kwargs
        )

    @staticmethod
    def handle_error(error_type, error_description):
        raise OAuthError(error_type, error_description)

    def request(self, method, url, withhold_token=False, auth=None, **kwargs):
        if not withhold_token and auth is None:
            if not self.token:
                raise MissingTokenError()

            if self.token.is_expired():
                self.ensure_active_token(**kwargs)

            auth = self.token_auth

        return super(OAuth2Client, self).request(method, url, auth=auth, **kwargs)

    def ensure_active_token(self, **kwargs):
        refresh_token = self.token.get("refresh_token")
        url = self.metadata.get("token_endpoint")
        if refresh_token and url:
            self.refresh_token(url, refresh_token=refresh_token, **kwargs)
        elif self.metadata.get("grant_type") == "client_credentials":
            access_token = self.token["access_token"]
            token = self.fetch_token(url, grant_type="client_credentials", **kwargs)
            if self.update_token:
                self.update_token(token, access_token=access_token)
        else:
            raise InvalidTokenError()

    def _fetch_token(
        self, url, body="", headers=None, auth=None, method="POST", **kwargs
    ):
        if method.upper() == "POST":
            resp = self.post(
                url, data=dict(url_decode(body)), headers=headers, auth=auth, **kwargs
            )
        else:
            if "?" in url:
                url = "&".join([url, body])
            else:
                url = "?".join([url, body])
            resp = self.get(url, headers=headers, auth=auth, **kwargs)

        for hook in self.compliance_hook["access_token_response"]:
            resp = hook(resp)

        return self.parse_response_token(resp.json())

    def _refresh_token(
        self, url, refresh_token=None, body="", headers=None, auth=None, **kwargs
    ):
        resp = self.post(
            url, data=dict(url_decode(body)), headers=headers, auth=auth, **kwargs
        )

        for hook in self.compliance_hook["refresh_token_response"]:
            resp = hook(resp)

        token = self.parse_response_token(resp.json())
        if "refresh_token" not in token:
            self.token["refresh_token"] = refresh_token

        if self.update_token:
            self.update_token(self.token, refresh_token=refresh_token)

        return self.token

    def _revoke_token(self, url, body=None, auth=None, headers=None, **kwargs):
        return self.post(
            url, data=dict(url_decode(body)), headers=headers, auth=auth, **kwargs
        )
