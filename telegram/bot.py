import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import os
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROXY_URL = "https://l-x.vercel.app"

class TelegramBot:
    def __init__(self, token: str, proxy_url: str):
        self.token = token
        self.proxy_url = proxy_url.strip()
        if not self.proxy_url.startswith(('http://', 'https://')):
            self.proxy_url = 'https://' + self.proxy_url
        
        self.application = Application.builder().token(self.token).build()
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        logger.info(f"Initialized bot with proxy URL: {self.proxy_url}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat.id
        context.user_data[chat_id] = {}
        await update.message.reply_text("Welcome! What tone do you want for your post? (e.g., formal, casual)")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat.id
        text = update.message.text

        if 'tone' not in context.user_data[chat_id]:
            context.user_data[chat_id]['tone'] = text
            await update.message.reply_text("Please upload an image to be attached to the post.")
        elif 'ai_caption' not in context.user_data[chat_id]:
            if text.lower() == 'yes':
                context.user_data[chat_id]['ai_caption'] = True
                await update.message.reply_text("How long do you want the caption to be? (e.g., short, medium, long)")
            else:
                context.user_data[chat_id]['ai_caption'] = False
                await update.message.reply_text("Please provide the caption for the post.")
        elif 'caption_length' not in context.user_data[chat_id] and context.user_data[chat_id]['ai_caption']:
            context.user_data[chat_id]['caption_length'] = text
            await self.generate_ai_caption(chat_id, context)
        elif 'caption' not in context.user_data[chat_id]:
            context.user_data[chat_id]['caption'] = text
            await self.ask_for_approval(chat_id, context)
        elif 'approved' not in context.user_data[chat_id]:
            if text.lower() == 'yes':
                context.user_data[chat_id]['approved'] = True
                await self.post_to_telegram_group(chat_id, context)
            else:
                context.user_data[chat_id]['approved'] = False
                await update.message.reply_text("Post not approved. Please start over with /start.")

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat.id
        file_info = await context.bot.get_file(update.message.photo[-1].file_id)
        context.user_data[chat_id]['image'] = file_info.file_path
        await update.message.reply_text("Do you want the caption to be AI generated? (yes/no)")

    async def generate_ai_caption(self, chat_id, context):
        tone = context.user_data[chat_id]['tone']
        length = context.user_data[chat_id]['caption_length']
        response = requests.post(
            f"{self.proxy_url}/generate_caption",
            json={'tone': tone, 'length': length}
        )
        caption = response.json().get('caption')
        context.user_data[chat_id]['caption'] = caption
        await self.ask_for_approval(chat_id, context)

    async def ask_for_approval(self, chat_id, context):
        caption = context.user_data[chat_id]['caption']
        await context.bot.send_message(chat_id, f"Here is your post:\n\nCaption: {caption}\n\nDo you approve? (yes/no)")

    async def post_to_telegram_group(self, chat_id, context):
        group_id = 'YOUR_TELEGRAM_GROUP_ID'
        caption = context.user_data[chat_id]['caption']
        image_path = context.user_data[chat_id]['image']
        await context.bot.send_photo(group_id, photo=open(image_path, 'rb'), caption=caption)
        await context.bot.send_message(chat_id, "Post has been made to the group!")

    def run(self):
        logger.info("Starting bot...")
        self.application.run_polling()

def main():
    token = os.getenv("TELEGRAM_TOKEN", TELEGRAM_TOKEN)
    proxy_url = os.getenv("PROXY_URL", PROXY_URL)
    
    if not proxy_url or proxy_url == "YOUR_PROXY_URL":
        raise ValueError("Please set a valid PROXY_URL")
    
    if not token or token == "YOUR_TELEGRAM_TOKEN":
        raise ValueError("Please set a valid TELEGRAM_TOKEN")
    
    bot = TelegramBot(token, proxy_url)
    print(f"Bot started with proxy URL: {bot.proxy_url}")
    print("Press Ctrl+C to stop.")
    bot.run()

if __name__ == "__main__":
    main()