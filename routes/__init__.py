# routes/__init__.py

from flask import Blueprint

auth_bp = Blueprint('auth', __name__)
data_bp = Blueprint('data', __name__)
query_bp = Blueprint('query', __name__)
users_bp = Blueprint('users', __name__)
unsub_bp = Blueprint('unsub', __name__)

def register_routes(app):
    from . import auth, data, query, users, unsub # Import modules to run their code

    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(data_bp, url_prefix='/api')
    app.register_blueprint(query_bp, url_prefix='/api')
    app.register_blueprint(users_bp, url_prefix='/api')
    app.register_blueprint(unsub_bp, url_prefix='/api')