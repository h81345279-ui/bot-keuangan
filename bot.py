import os
import json
import logging
import re
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

# ======================
# GOOGLE SHEETS SETUP
# ======================

SHEET_NAME = "KeuanganBot"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

google_creds_json = os.getenv("GOOGLE_CREDENTIALS")
google_creds_dict = json.loads(google_creds_json)

creds = Credentials.from_service_account_info(
    google_creds_dict,
    scopes=scopes
)

client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1


# ======================
# HELPER FUNCTION
# ======================

def format_rupiah(angka):
    return f"{angka:,}".replace(",", ".")


def get_last_balance():
    data = sheet.get_all_values()
    if len(data) <= 1:
        return 0
    return int(data[-1][4])


# ======================
# COMMANDS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot aktif 🔥")


async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    balance = get_last_balance()
    await update.message.reply_text(
        f"💰 Saldo sekarang: {format_rupiah(balance)}"
    )


# ======================
# HANDLE CHAT
# ======================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    pattern = r"^([+-])(\d+)\s*(.*)$"
    match = re.match(pattern, text)

    if not match:
        await update.message.reply_text(
            "Format salah.\nContoh:\n+50000 gaji\n-20000 makan"
        )
        return

    sign, amount, note = match.groups()
    amount = int(amount)

    last_balance = get_last_balance()

    if sign == "+":
        new_balance = last_balance + amount
        tipe = "Pemasukan"
    else:
        new_balance = last_balance - amount
        tipe = "Pengeluaran"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sheet.append_row([
        now,
        tipe,
        amount,
        note,
        new_balance
    ])

    await update.message.reply_text(
        f"✅ {tipe}: {format_rupiah(amount)}\n"
        f"💰 Saldo sekarang: {format_rupiah(new_balance)}"
    )


# ======================
# MAIN
# ======================

def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )

    bot_token = os.getenv("BOT_TOKEN")

    if not bot_token:
        raise ValueError("BOT_TOKEN tidak ditemukan di environment variables")

    app = ApplicationBuilder().token(bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot jalan...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()