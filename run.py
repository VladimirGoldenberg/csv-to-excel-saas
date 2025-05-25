from flask import Flask
from app.extensions import db
from app.routes import routes
import os
from app import create_app

app = Flask(
    __name__,
    static_folder='app/static',
    template_folder='app/templates',
    instance_relative_config=True
)

# Конфигурация
app.secret_key = 'secret'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# Правильный абсолютный путь к базе данных
db_path = os.path.join(app.instance_path, 'users.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация и регистрация
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
