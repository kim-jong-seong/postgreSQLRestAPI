from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt
import jwt
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
CORS(app) # React에서 접근 가능하도록

# 설정
app.config['SECRET_KEY'] = 'your_secret_key'

# DB 연결 함수
def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="postgres",
        user="postgres",
        password="(whdtjd12?)"
    )

    return conn

# JWT 토큰 검증 데코레이터
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')

        if not token:
            return jsonify({'error': '토큰이 필요합니다'}), 401
        
        try:
            # "Bearer TOKEN" 형식에서 토큰만 추출
            if token.startswith('Bearer '):
                token = token[7:]  

            data = jwt.decode(token, app.config['SECRET_KEY'], algrithms=["HS256"])
            current_user_id = data['user_id']
        except:
            return jsonify({'error': '유효하지 않은 토큰입니다'}), 401
        
        return f(current_user_id, *args, **kwargs)
    
    return decorated

# 1. 헬스체크
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'API 서버가 정상 작동 중입니다'})

# 2. 회원가입
@app.route('/api/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        name = data.get('name')
        
        # 입력 검증
        if not email or not password or not name:
            return jsonify({'error': '모든 필드를 입력해주세요'}), 400
        
        # 비밀번호 해시화 (문자열로 변환)
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 이메일 중복 확인
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '이미 존재하는 이메일입니다'}), 409
        
        # 사용자 생성
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
    
# 3. 로그인
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': '이메일과 비밀번호를 입력해주세요'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 사용자 조회
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()

        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': '존재하지 않는 이메일입니다'}), 404
        
        # 비밀번호 검증
        if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            cur.close()
            conn.close()
            return jsonify({'error': '비밀번호가 일치하지 않습니다'}), 401
        
        # JWT 토큰 생성(24시간 유효)
        token = jwt.encode({
            'user_id': user['id'],
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")

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
    
# 4. 사용자 정보 조회 (토큰 필요)
@app.route('/api/users/me', methods=['GET'])
@token_required
def get_my_info(current_user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 사용자 조회
        cur.execute("SELECT id, email, name, created_at FROM users WHERE id = %s", (current_user_id,))
        user = cur.fetchone()

        cur.close()
        conn.close()

        if not user:
            return jsonify({'error': '사용자를 찾을 수 없습니다'}), 404
        
        return jsonify({'user': user}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# 5. 전체 사용자 목록 조회
@app.route('/api/users', methods=['GET'])
def get_all_users():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id, email, name, created_at FROM users")
        users = cur.fetchall()

        cur.close()
        conn.close()

        return jsonify({'users': [dict(users) for user in users]}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# 6. 특정 사용자 조회
@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor) # 딕셔너리 형태로 결과 반환

        # 사용자 조회
        cur.execute("SELECT id, email, name, created_at FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()

        cur.close()
        conn.close()

        if not user:
            return jsonify({'error': '사용자를 찾을 수 없습니다'}), 404
        
        return jsonify({'user': dict(user)}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# 7. 내 정보 수정 (토큰 필요)
@app.route('/api/users/me', methods=['PUT'])
@token_required
def update_my_info(current_user_id):
    try:
        data = request.json
        name = data.get('name')
        
        if not name:
            return jsonify({'error': '이름을 입력해주세요'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "UPDATE users SET name = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (name, current_user_id)
        )
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'message': '정보 수정 성공'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 8. 비밀번호 변경 (토큰 필요)
@app.route('/api/users/me/password', methods=['PUT'])
@token_required
def change_password(current_user_id):
    try:
        data = request.json
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        
        if not old_password or not new_password:
            return jsonify({'error': '기존 비밀번호와 새 비밀번호를 입력해주세요'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 기존 비밀번호 확인
        cur.execute("SELECT password FROM users WHERE id = %s", (current_user_id,))
        user = cur.fetchone()
        
        if not bcrypt.checkpw(old_password.encode('utf-8'), user['password'].encode('utf-8')):
            cur.close()
            conn.close()
            return jsonify({'error': '기존 비밀번호가 일치하지 않습니다'}), 401
        
        # 새 비밀번호 해시화
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        
        # 비밀번호 업데이트
        cur.execute(
            "UPDATE users SET password = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (hashed_password.decode('utf-8'), current_user_id)
        )
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'message': '비밀번호 변경 성공'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 9. 회원 탈퇴 (토큰 필요)
@app.route('/api/users/me', methods=['DELETE'])
@token_required
def delete_my_account(current_user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("DELETE FROM users WHERE id = %s", (current_user_id,))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({'message': '회원 탈퇴 성공'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 서버 실행 ====================
if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Flask API 서버 시작")
    print("=" * 50)
    print("📍 서버 주소: http://0.0.0.0:5000")
    print("\n📚 API 엔드포인트:")
    print("  GET    /api/health          - 헬스체크")
    print("  POST   /api/signup          - 회원가입")
    print("  POST   /api/login           - 로그인")
    print("  GET    /api/users           - 전체 사용자 조회")
    print("  GET    /api/users/<id>      - 특정 사용자 조회")
    print("  GET    /api/users/me        - 내 정보 조회 (토큰 필요)")
    print("  PUT    /api/users/me        - 내 정보 수정 (토큰 필요)")
    print("  PUT    /api/users/me/password - 비밀번호 변경 (토큰 필요)")
    print("  DELETE /api/users/me        - 회원 탈퇴 (토큰 필요)")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=True)