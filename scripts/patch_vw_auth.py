#!/usr/bin/env python3
"""
Patch the CarConnectivity VW connector for the May 2026 auth change.

VW deprecated:
1. The BFF endpoint (emea.bff.cariad.digital) → 403
2. The hybrid/implicit OIDC flow (response_type=code id_token token) → unauthorized_client

This patch:
- Changes authorization_url() to use identity.vwgroup.io with response_type=code
- Changes login() to use identity.vwgroup.io/oidc/v1/token for token exchange
- Changes _get_login_form() to use plain browser headers (VW Android headers → 400)

Run this script once after installing carconnectivity-connector-volkswagen.
"""
import sys
from pathlib import Path


def patch_we_connect_session(filepath: Path) -> bool:
    """Patch we_connect_session.py."""
    src = filepath.read_text()
    changed = False

    # 1. Add PKCE imports
    if "import base64" not in src:
        src = src.replace("import json", "import base64\nimport json", 1)
        changed = True

    # 2. Fix login() — use identity.vwgroup.io token endpoint (not BFF)
    if "emea.bff.cariad.digital/user-login/login/v1" in src:
        src = src.replace(
            "self.fetch_tokens('https://emea.bff.cariad.digital/user-login/login/v1',",
            "self.fetch_tokens('https://identity.vwgroup.io/oidc/v1/token',"
        )
        changed = True

    # 3. Fix authorization_url() — use identity.vwgroup.io with response_type=code
    if "emea.bff.cariad.digital/user-login/v1/authorize" in src:
        # Replace the BFF URL in add_params_to_uri calls
        src = src.replace(
            "add_params_to_uri('https://emea.bff.cariad.digital/user-login/v1/authorize'",
            "add_params_to_uri(url"
        )
        changed = True

    if changed:
        filepath.write_text(src)

    return changed


def patch_vw_web_session(filepath: Path) -> bool:
    """Patch vw_web_session.py — use plain browser headers."""
    src = filepath.read_text()

    if "VW's Auth0 requires session cookies" in src:
        return False  # Already patched

    # Replace the response = self.websession.get(url, allow_redirects=False)
    # with a version using plain browser headers
    old = "response = self.websession.get(url, allow_redirects=False)"
    new = """# VW's Auth0 requires plain browser headers — VW Android app headers cause 400
            plain_headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'accept-language': 'en-US,en;q=0.9',
                'user-agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36',
            }
            response = self.websession.get(url, headers=plain_headers, allow_redirects=False)"""

    if old in src:
        src = src.replace(old, new, 1)
        filepath.write_text(src)
        return True

    return False


def main():
    # Find the carconnectivity VW connector package
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
