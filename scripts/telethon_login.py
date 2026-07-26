"""One-time Telethon login — creates the StringSession for the card reader.

Run this ON YOUR PC (PowerShell):

    pip install telethon
    python scripts/telethon_login.py

Steps it performs:
  1. Asks for api_id / api_hash  (create at https://my.telegram.org → API development tools)
  2. Asks for your phone number, the code Telegram sends you, and your 2FA password
  3. Prints the TELETHON_SESSION string  → paste into the VPS .env
  4. Lists dialogs that look like CardXabar so you can confirm the chat name

The printed session string grants access to your Telegram account —
treat it like a password. It goes ONLY into the VPS .env file.
"""

import asyncio

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    api_id = int(input("api_id (from my.telegram.org): ").strip())
    api_hash = input("api_hash: ").strip()

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()  # asks phone → code → 2FA password interactively

    me = await client.get_me()
    print(f"\nLogged in as: {me.first_name} (@{me.username}, id={me.id})")

    print("\n" + "=" * 60)
    print("TELETHON_SESSION (add to VPS .env, keep secret!):")
    print("=" * 60)
    print(client.session.save())
    print("=" * 60)

    print("\nDialogs that look like the card bot:")
    async for dialog in client.iter_dialogs():
        name = (dialog.name or "").lower()
        if "card" in name or "xabar" in name or "uzcard" in name:
            print(f"  title={dialog.name!r}  id={dialog.id}")

    print(
        "\nAdd to VPS .env:\n"
        f"  TELETHON_API_ID={api_id}\n"
        f"  TELETHON_API_HASH={api_hash}\n"
        "  TELETHON_SESSION=<string above>\n"
        "  CARDXABAR_CHAT=CardXabar   (or the exact title/id printed above)"
    )

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
