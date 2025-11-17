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
                cd.nm as role_nm,
                h.created_at,
                admin.name as admin_name,
                member_count.count as member_count,
                container_count.count as container_count
            FROM houses h
                JOIN house_members hm ON h.id = hm.house_id
                LEFT JOIN com_code_d cd ON hm.role_cd = cd.cd
                LEFT JOIN (
                    SELECT house_id, user_id
                    FROM house_members
                    WHERE role_cd = 'COM1100001'
                ) admin_member ON h.id = admin_member.house_id
                LEFT JOIN users admin ON admin_member.user_id = admin.id
                LEFT JOIN (
                    SELECT house_id, COUNT(*) as count
                    FROM house_members
                    GROUP BY house_id
                ) member_count ON h.id = member_count.house_id
                LEFT JOIN (
                    SELECT house_id, COUNT(*) as count
                    FROM containers
                    WHERE up_container_id IS NULL
                    GROUP BY house_id
                ) container_count ON h.id = container_count.house_id
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
    
# 4. 집 나가기 (멤버 전용)
@houses_bp.route('/<house_id>/leave', methods=['DELETE'])
@token_required
def leave_house(current_user_id, house_id):
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
        
        # 관리자는 나갈 수 없음
        if member['role_cd'] == 'COM1100001':
            return jsonify({'error': '관리자는 나갈 수 없습니다. 먼저 다른 사람에게 관리자 권한을 양도하거나 집을 삭제하세요'}), 403
        
        # 멤버 삭제
        cur.execute(
            "DELETE FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        
        if cur.rowcount == 0:
            return jsonify({'error': '이미 나간 집입니다'}), 404
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': '집에서 나갔습니다'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    

# 5. 특정 집의 구성원 목록 조회
@houses_bp.route('/<house_id>/members', methods=['GET'])
@token_required
def get_house_members(current_user_id, house_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인 (해당 집의 구성원인지)
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        member = cur.fetchone()
        
        if not member:
            return jsonify({'error': '해당 집의 구성원이 아닙니다'}), 403
        
        # 구성원 목록 조회
        cur.execute(
            """
            SELECT 
                hm.user_id,
                u.name as user_name,
                u.email,
                hm.role_cd,
                cd.nm as role_nm,
                hm.created_at as joined_at
            FROM house_members hm
                JOIN users u ON hm.user_id = u.id
                LEFT JOIN com_code_d cd ON hm.role_cd = cd.cd
            WHERE hm.house_id = %s
            ORDER BY 
                CASE WHEN hm.role_cd = 'COM1100001' THEN 0 ELSE 1 END,
                hm.created_at
            """,
            (house_id,)
        )
        members = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'members': members,
            'my_role': member['role_cd']
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 6. 구성원 추방 (관리자 전용)
@houses_bp.route('/<house_id>/members/<user_id>', methods=['DELETE'])
@token_required
def kick_member(current_user_id, house_id, user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인 (관리자인지)
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        member = cur.fetchone()
        
        if not member:
            return jsonify({'error': '해당 집의 구성원이 아닙니다'}), 403
        
        if member['role_cd'] != 'COM1100001':
            return jsonify({'error': '관리자만 추방할 수 있습니다'}), 403
        
        # 자기 자신 추방 방지
        if current_user_id == user_id:
            return jsonify({'error': '자기 자신은 추방할 수 없습니다'}), 400
        
        # 대상이 관리자인지 확인
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, user_id)
        )
        target = cur.fetchone()
        
        if not target:
            return jsonify({'error': '해당 구성원을 찾을 수 없습니다'}), 404
        
        if target['role_cd'] == 'COM1100001':
            return jsonify({'error': '관리자는 추방할 수 없습니다'}), 400
        
        # 추방 실행
        cur.execute(
            "DELETE FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, user_id)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': '구성원을 추방했습니다'}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500


# 7. 집 전체 히스토리 조회
@houses_bp.route('/<house_id>/logs', methods=['GET'])
@token_required
def get_house_logs(current_user_id, house_id):
    """
    집의 전체 활동 히스토리 조회

    Query Parameters:
    - limit: 조회할 로그 개수 (기본 3개, 최대 100개)
    """
    try:
        # limit 파라미터 (기본 3개)
        limit = request.args.get('limit', 3, type=int)
        if limit > 100:
            limit = 100

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 권한 확인 (해당 집의 구성원인지)
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        member = cur.fetchone()

        if not member:
            cur.close()
            conn.close()
            return jsonify({'error': '해당 집의 구성원이 아닙니다'}), 403

        # 집 이름 조회
        cur.execute(
            "SELECT name FROM houses WHERE id = %s",
            (house_id,)
        )
        house = cur.fetchone()
        house_name = house['name'] if house else ''

        # 히스토리 조회
        cur.execute(
            """
            SELECT
                cl.id,
                cl.container_id,
                cl.container_name,
                cl.container_type_cd,
                ct.nm as container_type_nm,
                cl.act_cd,
                cd.nm as act_nm,

                -- 위치 정보
                cl.from_container_id,
                fc.name as from_container_name,
                cl.to_container_id,
                tc.name as to_container_name,

                -- 집 정보
                cl.from_house_id,
                fh.name as from_house_name,
                cl.to_house_id,
                th.name as to_house_name,

                -- 소유자 정보
                cl.from_owner_user_id,
                fo.name as from_owner_name,
                cl.to_owner_user_id,
                tou.name as to_owner_name,

                -- 수량 정보
                cl.from_quantity,
                cl.to_quantity,

                -- 메모 정보
                cl.from_remk,
                cl.to_remk,

                -- 기타
                cl.log_remk,
                cl.created_at,
                cl.created_user,
                creator.name as creator_name

            FROM container_logs cl
            LEFT JOIN com_code_d cd ON cl.act_cd = cd.cd
            LEFT JOIN com_code_d ct ON cl.container_type_cd = ct.cd
            LEFT JOIN containers fc ON cl.from_container_id = fc.id
            LEFT JOIN containers tc ON cl.to_container_id = tc.id
            LEFT JOIN houses fh ON cl.from_house_id = fh.id
            LEFT JOIN houses th ON cl.to_house_id = th.id
            LEFT JOIN users fo ON cl.from_owner_user_id = fo.id
            LEFT JOIN users tou ON cl.to_owner_user_id = tou.id
            LEFT JOIN users creator ON cl.created_user = creator.id

            WHERE cl.from_house_id = %s OR cl.to_house_id = %s
            ORDER BY cl.created_at DESC
            LIMIT %s
            """,
            (house_id, house_id, limit)
        )

        logs = cur.fetchall()

        cur.close()
        conn.close()

        return jsonify({
            'logs': logs,
            'count': len(logs),
            'house_name': house_name
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500