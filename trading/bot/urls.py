from django.urls import path
from .views import user, common, trading

urlpatterns = [
    path('index', common.index, name='index'),
    path('login', user.login_handler, name='login'),
    path('logout', user.logout_handler, name='logout'),
    path('trading-settings', trading.trading_setting, name='trading-settings'),
    path('key-settings', user.api_key_handler, name='key-settings'),
    path('initialize-trading-settings', trading.initialize_trading_setting, name='initialize-trading-settings'),
    path('start-trading', trading.start_trading, name='start-trading'),
    path('stop-trading', trading.stop_trading, name='stop-trading'),
]
