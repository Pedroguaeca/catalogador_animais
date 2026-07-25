"""
Post Confirmation Lambda Trigger — define custom:tenant_id e custom:role após
o utilizador ser criado e confirmado no Cognito.

O Pre Sign-up trigger valida o convite e marca status='active', mas não consegue
definir atributos porque o utilizador ainda não existe no pool nesse momento.
O Post Confirmation dispara DEPOIS do utilizador estar criado — aqui
admin_update_user_attributes funciona.

Para utilizadores IDP externos (Google), este trigger dispara apenas na primeira
entrada (criação). Para logins subsequentes, os atributos já existem no registo.
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

INVITES_TABLE = os.environ["INVITES_TABLE"]

_ddb     = boto3.resource("dynamodb")
_cognito = boto3.client("cognito-idp", region_name="us-east-1")


def lambda_handler(event, context):
    user_pool_id = event["userPoolId"]
    username     = event["userName"]
    email        = event["request"]["userAttributes"].get("email", "")
    trigger      = event.get("triggerSource", "")

    logger.info("Post Confirmation | email=%s username=%s trigger=%s",
                email, username, trigger)

    if not email:
        # Sem email não há como buscar o convite — deixar passar sem erro
        logger.warning("Email ausente no Post Confirmation; atributos não definidos")
        return event

    # Busca o convite por email (o Pre Sign-up já marcou status='active')
    # Não filtramos por status aqui — o convite pode ser pending ou active
    table  = _ddb.Table(INVITES_TABLE)
    result = table.query(
        IndexName="email-index",
        KeyConditionExpression="email = :email",
        ExpressionAttributeValues={":email": email},
    )

    items = result.get("Items", [])
    if not items:
        logger.warning("Nenhum convite encontrado para email=%s — atributos não definidos", email)
        return event

    invite    = items[0]
    tenant_id = invite["tenant_id"]
    role      = invite.get("role", "analyst")
    logger.info("Convite encontrado | tenant_id=%s role=%s", tenant_id, role)

    try:
        _cognito.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=username,
            UserAttributes=[
                {"Name": "custom:tenant_id", "Value": tenant_id},
                {"Name": "custom:role",      "Value": role},
            ],
        )
        logger.info("custom:tenant_id e custom:role definidos | username=%s tenant=%s role=%s",
                    username, tenant_id, role)
    except ClientError as exc:
        # Não falha o trigger para não bloquear o login — mas regista para alertar
        logger.error("Falha ao definir atributos custom no Post Confirmation: %s", exc)

    return event
