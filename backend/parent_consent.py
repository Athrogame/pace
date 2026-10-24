"""Operator-only parent rights lookup and deletion.

Confirm the requester controls the original consent email before sharing data or
running a deletion. Do not accept a displayed From address alone as proof.
"""
import argparse
from pathlib import Path

from dotenv import load_dotenv

from . import db


def main():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    parser = argparse.ArgumentParser(description="Find or delete a parent-approved Pace plan")
    parser.add_argument("action", choices=("lookup", "delete"))
    parser.add_argument("parent_email", help="The verified parent contact address")
    args = parser.parse_args()
    with db.connect() as conn:
        rows = conn.execute("SELECT user_id, confirmed_at FROM parent_email_consents "
                            "WHERE parent_email = ? AND revoked_at IS NULL",
                            (args.parent_email.strip().lower(),)).fetchall()
        if args.action == "lookup":
            for row in rows:
                print(row["user_id"], "confirmed" if row["confirmed_at"] else "pending")
            if not rows:
                print("No matching consent records")
        else:
            for row in rows:
                db.delete_user(conn, row["user_id"])
            print("Deleted", len(rows), "plan(s) and consent record(s)")


if __name__ == "__main__":
    main()
