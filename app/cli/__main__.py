from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from pydantic import ValidationError

from app.core.exceptions import AlreadyExistsException


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(prog="python -m app.cli")
  subparsers = parser.add_subparsers(dest="command", required=True)

  create_user = subparsers.add_parser(
    "create-user", help="Create a user directly in the configured database"
  )
  create_user.add_argument("--email", required=True, help="Email address for the user")
  create_user.add_argument(
    "--password-stdin",
    action="store_true",
    help="Read the password from stdin instead of prompting (useful for Kubernetes)",
  )
  return parser


def _read_password(read_stdin: bool) -> str:
  if read_stdin:
    password = sys.stdin.readline().rstrip("\r\n")
  else:
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
      raise ValueError("Passwords do not match")
  return password


async def _create_user(email: str, password: str) -> None:
  from app.api.v1.users.schemas import UserCreate
  from app.api.v1.users.service import UserService
  from app.core.db import async_session

  user_data = UserCreate(email=email, password=password)
  async with async_session() as session:
    user = await UserService(session).create_user(user_data)
  print(f"Created user {user.email} ({user.id})")


async def _run_create_user(email: str, password: str) -> None:
  from app.core.db import engine

  try:
    await _create_user(email, password)
  finally:
    await engine.dispose()


def main() -> int:
  args = _parser().parse_args()

  if args.command == "create-user":
    try:
      password = _read_password(args.password_stdin)
      asyncio.run(_run_create_user(args.email, password))
    except (AlreadyExistsException, ValidationError, ValueError) as exc:
      print(f"Could not create user: {exc}", file=sys.stderr)
      return 1

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
