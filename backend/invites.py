"""
backend/invites.py — Lógica central de convites de utilizadores.

Fonte única de verdade para criar convites. Tanto o script CLI
(scripts/invite_user.py) como qualquer endpoint futuro importam
e chamam create_invite() — nunca reimplementam a lógica aqui.
"""

from __future__ import annotations

import os
import secrets
import string
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

INVITES_TABLE    = os.environ.get("INVITES_TABLE",         "siab-invites")
USER_POOL_ID     = os.environ.get("COGNITO_USER_POOL_ID",  "us-east-1_muBMGRYkB")
AWS_REGION       = os.environ.get("AWS_DEFAULT_REGION",    "us-east-1")

VALID_ROLES = {"analyst", "approver", "admin"}

_ddb     = boto3.resource("dynamodb", region_name=AWS_REGION)
_cognito = boto3.client("cognito-idp",  region_name=AWS_REGION)


def _generate_temp_password(length: int = 12) -> str:
    """Gera senha temporária que cumpre a política do User Pool.

    Política: min 8 chars, pelo menos 1 dígito, pelo menos 1 minúscula.
    Inclui maiúsculas e símbolos por robustez, mas não são obrigatórios.
    """
    lower   = string.ascii_lowercase
    digits  = string.digits
    upper   = string.ascii_uppercase
    symbols = "!@#$%^&*"
    alphabet = lower + digits + upper + symbols

    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        # Garante que a política mínima é satisfeita
        if (any(c in lower for c in pwd) and any(c in digits for c in pwd)):
            return pwd


def create_invite(
    tenant_id:  str,
    email:      str,
    role:       str,
    invited_by: str,
    method:     str,   # "google" | "password"
) -> dict:
    """Cria convite em siab-invites e, se method=='password', cria utilizador no Cognito.

    Returns:
        dict com chaves: tenant_id, email, role, status, method,
        e (se method=='password') temp_password.

    Raises:
        ValueError: argumento inválido (role, method).
        RuntimeError: convite duplicado ou falha do Cognito.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"role inválido: '{role}'. Válidos: {sorted(VALID_ROLES)}")
    if method not in ("google", "password"):
        raise ValueError(f"method inválido: '{method}'. Use 'google' ou 'password'.")

    table        = _ddb.Table(INVITES_TABLE)
    invited_at   = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Verifica duplicado ────────────────────────────────────────────────────
    existing = table.get_item(Key={"tenant_id": tenant_id, "email": email}).get("Item")
    if existing and existing.get("status") in ("pending", "active"):
        raise RuntimeError(
            f"Já existe convite com status='{existing['status']}' para "
            f"{email} no tenant {tenant_id}. Apague ou redefina antes de criar novo."
        )

    # ── Grava convite em DynamoDB ─────────────────────────────────────────────
    item: dict = {
        "tenant_id":  tenant_id,
        "email":      email,
        "role":       role,
        "status":     "pending",
        "invited_by": invited_by,
        "invited_at": invited_at,
    }
    table.put_item(Item=item)

    if method == "google":
        # O Pre Sign-up / Post Confirmation trigger cuida do resto no primeiro login.
        return {
            "tenant_id":  tenant_id,
            "email":      email,
            "role":       role,
            "status":     "pending",
            "method":     "google",
            "invited_at": invited_at,
        }

    # ── method == "password": cria utilizador directamente no Cognito ─────────
    temp_password = _generate_temp_password()
    try:
        _cognito.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=[
                {"Name": "email",              "Value": email},
                {"Name": "email_verified",     "Value": "true"},
                {"Name": "custom:tenant_id",   "Value": tenant_id},
                {"Name": "custom:role",        "Value": role},
            ],
            TemporaryPassword=temp_password,
            MessageAction="SUPPRESS",   # não envia email de boas-vindas
        )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "UsernameExistsException":
            # Utilizador já existe no Cognito — reverter item DynamoDB e informar
            table.delete_item(Key={"tenant_id": tenant_id, "email": email})
            raise RuntimeError(
                f"Utilizador {email} já existe no Cognito. "
                "Se precisas de redefinir o convite, apaga o utilizador primeiro."
            ) from exc
        raise RuntimeError(f"Erro Cognito ao criar utilizador: {exc}") from exc

    # Marca convite como active (bypass dos triggers — utilizador criado pelo admin)
    table.update_item(
        Key={"tenant_id": tenant_id, "email": email},
        UpdateExpression="SET #st = :active, activated_at = :ts",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={
            ":active": "active",
            ":ts":     invited_at,   # activated_at = invited_at (criação imediata)
        },
    )

    return {
        "tenant_id":     tenant_id,
        "email":         email,
        "role":          role,
        "status":        "active",
        "method":        "password",
        "invited_at":    invited_at,
        "temp_password": temp_password,
    }
