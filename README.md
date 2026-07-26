# Telegram LaTeX Bot

Make your rich LaTeX messages without Telegram Premium.

## Config and Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
nano .env # Save: Ctrl+S , Exit: Ctrl+X
```

Example `.env` file:

```env
BOT_TOKEN=YOUR_BOT_TOKEN
ADMIN_ID=CREATOR_NUMERIC_ID
DATABASE_PATH=database.sqlite3
BOT_API_BASE=https://api.telegram.org
```

Then run the bot:

```bash
python3 main.py
```

## Features

- `/start` for help and user registration.
- Receive LaTeX in private chat and send it using `sendRichMessage`.
- Invoke the bot from any chat using Guest Mode:

  ```text
  @LaTeXRm_Bot \displaystyle\sum_{i=1}^{10} t_i
  ```

- Reply directly in the same chat using `answerGuestQuery`.
- `/admin` (hidden; type it manually as the owner) is accessible only to the administrator and is completely ignored for everyone else.
- Plain text messages are ignored; only actual LaTeX or mathematical expressions are rendered.
- View total users and active users statistics.
- Multi-channel mandatory membership with enable/disable, add, and remove channel support.
- Broadcast text, photos, videos, and documents using `copyMessage`.
- SQLite database with long polling.

## Enabling Guest Mode

Open `@BotFather`, select your bot, and enable **Guest Mode** in the bot settings. After starting the bot, you should see:

```text
Bot started as @YourBot | guest mode=True
```

If it shows `False`, the bot will not respond in chats where it is not a member.

## Adding Mandatory Membership Channels

From `/admin` (hidden; type it manually as the owner):

1. Select **Mandatory Membership**.
2. Select **Add Channel**.
3. For a public channel:

   ```text
   @ChannelUsername
   ```

4. For a private channel:

   ```text
   -1001234567890 | https://t.me/+InviteLink
   ```

The bot must be an administrator in the channel so that `getChatMember` can correctly verify users.

## Sending Formulas

In the bot's private chat:

```latex
\frac{x^2+1}{\sqrt{x}}
```

In any chat:

```text
@YourBot \int_{0}^{\infty} e^{-x^2}\,dx
```

The bot uses Telegram's official mathematical expression block:

```json
{
  "type": "mathematical_expression",
  "expression": "\\displaystyle\\sum_{i=1}^{10} t_i"
}
```

## Library Note

This project intentionally communicates with the Telegram Bot API directly through `aiohttp`, since the currently available versions of some bot frameworks may not yet support `guest_message`, `answerGuestQuery`, or the new Rich Messages API.

## Inline UID Library

- Send a LaTeX formula to the bot in a private chat; it is stored and assigned a unique UID.
- Typing only `@LatexRM_bot` displays the user's most recently saved formulas.
- Typing part of a UID or part of the stored LaTeX filters the results.
- Typing an exact UID loads the corresponding stored formula.
- Typing raw LaTeX renders it directly as an inline result.
- Inline results are user-specific and use `cache_time=0`, ensuring each user sees only their own library.

## Guest Mode

Guest Mode is independent of Inline Mode. The bot receives `guest_message` updates and responds using `answerGuestQuery`. Telegram must report `supports_guest_queries=true` in the `getMe` response; otherwise, Guest Mode must be enabled in BotFather (or the Telegram bot settings). On startup, the bot logs either `guest mode=True` or `guest mode=False`.

# LICENSE

- [GPL v3.0](LICENSE)
