from flask import Blueprint, render_template, request, redirect, url_for, session, send_from_directory
from app.extensions import db
from app.models import User
import os
import pandas as pd
import stripe
from datetime import datetime
from flask_jwt_extended import jwt_required
from flask_jwt_extended import get_jwt_identity
from flask_jwt_extended import unset_jwt_cookies

from flask import jsonify
import os

from flask import current_app

routes = Blueprint('routes', __name__)

# Your webhook secret (не API ключ!)
# Получите его из Stripe > Webhooks > Show signing secret
endpoint_secret = 'whsec_mJCq05VFPTnkhgsekFvv7GKMGfWxb7RB'
# Загрузка Price ID из файла
with open("priceid.txt", "r") as f:
    PRICE_ID = f.read().strip()
routes = Blueprint('routes', __name__)

@routes.route('/')
def home():
    return redirect(url_for('routes.login'))

from flask import request, render_template, redirect, url_for, session, jsonify, make_response
from flask_jwt_extended import create_access_token, set_access_cookies

@routes.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session['user'] = user.username
            session['email'] = user.email

            # ✅ Генеруємо access token
            access_token = create_access_token(identity=email)

            # ✅ Створюємо відповідь і додаємо токен як cookie
            response = make_response(redirect(url_for('routes.dashboard')))
            set_access_cookies(response, access_token)

            return response

        return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')


@routes.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email'].lower()
        password = request.form['password']
        user = User(username=username, email=email, credits=1)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('routes.login'))
    return render_template('register.html')

@routes.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('routes.login'))

    user = User.query.filter_by(email=session['email']).first()
    return render_template('dashboard.html', user=user, username=user.username)

@routes.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    response = jsonify({"msg": "Logout successful"})
    unset_jwt_cookies(response)
    return redirect(url_for('routes.login'))

@routes.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user' not in session:
        return redirect(url_for('routes.login'))

    download_link = None
    error = None

    user = User.query.filter_by(email=session['email']).first()

    # 🔐 Проверка подписки и кредитов
    if not user.is_subscribed and user.credits <= 0:
        error = "❌ No credits left. Please subscribe to continue."
        return render_template('upload.html', download_link=None, error=error)

    if request.method == 'POST':
        if 'csv_file' not in request.files:
            error = "No file uploaded"
        else:
            file = request.files['csv_file']
            if file.filename.endswith('.csv'):
                try:
                    df = pd.read_csv(file)
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    filename = f"converted_{timestamp}.xlsx"

                    output_dir = os.path.join(os.getcwd(), 'Output')
                    os.makedirs(output_dir, exist_ok=True)
                    filepath = os.path.join(output_dir, filename)

                    df.to_excel(filepath, index=False)

                    # ✅ Списываем кредит только если нет подписки
                    if not user.is_subscribed:
                        user.credits -= 1
                        db.session.commit()

                    download_link = url_for('routes.download_file', filename=filename)
                except Exception as e:
                    error = f"Conversion error: {str(e)}"
            else:
                error = "Please upload a .csv file"

    return render_template('upload.html', download_link=download_link, error=error)

@routes.route('/download/<filename>')
def download_file(filename):
    output_dir = os.path.join(os.getcwd(), 'Output')
    return send_from_directory(output_dir, filename, as_attachment=True)

# Подключаем ключи из Sandbox
#stripe.api_key = 'price_1RQA9tPEKRLZftEaFkM6iaxk'  # ← вставьте ваш Secret Key
stripe.api_key = 'sk_test_51RQ9yxPEKRLZftEaieAl0HRhXNghS1VWqxtIG8fxB1dkrkP9y1LbPZR0EQuZDgnONI86SA3va6F0BqXbjXJtL4EA00usSx0GdW'  # Вставьте настоящий СЕКРЕТНЫЙ ключ

# Загрузка Price ID из файла
with open("priceid.txt", "r") as f:
    print("DEBUG: открываем файл priceid.txt")
    PRICE_ID = f.read().strip()

@routes.route('/subscribe', methods=['GET'], endpoint='subscribe')
@jwt_required()
def subscribe():
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price': PRICE_ID,
            'quantity': 1,
        }],
        mode='subscription',
        success_url=url_for('routes.dashboard', _external=True),
        cancel_url=url_for('routes.dashboard', _external=True),
        metadata={'user_email': get_jwt_identity()}
    )
    return redirect(session.url, code=303)


# ⚠️ Секрет Stripe webhook — получим из Stripe Dashboard
STRIPE_WEBHOOK_SECRET = 'whsec_tAElpn94llbIf0nYnELrBQAPKNlJ0jvA'  # ← заменим позже

@routes.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError as e:
        print("❌ Неверный payload")
        return jsonify(success=False), 400
    except stripe.error.SignatureVerificationError as e:
        print("❌ Неверная подпись")
        return jsonify(success=False), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        # Получаем customer_id
        customer_id = session.get("customer")
        email = None

        if customer_id:
            try:
                customer = stripe.Customer.retrieve(customer_id)
                email = customer.get("email")
            except Exception as e:
                print("❌ Ошибка получения email клиента из Stripe:", e)

        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                print(f"✅ Подписка активирована для {email}")
                user.is_subscribed = True
                db.session.commit()
            else:
                print(f"❌ Пользователь {email} не найден")
        else:
            print("❌ Email клиента не найден")

    return jsonify(success=True), 200
