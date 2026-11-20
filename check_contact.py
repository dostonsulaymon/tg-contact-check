#!/usr/bin/env python3
"""
Telegram contact-check tool (Telethon).

Checks whether a target Telegram user has you saved in their contacts,
by inspecting the `contact` and `mutual_contact` flags Telegram exposes
on User entities.

Setup:
    1. Get API_ID / API_HASH from https://my.telegram.org
    2. Put them in a .env file next to this script:
         TG_API_ID=123456
         TG_API_HASH=abcdef0123456789abcdef0123456789
       or export them as environment variables.
    3. pip install -r requirements.txt
    4. python check_contact.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    RPCError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.contacts import AddContactRequest, DeleteContactsRequest
from telethon.tl.types import User

# Session is persisted to a local .session file so login only happens once.
SESSION_FILE = "contact_checker"


def load_credentials():
    """Read API_ID / API_HASH from env vars or a .env file. Exit with a clear
    error if either is missing."""
    load_dotenv()  # no-op if there's no .env file; env vars still apply

    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")

    if not api_id or not api_hash:
        print(
            "ERROR: TG_API_ID and/or TG_API_HASH are not set.\n"
            "Set them as environment variables, or create a .env file with:\n"
            "  TG_API_ID=123456\n"
            "  TG_API_HASH=your_api_hash\n"
            "Get these values from https://my.telegram.org",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        api_id = int(api_id)
    except ValueError:
        print("ERROR: TG_API_ID must be an integer.", file=sys.stderr)
        sys.exit(1)

    return api_id, api_hash


async def ensure_authenticated(client: TelegramClient):
    """Connect and, only if there's no valid saved session yet, run the
    standard Telethon login flow (phone -> code -> optional 2FA password)."""
    await client.connect()

    if await client.is_user_authorized():
        return

    phone = input(
        "First run - enter your phone number in international format "
        "(e.g. +998901234567): "
    ).strip()

    # client.start() drives the phone -> code -> 2FA-password flow itself,
    # prompting via input()/getpass() as needed.
    await client.start(phone=phone)


async def they_have_me_via_temp_add(client: TelegramClient, entity: User, label: str):
    """Temporarily add the target as a contact, read mutual_contact, then
    remove them again. Returns True/False, or None if it couldn't tell."""
    # mutual_contact is only reported for people in *your* contacts, so we
    # add them by user ID (no phone number needed) just long enough to read it.
    # add_phone_privacy_exception=False: never reveal your number to them.
    try:
        updates = await client(
            AddContactRequest(
                id=entity,
                first_name=entity.first_name or label,
                last_name=entity.last_name or "",
                phone="",
                add_phone_privacy_exception=False,
            )
        )
    except FloodWaitError as e:
        print(f"Rate limited by Telegram. Try again in {e.seconds} seconds.")
        return None
    except RPCError as e:
        print(f"Telegram refused to add {label} temporarily: {e}")
        return None

    try:
        user = next(
            (u for u in getattr(updates, "users", []) if u.id == entity.id), None
        )
        if user is None:
            print("Telegram didn't return the user after adding - can't tell.")
            return None
        return bool(user.mutual_contact)
    finally:
        try:
            await client(DeleteContactsRequest(id=[entity]))
        except RPCError as e:
            print(
                f"WARNING: couldn't remove {label} from your contacts "
                f"again ({e}). Remove them manually."
            )


_dialogs_loaded = False


async def resolve_by_id(client: TelegramClient, user_id: int):
    """Telegram can't look up a bare user ID without an access hash, which
    Telethon only has for users this session has already seen. If the ID is
    unknown, load your chat list once (read-only) to learn more users."""
    global _dialogs_loaded
    try:
        return await client.get_entity(user_id)
    except ValueError:
        if _dialogs_loaded:
            raise
    print("ID not known yet - loading your chats once to look it up...")
    await client.get_dialogs()
    _dialogs_loaded = True
    return await client.get_entity(user_id)


async def check_user(client: TelegramClient, target: str):
    """Resolve a username or numeric user ID and report contact status in
    both directions."""
    target = target.lstrip("@").strip()
    if not target:
        print("Please enter a username or user ID.")
        return
    by_id = target.isdigit()
    shown = f"id {target}" if by_id else f"@{target}"

    try:
        if by_id:
            entity = await resolve_by_id(client, int(target))
        else:
            entity = await client.get_entity(target)
    except (UsernameNotOccupiedError, UsernameInvalidError):
        print(f"'{shown}' does not exist or the username is invalid.")
        return
    except ValueError:
        if by_id:
            print(
                f"Could not find user {shown}. Telegram only resolves IDs of "
                "people your account has seen (a chat with them, a shared "
                "group you've opened). Try their username instead."
            )
        else:
            print(f"Could not resolve '{shown}' - it may not exist.")
        return
    except FloodWaitError as e:
        print(f"Rate limited by Telegram. Try again in {e.seconds} seconds.")
        return

    if not isinstance(entity, User):
        print(f"{shown} is a group or channel, not a person.")
        return
    if entity.is_self:
        print("That's you.")
        return
    if entity.bot:
        print(f"{shown} is a bot - bots don't have contact lists.")
        return

    name = " ".join(filter(None, [entity.first_name, entity.last_name])) or "?"
    handle = f"@{entity.username}, " if entity.username else ""
    label = f"{name} ({handle}id {entity.id})"

    i_have_them = bool(entity.contact)
    if i_have_them:
        they_have_me = bool(entity.mutual_contact)
    else:
        they_have_me = await they_have_me_via_temp_add(client, entity, label)
        if they_have_me is None:
            return

    yes_no = {True: "YES", False: "no"}
    print(f"\n--- {label} ---")
    print(f"You have them saved:  {yes_no[i_have_them]}")
    print(f"They have you saved:  {yes_no[they_have_me]}")

    if i_have_them and they_have_me:
        print("=> Mutual contacts.")
    elif they_have_me:
        print("=> They have you saved, but you don't have them.")
    elif i_have_them:
        print("=> You have them saved, but they don't have you.")
    else:
        print("=> Neither of you has the other saved.")
    if not i_have_them:
        print("(Checked by adding them to your contacts for a moment.)")
    print()


async def main():
    api_id, api_hash = load_credentials()

    client = TelegramClient(SESSION_FILE, api_id, api_hash)
    await ensure_authenticated(client)

    print("Logged in. You can check as many usernames or user IDs as you like.\n")

    try:
        while True:
            target = input(
                "Enter username or user ID (or 'quit' to exit): "
            ).strip()
            if target.lower() in ("quit", "exit", ""):
                break
            await check_user(client, target)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted, exiting.")
