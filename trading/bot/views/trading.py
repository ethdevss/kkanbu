import arrow
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from bot.models.api_key import ApiKey
from bot.scheduler.bot_scheduler import BotScheduler
from bot.strategy.rsi import Rsi
from bot.telegram_bot import TelegramBot
from collector.models.strategy import RsiStrategy

scheduler = BotScheduler()
scheduler.start()

telegram_chat_id = "784845620"


@login_required
def initialize_trading_setting(request):
    if request.method == 'POST':
        RsiStrategy.objects().delete()
        return redirect('trading-settings')


@login_required
def trading_setting(request):
    if request.method == 'GET':
        if RsiStrategy.objects(is_running=True):
            rsi_strategy = RsiStrategy.objects(is_running=True).order_by('-created_at').first()
            context = {'is_running': True, 'rsi_strategy': rsi_strategy}
        elif RsiStrategy.objects(is_running=False):
            rsi_strategy = RsiStrategy.objects(is_running=False).order_by('-created_at').first()
            context = {'is_exist_strategy': True, 'rsi_strategy': rsi_strategy}
        else:
            context = {}
        return render(request, 'bot/trading-setting.html', context=context)
    elif request.method == 'POST':
        target_major_market_codes = request.POST.get('target_major_market_codes')
        target_major_market_codes = target_major_market_codes.replace(" ", "").split(',')
        target_minor_market_codes = request.POST.get('target_minor_market_codes')
        target_minor_market_codes = target_minor_market_codes.replace(" ", "").split(',')

        major_crypto_buy_percentage = int(request.POST.get('major_crypto_buy_percentage'))
        minor_crypto_buy_percentage = int(request.POST.get('minor_crypto_buy_percentage'))

        open_position_rsi = int(request.POST.get('open_position_rsi'))
        take_profit_percentage = int(request.POST.get('take_profit_percentage'))
        take_profit_rsi = int(request.POST.get('take_profit_rsi'))

        stop_loss_percentage = int(request.POST.get('stop_loss_percentage'))
        target_candle_minute = int(request.POST.get('target_candle_minute'))

        if RsiStrategy.objects(is_running=True): # 실행중인 RSI 전략이 존재한다면, 해당 전략을 정지하고 새로운 전략을 설정 하라는 안내 메세지를 리턴한다.
            context = {'message': 'There is already running strategy, Stop running strategies and add new strategy.'}
            return render(request, 'bot/trading-setting.html', context=context)

        RsiStrategy(target_major_market_codes=target_major_market_codes, target_minor_market_codes=target_minor_market_codes,
                    major_crypto_buy_percentage=major_crypto_buy_percentage, minor_crypto_buy_percentage=minor_crypto_buy_percentage,
                    open_position_rsi=open_position_rsi, take_profit_percentage=take_profit_percentage, take_profit_rsi=take_profit_rsi,
                    stop_loss_percentage=stop_loss_percentage, target_candle_minute=target_candle_minute, created_at=arrow.now()).save()
        return redirect('trading-settings')


@login_required
def start_trading(request):
    if request.method == 'POST':
        rsi_strategy = RsiStrategy.objects().order_by('-created_at').first()
        if rsi_strategy:
            user_email = request.user.email
            api_key = ApiKey.objects.get(user_email=user_email)

            # add strategy job for trading
            kwargs = {'target_major_market_codes': rsi_strategy.target_major_market_codes, 'target_minor_market_codes': rsi_strategy.target_minor_market_codes,
                      'major_crypto_buy_percentage': rsi_strategy.major_crypto_buy_percentage,
                      'minor_crypto_buy_percentage': rsi_strategy.minor_crypto_buy_percentage,
                      'open_position_rsi': rsi_strategy.open_position_rsi, 'take_profit_percentage': rsi_strategy.take_profit_percentage,
                      'take_profit_rsi': rsi_strategy.take_profit_rsi, 'stop_loss_percentage': rsi_strategy.stop_loss_percentage,
                      'target_candle_minute': rsi_strategy.target_candle_minute, 'access_key': api_key.access_key, 'secret_key': api_key.secret_key}

            message = f"자동 매매 프로그램을 시작합니다. 아래는 자동매매 전략 설정 내용입니다." \
                      f"트레이딩 대상 메이저 코인 목록: {rsi_strategy.target_major_market_codes}, 트레이딩 대상 마이너 코인 목록: {rsi_strategy.target_minor_market_codes}," \
                      f"메이저 코인 매수 비율: {rsi_strategy.major_crypto_buy_percentage}, 마이너 코인 매수 비율: {rsi_strategy.minor_crypto_buy_percentage}, " \
                      f"포지션 진입 기준 RSI: {rsi_strategy.open_position_rsi}, 익절 퍼센트: {rsi_strategy.take_profit_percentage}, " \
                      f"익절 RSI: {rsi_strategy.take_profit_rsi}, 손절 퍼센트: {rsi_strategy.stop_loss_percentage}, " \
                      f"대상 분봉 캔들: {rsi_strategy.target_candle_minute}"

            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

            scheduler.add_job(job_id="rsi_job", func=Rsi.run, minute='*', second='2', kwargs=kwargs)
            rsi_strategy.is_running = True
            rsi_strategy.save()
        return redirect('trading-settings')


@login_required
def stop_trading(request):
    if request.method == 'POST':
        rsi_strategy = RsiStrategy.objects(is_running=True).order_by('-created_at').first()
        if rsi_strategy:
            # remove strategy job
            scheduler.remove_job(job_id="rsi_job")
            rsi_strategy.is_running = False
            rsi_strategy.save()

            message = f"자동 매매 프로그램을 중지합니다."
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

        return redirect('trading-settings')
