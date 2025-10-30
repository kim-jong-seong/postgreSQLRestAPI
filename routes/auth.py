from flask import Blueprint, request, jsonify
import bcrypt
import jwt
from datetime import datetime, timedelta
from database import get_db_connection
from config import Config
from psycopg2.extras import RealDictCursor

auth_bp = Blueprint('auth', __name__, url_prefix='/api')

@auth_bp.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        name = data.get('name')
        
        if not email or not password or not name:
            return jsonify({'error': '모든 필드를 입력해주세요'}), 400
        
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '이미 존재하는 이메일입니다'}), 409
        
        cur.execute(
            "INSERT INTO users (email, password, name) VALUES (%s, %s, %s) RETURNING id",
            (email, hashed_password, name)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'message': '회원가입 성공',
            'user_id': user_id
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': '이메일과 비밀번호를 입력해주세요'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()

        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': '존재하지 않는 이메일입니다'}), 404
        
        if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            cur.close()
            conn.close()
            return jsonify({'error': '비밀번호가 일치하지 않습니다'}), 401
        
        token = jwt.encode({
            'user_id': user['id'],
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, Config.SECRET_KEY, algorithm="HS256")

        cur.close()
        conn.close()

        return jsonify({
            'message': '로그인 성공',
            'token': token,
            'user': {
                'id': user['id'],
                'email': user['email'],
                'name': user['name']
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500