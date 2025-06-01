from flask import Blueprint

# Create blueprints for different API sections
auth_bp = Blueprint('auth', __name__)
file_management_bp = Blueprint('file_management', __name__)
query_bp = Blueprint('query', __name__)
user_management_bp = Blueprint('user_management', __name__)

def register_routes(app):
    from . import auth, file_management, query, user_management # Import modules to run their code

    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(file_management_bp, url_prefix='/api')
    app.register_blueprint(query_bp, url_prefix='/api')
    app.register_blueprint(user_management_bp, url_prefix='/api')