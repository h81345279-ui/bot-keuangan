import os
import json
import logging
import re

from google.oauth2.service_account import Credentials
from datetime import datetime

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from google.oauth2.service_account import Credentials

# =======================
# PERUBAHAN SEPARATOR UANG
# ========================

def format_rupiah(angka):
   return f"{angka:,}".replace(",",".")

# ======================
# ISI TOKEN BOT KAMU
# ======================
BOT_TOKEN = "8560955900:AAGFDogPD8vAD0-WTKWJHLPu-jerP5VAtGI"
SHEET_NAME = "KeuanganBot"

# ======================
# GOOGLE SHEETS SETUP
# ======================
scopes = ["https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"]

google_creds_json = os.getenv("GOOGLE_CREDENTIALS")
google_creds_dict = json.loads(google_creds_json)

creds = Credentials.from_service_account_info(
    google_creds_dict,
    scopes=scopes


)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# ======================
# AMBIL SALDO TERAKHIR
# ======================
def get_last_balance():
    data = sheet.get_all_values()
    if len(data) <= 1:
        return 0
    return int(data[-1][4])

# ======================
# COMMAND /saldo
# ======================
async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    balance = get_last_balance()
    await update.message.reply_text(f"💰 Saldo sekarang: {balance:,}".replace(",","."))

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
    logging.basicConfig(level=logging.INFO)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot jalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
