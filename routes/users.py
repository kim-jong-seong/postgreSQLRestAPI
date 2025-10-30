from flask import Blueprint, request, jsonify
import bcrypt
from database import get_db_connection
from middlewares.auth import token_required
from psycopg2.extras import RealDictCursor

users_bp = Blueprint('users', __name__, url_prefix='/api/users')

@users_bp.route('/me', methods=['GET'])
@token_required
def get_my_info(current_user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id, email, name, created_at FROM users WHERE id = %s", (current_user_id,))
        user = cur.fetchone()

        cur.close()
        conn.close()

        if not user:
            return jsonify({'error': '사용자를 찾을 수 없습니다'}), 404
        
        return jsonify({'user': user}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ... 나머지 users 엔드포인트들