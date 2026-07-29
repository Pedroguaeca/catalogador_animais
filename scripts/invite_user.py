#!/usr/bin/env python3
"""
scripts/invite_user.py — CLI para convidar utilizadores para o SIAB.

Exemplos:
    python scripts/invite_user.py \\
        --email joao@empresa.com --tenant-id consultoria-teste \\
        --role analyst --method google

    python scripts/invite_user.py \\
        --email admin@empresa.com --tenant-id consultoria-teste \\
        --role admin --method password --invited-by setup@siab.io
"""

import argparse
import sys
import os

# Permite importar backend/ directamente quando o script é corrido da raiz do repo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.invites import create_invite, VALID_ROLES


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convida um utilizador para o SIAB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--email",       required=True,  help="Email do utilizador")
    parser.add_argument("--tenant-id",   required=True,  help="ID do tenant (ex: consultoria-teste)")
    parser.add_argument("--role",        required=True,  choices=sorted(VALID_ROLES),
                        help="Papel do utilizador")
    parser.add_argument("--method",      required=True,  choices=["google", "password"],
                        help="'google': aguarda login OAuth  |  'password': cria conta imediatamente")
    parser.add_argument("--invited-by",  default="cli",  help="Email/identificador de quem convida")

    args = parser.parse_args()

    print(f"\nA criar convite para {args.email} ({args.role}) no tenant {args.tenant_id}...")

    try:
        result = create_invite(
            tenant_id  = args.tenant_id,
            email      = args.email,
            role       = args.role,
            invited_by = args.invited_by,
            method     = args.method,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"\n✗ Erro: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n✓ Convite criado com sucesso!")
    print(f"  tenant_id  : {result['tenant_id']}")
    print(f"  email      : {result['email']}")
    print(f"  role       : {result['role']}")
    print(f"  status     : {result['status']}")
    print(f"  method     : {result['method']}")
    print(f"  invited_at : {result['invited_at']}")

    if result.get("temp_password"):
        print()
        print("  ┌─────────────────────────────────────────────────┐")
        print("  │  SENHA TEMPORÁRIA — copie agora, não é re-exibida│")
        print(f"  │  {result['temp_password']:<49}│")
        print("  └─────────────────────────────────────────────────┘")
        print("  O utilizador terá de alterar a senha no primeiro login.")
    else:
        print()
        print("  Próximo passo: o utilizador deve fazer login com Google.")
        print("  O convite será activado automaticamente no primeiro login.")

    print()


if __name__ == "__main__":
    main()
