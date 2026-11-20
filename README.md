# tg-contact-check

A small Telethon script that answers one question: **does this Telegram user have you in their contacts?**

It logs in as *you* (a regular Telegram user, not a bot) and reports contact status **in both directions**: whether you have them saved, and whether they have you saved.

## How it works

Telegram only reports `mutual_contact` (they have you too) for people in **your** contacts. So for each username:

1. Resolve it to a user (groups, channels and bots are rejected with a clear message).
2. If they're already in your contacts → read `mutual_contact` directly. Nothing is changed.
3. If not → add them as a contact **by user ID** (`AddContactRequest`, no phone number needed), read `mutual_contact` from the response, then remove them again with `DeleteContactsRequest`. Your phone number is **not** shared with them (`add_phone_privacy_exception=False`), and Telegram doesn't notify them.

| You have them | They have you | Result |
|---|---|---|
| YES | YES | Mutual contacts. |
| no | YES | They have you saved, but you don't have them. |
| YES | no | You have them saved, but they don't have you. |
| no | no | Neither of you has the other saved. |

If removing the temporary contact ever fails, the script prints a `WARNING` naming the user so you can remove them manually.

## Setup

1. Get an `api_id` / `api_hash` pair from <https://my.telegram.org> (API development tools → create an app). This authenticates *your account*, not the script — don't share it.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file next to `check_contact.py`:
   ```
   TG_API_ID=123456
   TG_API_HASH=your_api_hash_here
   ```

## Usage

```bash
python3 check_contact.py
```

- **First run**: you'll be asked for your phone number (e.g. `+998901234567`), then Telegram's standard login code and, if enabled, your 2FA password — same flow as logging into any Telegram client. A local `contact_checker.session` file is created so you won't need to log in again.
- **Every run after that**: it reuses the saved session and skips straight to asking for a username.
- Enter usernames (with or without `@`) or numeric user IDs one at a time; type `quit` to exit.
- **User IDs have a Telegram limit:** an ID can only be looked up if your account has already "seen" that person (a private chat, a group you've opened). If the ID is unknown, the script loads your chat list once (read-only) and retries. If it still can't be found, use their username.

## Notes

- `contact_checker.session` is your authenticated Telegram login — **never commit or share it**. It's gitignored here for that reason.
- Same goes for `.env` — it's gitignored too.
- Handles flood waits and invalid/unknown usernames without crashing.
- Checking lots of people quickly means lots of add/remove contact calls; Telegram may rate-limit you (`FloodWait`). Don't batch-hammer it.
