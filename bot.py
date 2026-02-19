import os
import json
import logging
import re
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

import matplotlib.pyplot as plt
from io import BytesIO

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
spreadsheet = client.open(SHEET_NAME)

def get_month_sheet():
    sheet_name = datetime.now().strftime("%m-%Y")
    try:
        return spreadsheet.worksheet(sheet_name)
    except:
        new_sheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="5")
        new_sheet.append_row(["Tanggal", "Tipe", "Jumlah", "Kategori", "Saldo"])
        return new_sheet


# ======================
# HELPER FUNCTION
# ======================

def format_rupiah(angka):
    return f"{angka:,}".replace(",", ".")


def get_last_balance():
    sheet = get_month_sheet()
    data = sheet.get_all_values()
    if len(data) <= 1:
        return 0
    return int(data[-1][4])


# ====SUMMARY====

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = sheet.get_all_values()

    if len(data) <= 1:
        await update.message.reply_text("Belum ada data.")
        return

    rows = data[1:]

    filter_month = None
    title = "📊 RINGKASAN SEMUA DATA\n\n"

    arg_text = None
    if context.args:
        arg_text = " ".join(context.args).lower()
    
    if arg_text and arg_text.isdigit() and len(arg_text) == 4:
        year = int(arg_text)
        filter_month = year
        title = f"📊 RINGKASAN TAHUN {year}\n\n"


    if arg_text:
        # 1️⃣ Kalau user ketik "bulan"
        if arg_text == "bulan":
            filter_month = datetime.now()
            title = "📊 RINGKASAN BULAN INI\n\n"

        # 2️⃣ Format angka: 02-2026
        else:
            try:
                filter_month = datetime.strptime(arg_text, "%m-%Y")
                title = f"📊 RINGKASAN {arg_text}\n\n"
            except:
                parts = arg_text.split()

                # 3️⃣ Format: januari
                if len(parts) == 1 and parts[0] in MONTH_MAP:
                    month = MONTH_MAP[parts[0]]
                    year = datetime.now().year
                    filter_month = datetime(year, month, 1)
                    title = f"📊 RINGKASAN {parts[0].capitalize()} {year}\n\n"

                # 4️⃣ Format: januari 2026
                elif len(parts) == 2 and parts[0] in MONTH_MAP:
                    try:
                        month = MONTH_MAP[parts[0]]
                        year = int(parts[1])
                        filter_month = datetime(year, month, 1)
                        title = f"📊 RINGKASAN {parts[0].capitalize()} {year}\n\n"
                    except:
                        pass


         # ===== MODE TAHUNAN =====
    if isinstance(filter_month, int):

        (
            total_income,
            total_expense,
            last_balance,
            monthly_expense,
            biggest_month,
            biggest_category
        ) = calculate_yearly_summary(rows, filter_month)

        monthly_text = ""
        for month, amt in sorted(monthly_expense.items()):
            monthly_text += f"Bulan {month}: {format_rupiah(amt)}\n"

        message = (
            f"{title}"
            f"💰 Total Pemasukan: {format_rupiah(total_income)}\n"
            f"💸 Total Pengeluaran: {format_rupiah(total_expense)}\n"
            f"🏦 Saldo Akhir Tahun: {format_rupiah(last_balance)}\n\n"
            f"📅 Pengeluaran per Bulan:\n"
            f"{monthly_text}\n"
            f"🔥 Bulan Terbesar: {biggest_month}\n"
            f"🏆 Kategori Terboros: {biggest_category}"
        )

        await update.message.reply_text(message)
        return




    total_income, total_expense, expense_by_category, largest_transaction, largest_detail = calculate_summary(rows, filter_month)

    # Kalau tidak ada pengeluaran
    if largest_transaction == 0:
        largest_detail = "-"

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


# =====CALCULATE MONTH SUMMARY=======

def calculate_summary(rows, filter_month=None):
    total_income = 0
    total_expense = 0
    expense_by_category = {}
    largest_transaction = 0
    largest_detail = ""

    for row in rows:
        tanggal = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        tipe = row[1]
        amount = int(row[2])
        note = row[3].strip().lower() if row[3] else "lainnya"

        if filter_month:
            if tanggal.month != filter_month.month or tanggal.year != filter_month.year:
                continue

        if tipe == "Pemasukan":
            total_income += amount
        else:
            total_expense += amount
            expense_by_category[note] = expense_by_category.get(note, 0) + amount

            if amount > largest_transaction:
                largest_transaction = amount
                largest_detail = f"{tanggal.strftime('%d-%m-%Y')} | {note}"

    return total_income, total_expense, expense_by_category, largest_transaction, largest_detail

# =====================
# CALCULATE YEARLY SUMMARY
# =====================

def calculate_yearly_summary(rows, year):
    total_income = 0
    total_expense = 0
    monthly_expense = {}
    category_total = {}
    last_balance = 0

    for row in rows:
        tanggal = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        tipe = row[1]
        amount = int(row[2])
        note = row[3].strip().lower() if row[3] else "lainnya"
        saldo = int(row[4])

        if tanggal.year != year:
            continue

        last_balance = saldo

        if tipe == "Pemasukan":
            total_income += amount
        else:
            total_expense += amount

            # total pengeluaran per bulan
            month_number = tanggal.month
            monthly_expense[month_number] = monthly_expense.get(month_number, 0) + amount

            # total pengeluaran per kategori
            category_total[note] = category_total.get(note, 0) + amount

    biggest_month = "-"
    if monthly_expense:
        biggest_month = max(monthly_expense, key=monthly_expense.get)

    biggest_category = "-"
    if category_total:
        biggest_category = max(category_total, key=category_total.get)

    return (
        total_income,
        total_expense,
        last_balance,
        monthly_expense,
        biggest_month,
        biggest_category
    )


# ======DETEKSI BULAN=====

MONTH_MAP = {
    "januari": 1,
    "februari": 2,
    "maret": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "agustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}




# ======================
# COMMANDS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot aktif 🔥")


async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    balance = get_last_balance()
    await update.message.reply_text(
        f"💰 Saldo sekarang: {format_rupiah(balance)}")

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

# ===========
# CHART
# ===========

async def chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = sheet.get_all_values()

    if len(data) <= 1:
        await update.message.reply_text("Belum ada data.")
        return

    rows = data[1:]

    _, total_expense, expense_by_category, _, _ = calculate_summary(rows)

    if not expense_by_category:
        await update.message.reply_text("Belum ada pengeluaran.")
        return

    labels = list(expense_by_category.keys())
    values = list(expense_by_category.values())

    plt.figure()
    plt.pie(values, labels=labels, autopct="%1.1f%%")
    plt.title("Pengeluaran per Kategori")

    buffer = BytesIO()
    plt.savefig(buffer, format="png")
    buffer.seek(0)

    await update.message.reply_photo(photo=buffer)


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
        if amount > last_balance:
            await update.message.reply_text(
                f"❌ Saldo tidak cukup!\n"
                f"Saldo sekarang: {format_rupiah(last_balance)}"
            )
            return
        new_balance = last_balance - amount
        tipe = "Pengeluaran"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sheet = get_month_sheet()
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
    app.add_handler(CommandHandler("chart", chart))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot jalan...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()