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
    PhoneNumberInvalidError,
    UserPrivacyRestrictedError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact

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


async def check_user(client: TelegramClient, username: str):
    """Resolve a username, try to add them as a contact (required for
    mutual_contact to mean anything), then report contact status."""
    username = username.lstrip("@").strip()
    if not username:
        print("Please enter a non-empty username.")
        return

    try:
        entity = await client.get_entity(username)
    except (UsernameNotOccupiedError, UsernameInvalidError):
        print(f"'@{username}' does not exist or the username is invalid.")
        return
    except ValueError:
        print(
            f"Could not resolve '@{username}'. Telegram couldn't find that "
            "entity (it may not exist, or Telethon has no cached reference "
            "to it yet)."
        )
        return
    except FloodWaitError as e:
        print(f"Rate limited by Telegram. Try again in {e.seconds} seconds.")
        return

    # IMPORTANT: `mutual_contact` only becomes meaningful once *you* have
    # added the target as a contact. Telegram's mutual_contact flag means
    # "this user has me in their contacts AND I have them in mine" - if you
    # never added them, `contact` is False and `mutual_contact` is always
    # False too, regardless of whether they've added you.
    #
    # Adding someone as a contact via ImportContactsRequest requires a phone
    # number. Usernames don't carry one - we only get `entity.phone` if the
    # target's privacy settings expose it to us (rare, e.g. already mutual
    # contacts or a fully public phone number). If we don't have a phone
    # number, we can't add them ourselves; we can only report whatever
    # contact status already exists.
    phone = getattr(entity, "phone", None)
    if phone:
        try:
            contact = InputPhoneContact(
                client_id=0,
                phone=phone,
                first_name=entity.first_name or username,
                last_name=entity.last_name or "",
            )
            result = await client(ImportContactsRequest([contact]))
            if result.users:
                # Use the refreshed User object returned by the import call -
                # its contact/mutual_contact flags reflect the post-import state.
                entity = result.users[0]
            else:
                print(
                    "Import call succeeded but Telegram didn't add the "
                    "contact (their privacy settings may block it)."
                )
        except UserPrivacyRestrictedError:
            print(
                "This user's privacy settings prevent you from adding them "
                "as a contact. Reporting existing status only."
            )
        except FloodWaitError as e:
            print(f"Rate limited by Telegram. Try again in {e.seconds} seconds.")
            return
        except PhoneNumberInvalidError:
            print("Telegram rejected that phone number for contact import.")
    else:
        print(
            f"No phone number available for @{username} - skipping contact "
            "import. Reporting existing contact status as-is."
        )

    is_contact = bool(getattr(entity, "contact", False))
    is_mutual = bool(getattr(entity, "mutual_contact", False))

    print(f"\n--- @{username} ---")
    print(f"contact:         {is_contact}")
    print(f"mutual_contact:  {is_mutual}")

    if is_contact and is_mutual:
        print("=> They have you in their contacts too.")
    elif is_contact and not is_mutual:
        print("=> You have them saved, but they don't have you.")
    else:
        print("=> You haven't added them, so mutual status is unknown.")
    print()


async def main():
    api_id, api_hash = load_credentials()

    client = TelegramClient(SESSION_FILE, api_id, api_hash)
    await ensure_authenticated(client)

    print("Logged in. You can check as many usernames as you like.\n")

    try:
        while True:
            username = input(
                "Enter target username (or 'quit' to exit): "
            ).strip()
            if username.lower() in ("quit", "exit", ""):
                break
            await check_user(client, username)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted, exiting.")
