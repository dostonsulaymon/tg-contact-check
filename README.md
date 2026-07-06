# tg-contact-check

A small Telethon script that answers one question: **does this Telegram user have you in their contacts?**

It logs in as *you* (a regular Telegram user, not a bot) and inspects the `contact` / `mutual_contact` flags Telegram exposes on user entities.

## How it works

Telegram only tells you `mutual_contact` (they have you too) once **you've** added the target as a contact yourself. So the script:

1. Resolves the username you give it to a user entity.
2. If their phone number happens to be visible to you (privacy settings permitting — this is rare unless you're already mutual or their number is public), it adds them as a contact via `ImportContactsRequest` so the flags become meaningful.
3. Reports `contact`, `mutual_contact`, and a plain-English interpretation:

| `contact` | `mutual_contact` | Meaning |
|---|---|---|
| ✅ | ✅ | They have you in their contacts too. |
| ✅ | ❌ | You have them saved, but they don't have you. |
| ❌ | — | You haven't added them, so mutual status is unknown. |

**Limitation:** if you don't already have the target's phone number, step 2 can't run, and you'll usually land in the "unknown" bucket. This is a Telegram API restriction, not a bug — there's no way around it without their number.

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
- Enter usernames (with or without `@`) one at a time; type `quit` to exit.

## Notes

- `contact_checker.session` is your authenticated Telegram login — **never commit or share it**. It's gitignored here for that reason.
- Same goes for `.env` — it's gitignored too.
- Handles flood waits, invalid/unknown usernames, and privacy-restricted contact imports without crashing.
