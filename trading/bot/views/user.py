from django.shortcuts import redirect
from django.http import HttpResponse
from django.template import loader
from django.contrib.auth import authenticate, login, logout
from ..forms import LoginForm
from ..models.api_key import ApiKey


def login_handler(request):
    if request.method == 'GET':
        template = loader.get_template('bot/login.html')
        form = LoginForm()
        context = {'form': form}
        return HttpResponse(template.render(context, request))
    elif request.method == 'POST':
        form = LoginForm(request.POST)
        username = form['username'].value()
        password = form['password'].value()
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('index')
        else:
            return HttpResponse('Login Failed, Try Again.')


def logout_handler(request):
    logout(request)
    return redirect('login')


def api_key_handler(request):
    if request.method == 'GET':
        template = loader.get_template('bot/key-setting.html')
        context = {}
        return HttpResponse(template.render(context, request))
    elif request.method == 'POST':
        access_key = request.POST.get('access_key')
        secret_key = request.POST.get('secret_key')

        current_user = request.user

        if ApiKey.objects(user_email=current_user.email):
            api_key = ApiKey.objects.get(user_email=current_user.email)
            api_key.access_key = access_key
            api_key.secret_key = secret_key
            api_key.save()
        else:
            ApiKey(user_email=current_user.email, access_key=access_key, secret_key=secret_key).save()
        return redirect('trading-settings')
