from flask import Blueprint, request, jsonify
from psycopg2.extras import RealDictCursor
from database import get_db_connection
from middlewares.auth import token_required

invitations_bp = Blueprint('invitations', __name__, url_prefix='/api')

# 1. 초대 보내기
@invitations_bp.route('/houses/<house_id>/invitations', methods=['POST'])
@token_required
def send_invitation(current_user_id, house_id):
    try:
        data = request.json
        invitee_email = data.get('invitee_email')
        
        if not invitee_email:
            return jsonify({'error': '초대할 사용자의 이메일을 입력해주세요'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. 초대 보낸 사람이 해당 집의 멤버인지 확인
        cur.execute(
            "SELECT user_id FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '해당 집의 멤버만 초대할 수 있습니다'}), 403
        
        # 2. 이메일로 사용자 조회
        cur.execute("SELECT id, name, email FROM users WHERE email = %s", (invitee_email,))
        invitee = cur.fetchone()
        if not invitee:
            cur.close()
            conn.close()
            return jsonify({'error': '가입되지 않은 이메일입니다'}), 404
        
        invitee_user_id = invitee['id']
        
        # 3. 자기 자신 초대 방지
        if invitee_user_id == current_user_id:
            cur.close()
            conn.close()
            return jsonify({'error': '자기 자신을 초대할 수 없습니다'}), 400
        
        # 4. 이미 멤버인지 확인
        cur.execute(
            "SELECT user_id FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, invitee_user_id)
        )
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '이미 해당 집의 멤버입니다'}), 409
        
        # 5. 대기중인 초대가 있는지 확인
        cur.execute(
            """
            SELECT id FROM house_invitations 
            WHERE house_id = %s AND invitee_user_id = %s AND status_cd = 'COM1400001'
            """,
            (house_id, invitee_user_id)
        )
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '이미 대기중인 초대가 있습니다'}), 409
        
        # 6. 초대 생성
        cur.execute(
            """
            INSERT INTO house_invitations 
            (house_id, inviter_user_id, invitee_user_id, status_cd, created_user, updated_user)
            VALUES (%s, %s, %s, 'COM1400001', %s, %s)
            RETURNING id, created_at
            """,
            (house_id, current_user_id, invitee_user_id, current_user_id, current_user_id)
        )
        invitation = cur.fetchone()
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'message': '초대를 보냈습니다',
            'invitation': {
                'id': invitation['id'],
                'invitee_name': invitee['name'],
                'invitee_email': invitee['email'],
                'created_at': invitation['created_at'].isoformat()
            }
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500

# 2. 받은 초대 목록 조회
@invitations_bp.route('/invitations/received', methods=['GET'])
@token_required
def get_received_invitations(current_user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute(
            """
            SELECT 
                hi.id,
                hi.house_id,
                h.name as house_name,
                hi.inviter_user_id,
                u.name as inviter_name,
                hi.status_cd,
                cd.nm as status_nm,
                hi.created_at
            FROM house_invitations hi
                JOIN houses h ON hi.house_id = h.id
                JOIN users u ON hi.inviter_user_id = u.id
                LEFT JOIN com_code_d cd ON hi.status_cd = cd.cd
            WHERE hi.invitee_user_id = %s AND hi.status_cd = 'COM1400001'
            ORDER BY hi.created_at DESC
            """,
            (current_user_id,)
        )
        invitations = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'invitations': invitations}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 2-1. 보낸 초대 목록 조회 (최근 7일)
@invitations_bp.route('/invitations/sent', methods=['GET'])
@token_required
def get_sent_invitations(current_user_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute(
            """
            SELECT 
                hi.id,
                hi.house_id,
                h.name as house_name,
                hi.invitee_user_id,
                u.name as invitee_name,
                u.email as invitee_email,
                hi.status_cd,
                cd.nm as status_nm,
                hi.created_at,
                hi.responded_at
            FROM house_invitations hi
                JOIN houses h ON hi.house_id = h.id
                JOIN users u ON hi.invitee_user_id = u.id
                LEFT JOIN com_code_d cd ON hi.status_cd = cd.cd
            WHERE hi.inviter_user_id = %s 
                AND hi.created_at >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY hi.created_at DESC
            """,
            (current_user_id,)
        )
        invitations = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'invitations': invitations}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 3. 초대 수락
@invitations_bp.route('/invitations/<invitation_id>/accept', methods=['PATCH'])
@token_required
def accept_invitation(current_user_id, invitation_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 초대 정보 조회
        cur.execute(
            """
            SELECT house_id, inviter_user_id, invitee_user_id, status_cd
            FROM house_invitations
            WHERE id = %s
            """,
            (invitation_id,)
        )
        invitation = cur.fetchone()
        
        if not invitation:
            cur.close()
            conn.close()
            return jsonify({'error': '존재하지 않는 초대입니다'}), 404
        
        # 초대받은 사람이 본인인지 확인
        if invitation['invitee_user_id'] != current_user_id:
            cur.close()
            conn.close()
            return jsonify({'error': '본인의 초대만 수락할 수 있습니다'}), 403
        
        # 대기중 상태인지 확인
        if invitation['status_cd'] != 'COM1400001':
            cur.close()
            conn.close()
            return jsonify({'error': '대기중인 초대만 수락할 수 있습니다'}), 400
        
        # house_members에 추가 (멤버 권한)
        cur.execute(
            """
            INSERT INTO house_members (house_id, user_id, role_cd, created_user, updated_user)
            VALUES (%s, %s, 'COM1100002', %s, %s)
            """,
            (invitation['house_id'], current_user_id, current_user_id, current_user_id)
        )
        
        # 초대 상태 업데이트
        cur.execute(
            """
            UPDATE house_invitations
            SET status_cd = 'COM1400002', 
                responded_at = CURRENT_TIMESTAMP,
                updated_user = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (current_user_id, invitation_id)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': '초대를 수락했습니다'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500

# 4. 초대 거절
@invitations_bp.route('/invitations/<invitation_id>/reject', methods=['PATCH'])
@token_required
def reject_invitation(current_user_id, invitation_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 초대 정보 조회
        cur.execute(
            """
            SELECT invitee_user_id, status_cd
            FROM house_invitations
            WHERE id = %s
            """,
            (invitation_id,)
        )
        invitation = cur.fetchone()
        
        if not invitation:
            cur.close()
            conn.close()
            return jsonify({'error': '존재하지 않는 초대입니다'}), 404
        
        # 초대받은 사람이 본인인지 확인
        if invitation['invitee_user_id'] != current_user_id:
            cur.close()
            conn.close()
            return jsonify({'error': '본인의 초대만 거절할 수 있습니다'}), 403
        
        # 대기중 상태인지 확인
        if invitation['status_cd'] != 'COM1400001':
            cur.close()
            conn.close()
            return jsonify({'error': '대기중인 초대만 거절할 수 있습니다'}), 400
        
        # 초대 상태 업데이트
        cur.execute(
            """
            UPDATE house_invitations
            SET status_cd = 'COM1400003', 
                responded_at = CURRENT_TIMESTAMP,
                updated_user = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (current_user_id, invitation_id)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': '초대를 거절했습니다'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500

# 5. 초대 취소 (초대 보낸 사람만 가능)
@invitations_bp.route('/invitations/<invitation_id>/cancel', methods=['PATCH'])
@token_required
def cancel_invitation(current_user_id, invitation_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 초대 정보 조회
        cur.execute(
            """
            SELECT inviter_user_id, status_cd
            FROM house_invitations
            WHERE id = %s
            """,
            (invitation_id,)
        )
        invitation = cur.fetchone()
        
        if not invitation:
            cur.close()
            conn.close()
            return jsonify({'error': '존재하지 않는 초대입니다'}), 404
        
        # 초대 보낸 사람이 본인인지 확인
        if invitation['inviter_user_id'] != current_user_id:
            cur.close()
            conn.close()
            return jsonify({'error': '초대를 보낸 사람만 취소할 수 있습니다'}), 403
        
        # 대기중 상태인지 확인
        if invitation['status_cd'] != 'COM1400001':
            cur.close()
            conn.close()
            return jsonify({'error': '대기중인 초대만 취소할 수 있습니다'}), 400
        
        # 초대 상태 업데이트
        cur.execute(
            """
            UPDATE house_invitations
            SET status_cd = 'COM1400004', 
                responded_at = CURRENT_TIMESTAMP,
                updated_user = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (current_user_id, invitation_id)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': '초대를 취소했습니다'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500