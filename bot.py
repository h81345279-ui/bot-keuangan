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

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = sheet.get_all_values()

    if len(data) <= 1:
        await update.message.reply_text("Belum ada data.")
        return

    rows = data[1:]

    filter_month = None
    title = "📊 RINGKASAN SEMUA DATA\n\n"

    if context.args:
        arg = context.args[0].lower()

        if arg == "bulan":
            filter_month = datetime.now()
            title = "📊 RINGKASAN BULAN INI\n\n"
        else:
            try:
                filter_month = datetime.strptime(arg, "%m-%Y")
                title = f"📊 RINGKASAN {arg}\n\n"
            except:
                pass

    total_income, total_expense, expense_by_category, largest_transaction, largest_detail = calculate_summary(rows, filter_month)

    percent_text = ""
    for cat, amt in expense_by_category.items():
        percent = (amt / total_expense) * 100 if total_expense else 0
        percent_text += f"{cat}: {format_rupiah(amt)} ({percent:.1f}%)\n"

    message = (
        f"{title}"
        f"💰 Total Pemasukan: {format_rupiah(total_income)}\n"
        f"💸 Total Pengeluaran: {format_rupiah(total_expense)}\n\n"
        f"🔥 Transaksi Terbesar:\n"
        f"{largest_detail} - {format_rupiah(largest_transaction)}\n\n"
        f"📂 Pengeluaran per Kategori:\n"
        f"{percent_text}"
    )

    await update.message.reply_text(message)



# ======================
# COMMANDS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot aktif 🔥")


async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    balance = get_last_balance()
    await update.message.reply_text(
        f"💰 Saldo sekarang: {format_rupiah(balance)}")


# ===SUMMARY===

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = sheet.get_all_values()

    if len(data) <= 1:
        await update.message.reply_text("Belum ada data.")
        return

    rows = data[1:]

    filter_month = False
    now = datetime.now()

    # Cek apakah user ketik /summary bulan
    if context.args and context.args[0].lower() == "bulan":
        filter_month = True

    total_income = 0
    total_expense = 0
    expense_by_category = {}
    largest_transaction = 0
    largest_detail = ""

    for row in rows:
        tanggal_str = row[0]
        tipe = row[1]
        amount = int(row[2])
        note = row[3]

        tanggal = datetime.strptime(tanggal_str, "%Y-%m-%d %H:%M:%S")

        if filter_month:
            if tanggal.month != now.month or tanggal.year != now.year:
                continue

        if tipe == "Pemasukan":
            total_income += amount
        else:
            total_expense += amount

            category = note.strip().lower() if note else "lainnya"

            expense_by_category[category] = expense_by_category.get(category, 0) + amount

            if amount > largest_transaction:
                largest_transaction = amount
                largest_detail = f"{tanggal.strftime('%d-%m-%Y')} | {category}"

    if total_expense > 0:
        percent_text = ""
        for cat, amt in expense_by_category.items():
            percent = (amt / total_expense) * 100
            percent_text += f"{cat}: {format_rupiah(amt)} ({percent:.1f}%)\n"
    else:
        percent_text = "Tidak ada pengeluaran."

    title = "📊 RINGKASAN BULAN INI\n\n" if filter_month else "📊 RINGKASAN SEMUA DATA\n\n"

    message = (
        f"{title}"
        f"💰 Total Pemasukan: {format_rupiah(total_income)}\n"
        f"💸 Total Pengeluaran: {format_rupiah(total_expense)}\n\n"
        f"🔥 Transaksi Terbesar:\n"
        f"{largest_detail} - {format_rupiah(largest_transaction)}\n\n"
        f"📂 Pengeluaran per Kategori:\n"
        f"{percent_text}"
    )

    await update.message.reply_text(message)

# ==========
# TOP
# ==========

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = sheet.get_all_values()

    if len(data) <= 1:
        await update.message.reply_text("Belum ada data.")
        return

    rows = data[1:]

    _, total_expense, expense_by_category, _, _ = calculate_summary(rows)

    if not expense_by_category:
        await update.message.reply_text("Belum ada data pengeluaran.")
        return

    sorted_categories = sorted(
        expense_by_category.items(),
        key=lambda x: x[1],
        reverse=True
    )

    message = "🏆 TOP 3 PENGELUARAN\n\n"

    for i, (cat, amt) in enumerate(sorted_categories[:3], start=1):
        percent = (amt / total_expense) * 100
        message += f"{i}. {cat} - {format_rupiah(amt)} ({percent:.1f}%)\n"

    await update.message.reply_text(message)




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
   
  # =====Normalisasi kategori disini ya====
    
    note = note.strip().lower() if note else "lainnya"

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
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot jalan...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()