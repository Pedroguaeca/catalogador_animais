"""
Pre Sign-up Lambda Trigger — valida convites antes de criar o utilizador no Cognito.

Fluxo esperado (Google OAuth, primeira entrada):
1. Utilizador clica "Entrar com Google" no frontend
2. Cognito recebe o token do Google e cria o registo federado no User Pool
3. ESTE trigger dispara (pré-criação, utilizador já existe no pool para IDP federados)
4. Consultamos siab-invites via GSI email-index com status='pending'
5. Se não encontrado → lançamos exceção → Cognito nega a criação da conta
6. Se encontrado → aprovamos + definimos custom:tenant_id e custom:role via AdminAPI

Nota sobre definir atributos no Pre Sign-up:
  - event.request.userAttributes é SOMENTE LEITURA neste trigger.
  - Para utilizadores federados (Google), o registo JÁ EXISTE no pool quando este
    trigger dispara → admin_update_user_attributes funciona aqui.
  - Para utilizadores nativos (email/senha), o registo ainda não existe quando o
    trigger dispara → admin_update_user_attributes lançaria UserNotFoundException;
    tratamos esse caso sem falhar o trigger (Post Confirmation seria o fallback).
"""

import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

INVITES_TABLE = os.environ["INVITES_TABLE"]
# USER_POOL_ID não é env var — viria event["userPoolId"] (todos os triggers Cognito
# incluem o campo). Evita dependência circular no CDK/CloudFormation.

_ddb     = boto3.resource("dynamodb")
_cognito = boto3.client("cognito-idp", region_name="us-east-1")


def lambda_handler(event, context):
    email        = event["request"]["userAttributes"].get("email", "")
    user_pool_id = event["userPoolId"]

    if not email:
        raise Exception("Atributo email ausente no evento Pre Sign-up")

    logger.info("Pre Sign-up | email=%s trigger=%s", email, event.get("triggerSource"))

    # ── Consulta convite via GSI email-index ──────────────────────────────────
    # "status" é palavra reservada no DynamoDB — alias obrigatório via #st.
    table = _ddb.Table(INVITES_TABLE)
    result = table.query(
        IndexName="email-index",
        KeyConditionExpression="email = :email",
        FilterExpression="#st = :st",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":email": email, ":st": "pending"},
    )

    items = result.get("Items", [])
    if not items:
        logger.warning("Nenhum convite pendente | email=%s", email)
        raise Exception(f"Usuário não convidado: {email}")

    invite    = items[0]
    tenant_id = invite["tenant_id"]
    role      = invite.get("role", "analyst")
    logger.info("Convite encontrado | tenant_id=%s role=%s", tenant_id, role)

    # ── Aprovação automática (fluxo federado não precisa de confirmação por email) ──
    event["response"]["autoConfirmUser"] = True
    event["response"]["autoVerifyEmail"] = True

    # ── Define custom:tenant_id e custom:role no registo do utilizador ────────
    username = event["userName"]
    try:
        _cognito.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=username,
            UserAttributes=[
                {"Name": "custom:tenant_id", "Value": tenant_id},
                {"Name": "custom:role",      "Value": role},
            ],
        )
        logger.info("Atributos custom definidos | username=%s tenant=%s role=%s",
                    username, tenant_id, role)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "UserNotFoundException":
            # Utilizador nativo ainda não existe no pool — não falha o trigger.
            # Se este projeto passar a suportar login email/senha, adicionar
            # um Post Confirmation trigger para definir os atributos nesse fluxo.
            logger.warning("UserNotFoundException em Pre Sign-up — fluxo nativo? username=%s", username)
        else:
            logger.error("Erro inesperado ao definir atributos custom: %s", exc)
            raise

    # ── Marca convite como activo ─────────────────────────────────────────────
    activated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    table.update_item(
        Key={"tenant_id": tenant_id, "email": email},
        UpdateExpression="SET #st = :active, activated_at = :ts",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":active": "active", ":ts": activated_at},
    )
    logger.info("Convite marcado como active | tenant_id=%s email=%s activated_at=%s",
                tenant_id, email, activated_at)

    return event
