import base64
from datetime import datetime
import hashlib
import hmac
import json
import secrets
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse


from .exceptions import Unauthorized


class AuthInterface:
    _cookie_name: Optional[str] = None

    def __init__(self, server, *args, **kwargs):
        self._register_logout_route(server)

    def _register_logout_route(self, server: FastAPI):
        def logout(request: Request):
            response = RedirectResponse("/", status_code=303)
            if self._cookie_name is not None:
                response.delete_cookie(self._cookie_name)
            return response
        server.add_route("/logout", logout)

    def is_authenticated(self, request: Request):
        pass

    def get_tenant_id(self, request: Request):
        return None


class NoopAuth(AuthInterface):
    def __init__(self, server):
        super().__init__(server)

    def is_authenticated(self, request: Request):
        print("Noop auth")
        return True


class MultitenantAuth(AuthInterface):
    def __init__(self, server) -> None:
        self._cookie_name = "demo_auth"
        super().__init__(server)

    def is_authenticated(self, request: Request):
        cookie = request.cookies.get(self._cookie_name)
        if not cookie:
            session_id  = self._generate_session_id()
            response = RedirectResponse(request.url, status_code=303)
            response.set_cookie(self._cookie_name, session_id)
            raise Unauthorized(response)
        return True
    
    def get_tenant_id(self, request: Request):
        tenant_id = request.cookies[self._cookie_name]
        return tenant_id
    
    def _generate_session_id(self) -> str:
        return secrets.token_hex(24)


class PrivateInstanceAuth(AuthInterface):
    def __init__(self, password, secret_key, login_redirect: str, server: FastAPI):
        self._password = password
        self._cookie_name = "private_auth"
        self._signer = Signer(secret_key=secret_key)
        self._login_redirect = login_redirect
        self._register_login_route(server=server)
        super().__init__(server)

    def is_authenticated(self, request: Request):
        print("Checking private auth")
        if self._signer.check_token(request.cookies.get(self._cookie_name)):
            return True
        if request.url.path == self._login_redirect:
            return True
        next = request.url.path
        q = f"?next={next}"
        response = RedirectResponse(self._login_redirect + q, status_code=303)
        raise Unauthorized(response)

    def _register_login_route(self, server: FastAPI):
        async def login(request: Request):
            next = request.query_params["next"]
            if self._signer.check_token(request.cookies.get(self._cookie_name)):
                response = RedirectResponse(request.query_params["next"], status_code=303)
                return response
            action_url = self._login_redirect + f"?next={next}"
            if request.method == "GET":
                return HTMLResponse(
                    f"""
                    <form action="{action_url}" method="POST">
                        <label>Enter Password</label>
                        <input type="text" name="password" required />
                        <button type="submit">Login</button>
                    </form>
                    """
                    )
            else:
                form = await request.form()
                password = form["password"]
                if password != self._password:
                    return Response(status_code=401)
                else:
                    response = RedirectResponse(request.query_params["next"], status_code=303)
                    cookie = self._signer.generate_token()
                    response.set_cookie(self._cookie_name, cookie)
                    return response
        server.add_route(self._login_redirect, login, methods=["GET", "POST"])


class Signer:
    """NOTE: I know this is a horrible idea. I should just import jwt. 
    
    But this data isn't terribly sensitive, and this was more fun.
    """
    def __init__(self, secret_key: str):
        self._secret_key = secret_key

    def __signer(self) -> hmac.HMAC:
        return hmac.new(self._secret_key.encode("utf-8"), digestmod=hashlib.sha256)

    def generate_token(self) -> str:
        value: str = datetime.utcnow().isoformat()
        digest = self._digest_value(value)
        token_obj = {
            "value": value, 
            "digest": digest,
        }
        token_str = json.dumps(token_obj)
        token_bytes = token_str.encode("utf-8")
        return base64.b64encode(token_bytes).decode("utf-8")
    
    def check_token(self, token: str) -> bool:
        if token:
            token_bytes = base64.b64decode(token)
            token_str = token_bytes.decode("utf-8")
            token_obj = json.loads(token_str)
            value = token_obj["value"]
            digest = token_obj["digest"]
            expected_digest = self._digest_value(value)
            return hmac.compare_digest(digest, expected_digest)
        return False
    
    def _digest_value(self, value: str):
        signer = self.__signer()
        signer.update(value.encode("utf-8"))
        return signer.hexdigest()
    