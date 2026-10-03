"""Admin commands.

    python -m app.mockbank.cli create-client --name paymentsapp-dev --owner <customer_id> [--webhook-url URL]
    python -m app.mockbank.cli list-clients
    python -m app.mockbank.cli set-webhook --name paymentsapp-dev --url URL
    python -m app.mockbank.cli deactivate-client --name paymentsapp-dev
"""

import argparse
import sys

from app.mockbank.db.database import SessionLocal
from app.mockbank.db.models import ApiClientModel
from app.mockbank.services import clients


def _find(db, name: str) -> ApiClientModel:
    client = db.query(ApiClientModel).filter(ApiClientModel.name == name).one_or_none()
    if client is None:
        sys.exit(f"no client named {name!r}")
    return client


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.mockbank.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-client", help="issue an API key for a new client (printed once)")
    create.add_argument("--name", required=True)
    create.add_argument("--owner", required=True, help="customer_id whose UPI IDs this client may pay from")
    create.add_argument("--webhook-url")

    sub.add_parser("list-clients")

    hook = sub.add_parser("set-webhook")
    hook.add_argument("--name", required=True)
    hook.add_argument("--url", required=True, help="empty string to remove")

    deactivate = sub.add_parser("deactivate-client")
    deactivate.add_argument("--name", required=True)

    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        if args.command == "create-client":
            try:
                client, api_key = clients.create_client(db, args.name, args.owner, args.webhook_url)
            except ValueError as exc:
                sys.exit(str(exc))
            print(f"client_id:      {client.client_id}")
            print(f"name:           {client.name}")
            print(f"owner:          {client.owner_customer_id}")
            print(f"api_key:        {api_key}")
            print(f"webhook_secret: {client.webhook_secret}")
            print("Store the api_key now: only its hash is kept and it cannot be shown again.")
        elif args.command == "list-clients":
            for c in db.query(ApiClientModel).order_by(ApiClientModel.created_at):
                state = "active" if c.active else "inactive"
                print(f"{c.client_id}  {c.name}  owner={c.owner_customer_id}  key=mbk_{c.key_prefix}_...  {state}  webhook={c.webhook_url or '-'}")
        elif args.command == "set-webhook":
            client = _find(db, args.name)
            client.webhook_url = args.url or None
            db.commit()
            print(f"webhook_url for {client.name}: {client.webhook_url or '-'}")
        elif args.command == "deactivate-client":
            client = _find(db, args.name)
            client.active = False
            db.commit()
            print(f"{client.name} deactivated")
    finally:
        db.close()


if __name__ == "__main__":
    main()
