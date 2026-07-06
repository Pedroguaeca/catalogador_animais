"""
Infraestrutura de testes JWT para a API SIAB.

Gera um par RSA de teste uma vez por sessão, assina JWTs reais com ele e
popula _jwks_cache do api.py antes de cada teste. SIAB_JWT_VALIDATION
permanece True — os testes exercitam o mesmo caminho de validação de produção.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt
from jose.utils import base64url_encode as _b64u

# ── Chave RSA gerada uma vez por sessão ───────────────────────────────────────
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY  = _PRIVATE_KEY.public_key()
_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

TEST_KID       = "siab-test-key-1"
TEST_USER_POOL = "us-east-1_TESTPOOL"
TEST_CLIENT_ID = "test-client-id"
TEST_ISSUER    = f"https://cognito-idp.us-east-1.amazonaws.com/{TEST_USER_POOL}"
DEFAULT_TENANT = "consultoria-teste"


def _make_jwk() -> dict:
    pub = _PUBLIC_KEY.public_numbers()

    def _int_b64(n: int) -> str:
        length = (n.bit_length() + 7) // 8
        return _b64u(n.to_bytes(length, "big")).decode()

    return {
        "kty": "RSA",
        "use": "sig",
        "kid": TEST_KID,
        "alg": "RS256",
        "n": _int_b64(pub.n),
        "e": _int_b64(pub.e),
    }


_TEST_JWK = _make_jwk()


def make_jwt(
    *,
    tenant_id: str = DEFAULT_TENANT,
    role: str = "admin",
    expired: bool = False,
    bad_signature: bool = False,
) -> str:
    """JWT RS256 assinado com a chave de teste. Passa pelo _verify_jwt de produção."""
    now = int(time.time())
    payload = {
        "sub":                f"test-{tenant_id}",
        "iss":                TEST_ISSUER,
        "aud":                TEST_CLIENT_ID,
        "token_use":          "id",
        "custom:tenant_id":   tenant_id,
        "custom:role":        role,
        "iat":                now - 7200 if expired else now - 1,
        "exp":                now - 1 if expired else now + 3600,
    }
    token = jwt.encode(payload, _PRIVATE_PEM, algorithm="RS256",
                       headers={"kid": TEST_KID})
    if bad_signature:
        parts = token.split(".")
        token = f"{parts[0]}.{parts[1]}.BADSIGNATUREXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    return token


@pytest.fixture(autouse=True)
def _patch_jwt():
    """
    Ativa para cada teste:
    - api._jwks_cache preenchido com a JWK de teste (kid = TEST_KID)
    - api._COGNITO_ISSUER / _APP_CLIENT_ID apontam para os valores de teste
    - api._JWT_VALIDATION = True (validação sempre ligada)
    """
    with patch("backend.api._USER_POOL_ID",   TEST_USER_POOL), \
         patch("backend.api._APP_CLIENT_ID",  TEST_CLIENT_ID), \
         patch("backend.api._COGNITO_ISSUER", TEST_ISSUER), \
         patch("backend.api._JWT_VALIDATION", True), \
         patch.dict("backend.api._jwks_cache", {TEST_KID: _TEST_JWK}, clear=True):
        yield
