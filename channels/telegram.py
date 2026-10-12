"""Kanal Telegram (opsional). Aktif kalau TELEGRAM_BOT_TOKEN diisi di .env.
Pesan dikirim ke telegram_chat_id nasabah, atau ke TELEGRAM_DEMO_CHAT_ID untuk demo."""

import httpx

import config


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_DEMO_CHAT_ID)


def format_message(record: dict) -> str:
    return f"{record['title']}\n\n{record['body']}\n\n👉 {record['cta']}\n\n{record['footer']}"


def find_chat_ids() -> list[dict]:
    """Cari chat id dari pesan terbaru yang dikirim orang ke bot (getUpdates)."""
    r = httpx.get(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates", timeout=15)
    r.raise_for_status()
    chats = {}
    for upd in r.json().get("result", []):
        chat = (upd.get("message") or upd.get("edited_message") or {}).get("chat")
        if chat:
            chats[chat["id"]] = {"chat_id": chat["id"], "nama": chat.get("first_name") or chat.get("title"),
                                 "username": chat.get("username")}
    return list(chats.values())


def send(text: str, chat_id: str | None = None) -> tuple[bool, str]:
    target = chat_id or config.TELEGRAM_DEMO_CHAT_ID
    try:
        r = httpx.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                       json={"chat_id": target, "text": text}, timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            return True, "terkirim"
        return False, f"gagal: HTTP {r.status_code}"
    except httpx.HTTPError as e:
        return False, f"gagal: {type(e).__name__}"
