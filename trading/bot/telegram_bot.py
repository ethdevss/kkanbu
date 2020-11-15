import telegram


class TelegramBot:
    token = '985728867:AAE9kltQqpmIdwPi510h4fzfQas59besQzE'
    bot = telegram.Bot(token)

    @classmethod
    def send_message(cls, chat_id, message):
        try:
            cls.bot.send_message(chat_id=chat_id, text=message)
        except Exception as e:
            print('raise exception while sending telegram message')
            print(e)
