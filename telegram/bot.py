import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
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
TELEGRAM_GROUP_ID = -1002410678804  # Use the group ID obtained from the updates

class TelegramBot:
    def __init__(self, token: str, proxy_url: str, group_id: int):
        self.token = token
        self.proxy_url = proxy_url.strip()
        self.group_id = group_id
        if not self.proxy_url.startswith(('http://', 'https://')):
            self.proxy_url = 'https://' + self.proxy_url
        
        self.application = Application.builder().token(self.token).build()
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.application.add_handler(CallbackQueryHandler(self.handle_button))
        logger.info(f"Initialized bot with proxy URL: {self.proxy_url}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat.id
        context.user_data[chat_id] = {'state': 'ASK_TONE'}
        await update.message.reply_text("Welcome! What tone do you want for your post? (e.g., formal, casual)")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat.id
        text = update.message.text

        # Ensure chat_id is initialized in context.user_data
        if chat_id not in context.user_data:
            context.user_data[chat_id] = {}

        state = context.user_data[chat_id].get('state')

        logger.info(f"Received message from user {chat_id}: {text}")

        if state == 'ASK_TONE':
            context.user_data[chat_id]['tone'] = text
            context.user_data[chat_id]['state'] = 'ASK_IMAGE'
            await update.message.reply_text("Please upload an image to be attached to the post.")
        elif state == 'ASK_AI_CAPTION':
            if text.lower() == 'yes':
                context.user_data[chat_id]['ai_caption'] = True
                context.user_data[chat_id]['state'] = 'ASK_CAPTION_LENGTH'
                await update.message.reply_text("How long do you want the caption to be? (e.g., short, medium, long)")
            else:
                context.user_data[chat_id]['ai_caption'] = False
                context.user_data[chat_id]['state'] = 'ASK_CAPTION'
                await update.message.reply_text("Please provide the caption for the post.")
        elif state == 'ASK_CAPTION_LENGTH':
            context.user_data[chat_id]['caption_length'] = text
            await self.generate_ai_caption(chat_id, context)
        elif state == 'ASK_CAPTION':
            context.user_data[chat_id]['caption'] = text
            await self.ask_for_approval(chat_id, context)
        elif state == 'ASK_APPROVAL':
            if text.lower() == 'yes':
                context.user_data[chat_id]['approved'] = True
                await self.post_to_telegram_group(chat_id, context)
            else:
                context.user_data[chat_id]['approved'] = False
                await update.message.reply_text("Post not approved. Please start over with /start.")

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat.id

        # Ensure chat_id is initialized in context.user_data
        if chat_id not in context.user_data:
            context.user_data[chat_id] = {}

        state = context.user_data[chat_id].get('state')

        if state == 'ASK_IMAGE':
            file_info = await context.bot.get_file(update.message.photo[-1].file_id)
            context.user_data[chat_id]['image'] = file_info.file_path
            context.user_data[chat_id]['state'] = 'ASK_AI_CAPTION'
            keyboard = [
                [InlineKeyboardButton("Yes", callback_data='yes')],
                [InlineKeyboardButton("No", callback_data='no')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Do you want the caption to be AI generated?", reply_markup=reply_markup)

    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat.id
        data = query.data

        state = context.user_data[chat_id].get('state')

        if state == 'ASK_AI_CAPTION':
            if data == 'yes':
                context.user_data[chat_id]['ai_caption'] = True
                context.user_data[chat_id]['state'] = 'ASK_CAPTION_LENGTH'
                await query.message.reply_text("How long do you want the caption to be? (e.g., short, medium, long)")
            else:
                context.user_data[chat_id]['ai_caption'] = False
                context.user_data[chat_id]['state'] = 'ASK_CAPTION'
                await query.message.reply_text("Please provide the caption for the post.")
        elif state == 'ASK_APPROVAL':
            if data == 'yes':
                context.user_data[chat_id]['approved'] = True
                await self.post_to_telegram_group(chat_id, context)
            else:
                context.user_data[chat_id]['approved'] = False
                await query.message.reply_text("Post not approved. Please start over with /start.")

    async def generate_ai_caption(self, chat_id, context):
        tone = context.user_data[chat_id]['tone']
        length = context.user_data[chat_id]['caption_length']
        try:
            response = requests.post(
                f"{self.proxy_url}/generate_caption",
                json={'tone': tone, 'length': length}
            )
            response.raise_for_status()
            caption = response.json().get('caption')
            context.user_data[chat_id]['caption'] = caption
            await self.ask_for_approval(chat_id, context)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error generating AI caption: {e}")
            await context.bot.send_message(chat_id, "Sorry, there was an error generating the caption. Please try again.")
        except ValueError as e:
            logger.error(f"Error parsing JSON response: {e}")
            await context.bot.send_message(chat_id, "Sorry, there was an error processing the response. Please try again.")

    async def ask_for_approval(self, chat_id, context):
        caption = context.user_data[chat_id]['caption']
        context.user_data[chat_id]['state'] = 'ASK_APPROVAL'
        keyboard = [
            [InlineKeyboardButton("Yes", callback_data='yes')],
            [InlineKeyboardButton("No", callback_data='no')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id, f"Here is your post:\n\nCaption: {caption}\n\nDo you approve?", reply_markup=reply_markup)

    async def post_to_telegram_group(self, chat_id, context):
        caption = context.user_data[chat_id]['caption']
        image_path = context.user_data[chat_id]['image']
        try:
            await context.bot.send_photo(self.group_id, photo=open(image_path, 'rb'), caption=caption)
            await context.bot.send_message(chat_id, "Post has been made to the group!")
        except Exception as e:
            logger.error(f"Error posting to Telegram group: {e}")
            await context.bot.send_message(chat_id, "Sorry, there was an error posting to the group. Please try again.")

    def run(self):
        logger.info("Starting bot...")
        self.application.run_polling()

def main():
    token = os.getenv("TELEGRAM_TOKEN", TELEGRAM_TOKEN)
    proxy_url = os.getenv("PROXY_URL", PROXY_URL)
    group_id = TELEGRAM_GROUP_ID  # Use the group ID directly
    
    if not proxy_url or proxy_url == "YOUR_PROXY_URL":
        raise ValueError("Please set a valid PROXY_URL")
    
    if not token or token == "YOUR_TELEGRAM_TOKEN":
        raise ValueError("Please set a valid TELEGRAM_TOKEN")
    
    if not group_id:
        raise ValueError("Please set a valid TELEGRAM_GROUP_ID")
    
    bot = TelegramBot(token, proxy_url, group_id)
    print(f"Bot started with proxy URL: {bot.proxy_url}")
    print("Press Ctrl+C to stop.")
    bot.run()

if __name__ == "__main__":
    main()