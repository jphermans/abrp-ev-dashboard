#!/usr/bin/env python3
"""
Patch the CarConnectivity VW connector for the May/August 2026 auth change.

VW changed:
1. BFF authorize endpoint → 403
2. BFF token endpoint → broken
3. VW Android app User-Agent headers → 400 on Auth0 login pages
"""
import sys
import hashlib
import base64
import re
from pathlib import Path


def patch_we_connect_session(filepath: Path) -> bool:
    """Patch we_connect_session.py to bypass the dead BFF endpoints."""
    src = filepath.read_text()
    changed = False

    # 0. Ensure required imports are present
    if "import base64" not in src:
        src = src.replace("import json", "import base64\nimport json", 1)
        changed = True
    if "import hashlib" not in src:
        src = src.replace("import json", "import hashlib\nimport json", 1)
        changed = True

    # 1. Fix authorization_url() — bypass BFF, use identity.vwgroup.io directly with PKCE
    if "emea.bff.cariad.digital/user-login/v1/authorize" in src:
        old_block = """        auth_url: str = add_params_to_uri('https://emea.bff.cariad.digital/user-login/v1/authorize', params)
        try_login_response: requests.Response = self.get(auth_url, allow_redirects=False, access_type=AccessType.NONE)  # pyright: ignore reportCallIssue
        if try_login_response.status_code != requests.codes['see_other'] or 'Location' not in try_login_response.headers:
            raise AuthenticationError('Authorization URL could not be fetched due to WeConnect failure')
        # Redirect is URL to authorize
        redirect: str = try_login_response.headers['Location']
        query: str = urlparse(redirect).query
        query_params: Dict[str, str] = dict(parse_qsl(query))
        if 'state' in query_params:
            self.state = query_params['state']

        return redirect"""

        new_block = """        self._code_verifier = __import__('secrets').token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(self._code_verifier.encode()).digest()
        ).rstrip(b'=').decode()
        params.append(('client_id', self.client_id))
        params.append(('response_type', 'code'))
        params.append(('scope', 'openid profile'))
        params.append(('code_challenge', code_challenge))
        params.append(('code_challenge_method', 'S256'))
        if state is None:
            self.state = __import__('secrets').token_urlsafe(32)
            state = self.state
        params.append(('state', state))
        auth_url: str = add_params_to_uri(url, params)
        return auth_url"""

        if old_block in src:
            src = src.replace(old_block, new_block)
            changed = True

    # 2. Fix login() token endpoint
    if "emea.bff.cariad.digital/user-login/login/v1" in src:
        src = src.replace(
            "self.fetch_tokens('https://emea.bff.cariad.digital/user-login/login/v1',",
            "self.fetch_tokens('https://identity.vwgroup.io/oidc/v1/token',"
        )
        changed = True

    # 3. Fix refresh() token endpoint
    if "emea.bff.cariad.digital/login/v1/idk/token" in src:
        src = src.replace(
            "'https://emea.bff.cariad.digital/login/v1/idk/token'",
            "'https://identity.vwgroup.io/oidc/v1/token'"
        )
        changed = True

    # 4. Replace fetch_tokens() to use authorization code + PKCE (not hybrid flow)
    if "self.parse_from_fragment(authorization_response)" in src and "grant_type" not in src:
        old_start = "    def fetch_tokens("
        old_end = "    def parse_from_body("

        start_idx = src.find(old_start)
        end_idx = src.find(old_end)

        if start_idx != -1 and end_idx != -1:
            new_method = '''    def fetch_tokens(
        self,
        token_url,
        authorization_response=None,
        **_
    ):
        """
        Exchange authorization code for tokens (authorization code + PKCE flow).
        """
        from urllib.parse import urlparse, parse_qs
        import json as _json

        parsed = urlparse(authorization_response)
        params = parse_qs(parsed.query)
        code = params.get('code', [None])[0]

        if not code:
            LOG.error("No authorization code in response: %s", authorization_response[:200])
            return None

        token_body = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri,
            'client_id': self.client_id,
        }
        if hasattr(self, '_code_verifier') and self._code_verifier:
            token_body['code_verifier'] = self._code_verifier

        request_headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'accept': 'application/json',
            'user-agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36',
        }

        token_response = self.post(
            token_url,
            data=token_body,
            headers=request_headers,
            allow_redirects=False,
            access_type=AccessType.ID,
        )

        if token_response.status_code != requests.codes['ok']:
            LOG.error("Token exchange failed: %s", token_response.status_code)
            raise TemporaryAuthenticationError(
                f'Token exchange failed: {token_response.status_code}'
            )

        token = _json.loads(token_response.text)
        self.token = token

        if token:
            LOG.debug("Tokens fetched. Expires in: %s", token.get('expires_in', 'unknown'))
        return token

'''
            src = src[:start_idx] + new_method + src[end_idx:]
            changed = True

    if changed:
        filepath.write_text(src)
    return changed


def patch_vw_web_session(filepath: Path) -> bool:
    """Patch vw_web_session.py — use plain browser headers for Auth0 GET requests."""
    src = filepath.read_text()

    if "PATCHED: plain headers" in src:
        return False

    lines = src.split('\n')
    patched_lines = []
    i = 0
    changed = False

    while i < len(lines):
        line = lines[i]

        # Only patch lines that are GET requests with allow_redirects=False
        # that DON'T already have headers= parameter
        if 'self.websession.get(' in line and 'allow_redirects=False' in line and 'headers=' not in line:
            # Extract indentation
            indent = len(line) - len(line.lstrip())
            indent_str = ' ' * indent

            # Insert plain headers block before the GET line
            patched_lines.append(f"{indent_str}# PATCHED: plain headers for Auth0")
            patched_lines.append(f"{indent_str}_ph = {{'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'accept-language': 'en-US,en;q=0.9', 'user-agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36'}}")
            # Modify the GET line to include headers=_ph
            new_line = line.replace('allow_redirects=False)', 'headers=_ph, allow_redirects=False)')
            patched_lines.append(new_line)
            changed = True
        else:
            patched_lines.append(line)

        i += 1

    if changed:
        filepath.write_text('\n'.join(patched_lines))

    return changed


def main():
    try:
        import carconnectivity_connectors.volkswagen as vw_pkg
        base = Path(vw_pkg.__file__).parent / "auth"
    except ImportError:
        print("carconnectivity-connector-volkswagen not installed")
        return 1

    wcf = base / "we_connect_session.py"
    vwf = base / "vw_web_session.py"

    changed = False
    if wcf.exists():
        if patch_we_connect_session(wcf):
            print(f"  ✅ Patched {wcf.name}")
            changed = True
        else:
            print(f"  ⏭️  {wcf.name} already patched or not needed")

    if vwf.exists():
        if patch_vw_web_session(vwf):
            print(f"  ✅ Patched {vwf.name}")
            changed = True
        else:
            print(f"  ⏭️  {vwf.name} already patched or not needed")

    if changed:
        print("\n✅ VW auth patch applied successfully")
    else:
        print("\n✅ All patches already applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
