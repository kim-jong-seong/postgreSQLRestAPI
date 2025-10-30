from flask import Blueprint, request, jsonify
from psycopg2.extras import RealDictCursor
from database import get_db_connection
from middlewares.auth import token_required

houses_bp = Blueprint('houses', __name__, url_prefix='/api/houses')

# 1. 내가 속한 모든 집 조회
@houses_bp.route('/', methods=['GET'])
@token_required
def get_my_houses(current_user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute(
            """
            SELECT 
                h.id, 
                h.name, 
                hm.role_cd,
                hm.seq,
                h.created_at
            FROM houses h
            JOIN house_members hm ON h.id = hm.house_id
            WHERE hm.user_id = %s
            ORDER BY h.id
            """,
            (current_user_id,)
        )
        houses = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'houses': houses}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 2. 집 생성
@houses_bp.route('/', methods=['POST'])
@token_required
def create_house(current_user_id):
    try:
        data = request.json
        house_name = data.get('name')
        
        if not house_name:
            return jsonify({'error': '집 이름을 입력해주세요'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 집 생성
        cur.execute(
            """
            INSERT INTO houses (name, created_user, updated_user)
            VALUES (%s, %s, %s)
            RETURNING id, name, created_at
            """,
            (house_name, current_user_id, current_user_id)
        )
        house = cur.fetchone()
        
        # 구성원 등록 (관리자)
        cur.execute(
            """
            INSERT INTO house_members (house_id, user_id, role_cd, created_user, updated_user)
            VALUES (%s, %s, 'COM1100001', %s, %s)
            RETURNING seq
            """,
            (house['id'], current_user_id, current_user_id, current_user_id)
        )
        member = cur.fetchone()
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'message': '집 생성 성공',
            'house': {
                'id': house['id'],
                'name': house['name'],
                'role_cd': 'COM1100001',
                'seq': member['seq'],
                'created_at': house['created_at'].isoformat()
            }
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500

# 3. 집 삭제
@houses_bp.route('/<house_id>', methods=['DELETE'])
@token_required
def delete_house(current_user_id, house_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인
        cur.execute(
            """
            SELECT role_cd 
            FROM house_members 
            WHERE house_id = %s AND user_id = %s
            """,
            (house_id, current_user_id)
        )
        member = cur.fetchone()
        
        if not member:
            return jsonify({'error': '해당 집의 구성원이 아닙니다'}), 403
        
        if member['role_cd'] != 'COM1100001':
            return jsonify({'error': '관리자만 집을 삭제할 수 있습니다'}), 403
        
        # 집 삭제
        cur.execute("DELETE FROM houses WHERE id = %s", (house_id,))
        
        if cur.rowcount == 0:
            return jsonify({'error': '존재하지 않는 집입니다'}), 404
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': '집 삭제 성공'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500