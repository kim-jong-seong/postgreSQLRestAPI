from flask import Blueprint

def register_blueprints(app):
    from routes.auth import auth_bp
    from routes.users import users_bp
    # from routes.houses import houses_bp
    # from routes.containers import containers_bp
    # ... 등등
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    # app.register_blueprint(houses_bp)
    # app.register_blueprint(containers_bp)