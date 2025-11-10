from flask import Blueprint, request, jsonify
from psycopg2.extras import RealDictCursor
from database import get_db_connection
from middlewares.auth import token_required

containers_bp = Blueprint('containers', __name__, url_prefix='/api/houses')

# 1. 컨테이너 조회 (최상위 또는 특정 부모의 자식들)
@containers_bp.route('/<house_id>/containers', methods=['GET'])
@token_required
def get_containers(current_user_id, house_id):
    """
    Query Parameters:
    - level=root : 최상위 영역들 조회
    - parent_id={container_id} : 특정 컨테이너의 자식들 조회
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        member = cur.fetchone()
        
        if not member:
            cur.close()
            conn.close()
            return jsonify({'error': '접근 권한이 없습니다'}), 403
        
        # 쿼리 파라미터
        level = request.args.get('level')
        parent_id = request.args.get('parent_id')
        
        if level == 'root':
            # 최상위 영역들 조회 (상세 정보 포함)
            cur.execute(
                """
                SELECT 
                    c.id,
                    c.name,
                    c.house_id,
                    c.up_container_id,
                    c.type_cd,
                    cd.nm as type_nm,
                    c.quantity,
                    c.remk,
                    c.owner_user_id,
                    u.name as owner_name,
                    c.created_at,
                    c.created_user,
                    creator.name as creator_name,
                    (SELECT COUNT(*) 
                     FROM containers 
                     WHERE up_container_id = c.id 
                     AND house_id = %s) as child_count
                FROM containers c
                LEFT JOIN com_code_d cd ON c.type_cd = cd.cd
                LEFT JOIN users u ON c.owner_user_id = u.id
                LEFT JOIN users creator ON c.created_user = creator.id
                WHERE c.house_id = %s 
                  AND c.up_container_id IS NULL
                ORDER BY c.type_cd, c.name
                """,
                (house_id, house_id)
            )
        elif parent_id:
            # 특정 부모의 자식들 조회 (상세 정보 포함)
            cur.execute(
                """
                SELECT 
                    c.id,
                    c.name,
                    c.house_id,
                    c.up_container_id,
                    c.type_cd,
                    cd.nm as type_nm,
                    c.quantity,
                    c.remk,
                    c.owner_user_id,
                    u.name as owner_name,
                    c.created_at,
                    c.created_user,
                    creator.name as creator_name,
                    (SELECT COUNT(*) 
                     FROM containers 
                     WHERE up_container_id = c.id 
                     AND house_id = %s) as child_count
                FROM containers c
                LEFT JOIN com_code_d cd ON c.type_cd = cd.cd
                LEFT JOIN users u ON c.owner_user_id = u.id
                LEFT JOIN users creator ON c.created_user = creator.id
                WHERE c.house_id = %s 
                  AND c.up_container_id = %s
                ORDER BY c.type_cd, c.name
                """,
                (house_id, house_id, parent_id)
            )
        else:
            cur.close()
            conn.close()
            return jsonify({'error': 'level 또는 parent_id 파라미터가 필요합니다'}), 400
        
        containers = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'containers': containers,
            'my_role': member['role_cd']
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 2. 컨테이너 상세 조회
@containers_bp.route('/<house_id>/containers/<container_id>', methods=['GET'])
@token_required
def get_container_detail(current_user_id, house_id, container_id):
    """
    특정 컨테이너의 상세 정보 조회
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '접근 권한이 없습니다'}), 403
        
        # 컨테이너 상세 조회
        cur.execute(
            """
            SELECT 
                c.id,
                c.name,
                c.house_id,
                c.up_container_id,
                c.type_cd,
                cd.nm as type_nm,
                c.quantity,
                c.remk,
                c.owner_user_id,
                u.name as owner_name,
                c.created_at,
                c.created_user,
                creator.name as creator_name,
                (SELECT COUNT(*) 
                 FROM containers 
                 WHERE up_container_id = c.id 
                 AND house_id = %s) as child_count
            FROM containers c
            LEFT JOIN com_code_d cd ON c.type_cd = cd.cd
            LEFT JOIN users u ON c.owner_user_id = u.id
            LEFT JOIN users creator ON c.created_user = creator.id
            WHERE c.house_id = %s 
              AND c.id = %s
            """,
            (house_id, house_id, container_id)
        )
        container = cur.fetchone()
        
        if not container:
            cur.close()
            conn.close()
            return jsonify({'error': '컨테이너를 찾을 수 없습니다'}), 404
        
        # 부모 경로 조회 (브레드크럼용)
        cur.execute(
            """
            WITH RECURSIVE parent_path AS (
                SELECT id, name, up_container_id, 1 as depth
                FROM containers
                WHERE id = %s AND house_id = %s
                
                UNION ALL
                
                SELECT c.id, c.name, c.up_container_id, pp.depth + 1
                FROM containers c
                JOIN parent_path pp ON c.id = pp.up_container_id
                WHERE c.house_id = %s
            )
            SELECT id, name FROM parent_path
            ORDER BY depth DESC
            """,
            (container_id, house_id, house_id)
        )
        path = cur.fetchall()
        
        # 하위 항목 미리보기 (영역/박스만, 최대 3개)
        child_preview = []
        if container['type_cd'] in ['COM1200001', 'COM1200002']:  # 영역 또는 박스
            cur.execute(
                """
                SELECT 
                    c.id,
                    c.name,
                    c.type_cd,
                    cd.nm as type_nm,
                    c.quantity,
                    c.owner_user_id,
                    u.name as owner_name
                FROM containers c
                LEFT JOIN com_code_d cd ON c.type_cd = cd.cd
                LEFT JOIN users u ON c.owner_user_id = u.id
                WHERE c.up_container_id = %s 
                  AND c.house_id = %s
                ORDER BY c.type_cd, c.name
                LIMIT 3
                """,
                (container_id, house_id)
            )
            child_preview = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'container': container,
            'path': path,
            'child_preview': child_preview
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 3. 컨테이너 생성
@containers_bp.route('/<house_id>/containers', methods=['POST'])
@token_required
def create_container(current_user_id, house_id):
    """
    Request Body:
    {
        "parent_id": "C202500001" (optional, null이면 최상위),
        "type_cd": "COM1200001" (영역/박스/물품),
        "name": "거실",
        "quantity": 1 (물품일 때만),
        "owner_user_id": "0000000001" (물품일 때만, optional),
        "remk": "메모" (물품일 때만, optional)
    }
    """
    try:
        data = request.json
        parent_id = data.get('parent_id')
        type_cd = data.get('type_cd')
        name = data.get('name')
        quantity = data.get('quantity')
        owner_user_id = data.get('owner_user_id')
        remk = data.get('remk')
        
        # 유효성 검사
        if not type_cd or not name:
            return jsonify({'error': 'type_cd와 name은 필수입니다'}), 400
        
        # 물품일 때 수량 체크
        if type_cd == 'COM1200003':
            if quantity is None:
                quantity = 1
            if quantity < 0:
                return jsonify({'error': '수량은 0 이상이어야 합니다'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '접근 권한이 없습니다'}), 403
        
        # 부모 확인 (parent_id가 있는 경우)
        if parent_id:
            cur.execute(
                "SELECT id FROM containers WHERE id = %s AND house_id = %s",
                (parent_id, house_id)
            )
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({'error': '부모 컨테이너를 찾을 수 없습니다'}), 404
        
        # 컨테이너 생성
        cur.execute(
            """
            INSERT INTO containers 
            (house_id, up_container_id, type_cd, name, quantity, owner_user_id, remk, created_user, updated_user)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, name, type_cd, created_at
            """,
            (house_id, parent_id, type_cd, name, quantity, owner_user_id, remk, current_user_id, current_user_id)
        )
        container = cur.fetchone()
        
        # ============================================
        # container_logs 기록 추가 (생성)
        # ============================================
        log_remk = f"{name} 생성"
        
        cur.execute(
            """
            INSERT INTO container_logs 
            (container_id, act_cd, to_container_id, to_quantity, to_owner_user_id, 
             to_remk, log_remk, created_user, updated_user)
            VALUES (%s, 'COM1300001', %s, %s, %s, %s, %s, %s, %s)
            """,
            (container['id'], parent_id, quantity, owner_user_id, 
             remk, log_remk, current_user_id, current_user_id)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'message': '컨테이너가 생성되었습니다',
            'container': container
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500


# 4. 컨테이너 수정 (up_container_id 이동 기능 추가됨)
# 4. 컨테이너 수정 (이름, 위치, 수량, 메모, 소유자 등)
@containers_bp.route('/<house_id>/containers/<container_id>', methods=['PATCH'])
@token_required
def update_container(current_user_id, house_id, container_id):
    """
    컨테이너 정보 수정 (이름, up_container_id, 수량, 메모, 소유자)
    - 집 간 이동 기능 포함 (target_house_id)
    """
    conn = None
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '접근 권한이 없습니다'}), 403
        
        # 컨테이너 정보 조회
        cur.execute(
            """
            SELECT c.*, cd.nm as type_nm
            FROM containers c
            LEFT JOIN com_code_d cd ON c.type_cd = cd.cd
            WHERE c.id = %s AND c.house_id = %s
            """,
            (container_id, house_id)
        )
        container = cur.fetchone()
        
        if not container:
            cur.close()
            conn.close()
            return jsonify({'error': '컨테이너를 찾을 수 없습니다'}), 404
        
        # ============================================
        # 집 간 이동 처리
        # ============================================
        target_house_id = data.get('target_house_id')
        house_changed = False
        
        if target_house_id and target_house_id != house_id:
            # 대상 집의 멤버인지 확인
            cur.execute(
                "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
                (target_house_id, current_user_id)
            )
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({'error': '대상 집에 대한 권한이 없습니다'}), 403
            
            house_changed = True
        
        # 업데이트할 필드 구성
        update_fields = []
        params = []
        
        if 'name' in data:
            update_fields.append("name = %s")
            params.append(data['name'])
        
        # 집 변경
        if house_changed:
            update_fields.append("house_id = %s")
            params.append(target_house_id)
        
        # up_container_id 수정 (이동 기능)
        if 'up_container_id' in data:
            # 부모 컨테이너 유효성 검사
            new_parent_id = data['up_container_id']
            if new_parent_id is not None:
                # 검증할 house_id 결정 (집 간 이동이면 대상 집, 아니면 현재 집)
                check_house_id = target_house_id if house_changed else house_id
                cur.execute(
                    "SELECT id, type_cd FROM containers WHERE id = %s AND house_id = %s",
                    (new_parent_id, check_house_id)
                )
                parent = cur.fetchone()
                if not parent:
                    cur.close()
                    conn.close()
                    return jsonify({'error': '부모 컨테이너를 찾을 수 없습니다'}), 404
                # 물품은 물품 안에 들어갈 수 없음
                if parent['type_cd'] == 'COM1200003':
                    cur.close()
                    conn.close()
                    return jsonify({'error': '물품 안에는 다른 항목을 넣을 수 없습니다'}), 400
                # 자기 자신의 하위로 이동 불가 (순환 참조 방지)
                if new_parent_id == container_id:
                    cur.close()
                    conn.close()
                    return jsonify({'error': '자기 자신의 하위로 이동할 수 없습니다'}), 400
            
            update_fields.append("up_container_id = %s")
            params.append(new_parent_id)
        
        # 물품일 때만 추가 필드 수정 가능
        if container['type_cd'] == 'COM1200003':
            if 'quantity' in data:
                update_fields.append("quantity = %s")
                params.append(data['quantity'])
            
            if 'remk' in data:
                update_fields.append("remk = %s")
                params.append(data['remk'])
            
            if 'owner_user_id' in data:
                owner_id = data['owner_user_id']
                if owner_id:
                    cur.execute(
                        "SELECT id FROM house_members WHERE house_id = %s AND user_id = %s",
                        (house_id if not house_changed else target_house_id, owner_id)
                    )
                    if not cur.fetchone():
                        cur.close()
                        conn.close()
                        return jsonify({'error': '소유자는 해당 집의 멤버여야 합니다'}), 400
                
                update_fields.append("owner_user_id = %s")
                params.append(owner_id)
        
        # 수정할 필드가 없으면 에러
        if not update_fields:
            cur.close()
            conn.close()
            return jsonify({'error': '수정할 필드가 없습니다'}), 400
        
        # 수정 전 값 저장 (로그용)
        before_values = dict(container)
        
        # UPDATE 쿼리 실행
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        update_fields.append("updated_user = %s")
        params.append(current_user_id)
        params.append(container_id)
        
        update_query = f"""
            UPDATE containers 
            SET {', '.join(update_fields)}
            WHERE id = %s
            RETURNING *
        """
        
        cur.execute(update_query, params)
        updated = cur.fetchone()
        
        # ============================================
        # 하위 항목 일괄 처리 (집 변경 시)
        # ============================================
        child_count = 0
        if house_changed:
            cur.execute(
                """
                WITH RECURSIVE children AS (
                    SELECT id, house_id FROM containers WHERE up_container_id = %s
                    UNION ALL
                    SELECT c.id, c.house_id FROM containers c
                    INNER JOIN children ch ON c.up_container_id = ch.id
                )
                UPDATE containers
                SET house_id = %s, updated_at = CURRENT_TIMESTAMP, updated_user = %s
                WHERE id IN (SELECT id FROM children)
                RETURNING id
                """,
                (container_id, target_house_id, current_user_id)
            )
            child_updates = cur.fetchall()
            child_count = len(child_updates)
        
        # ============================================
        # 로그 기록
        # ============================================
        act_cd = None
        log_remk = None
        
        # 집 변경 로그
        if house_changed:
            act_cd = 'COM1300003'
            log_remk = f'하위 항목 {child_count}개 포함' if child_count > 0 else None
            
            cur.execute(
                """
                INSERT INTO container_logs (
                    container_id, act_cd,
                    from_house_id, to_house_id,
                    from_container_id, to_container_id,
                    from_owner_user_id, to_owner_user_id,
                    from_quantity, to_quantity,
                    from_remk, to_remk,
                    log_remk, created_user
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    container_id, act_cd,
                    before_values['house_id'], updated['house_id'],
                    before_values['up_container_id'], updated['up_container_id'],
                    before_values.get('owner_user_id'), updated.get('owner_user_id'),
                    before_values.get('quantity'), updated.get('quantity'),
                    before_values.get('remk'), updated.get('remk'),
                    log_remk, current_user_id
                )
            )
        
        # 위치 변경 로그 (같은 집 내)
        elif 'up_container_id' in data and before_values['up_container_id'] != updated['up_container_id']:
            act_cd = 'COM1300003'
            
            cur.execute(
                """
                INSERT INTO container_logs (
                    container_id, act_cd,
                    from_container_id, to_container_id,
                    from_owner_user_id, to_owner_user_id,
                    from_quantity, to_quantity,
                    from_remk, to_remk,
                    created_user
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    container_id, act_cd,
                    before_values['up_container_id'], updated['up_container_id'],
                    before_values.get('owner_user_id'), updated.get('owner_user_id'),
                    before_values.get('quantity'), updated.get('quantity'),
                    before_values.get('remk'), updated.get('remk'),
                    current_user_id
                )
            )
        
        # 기타 수정 로그
        elif any(field in data for field in ['name', 'quantity', 'remk', 'owner_user_id']):
            act_cd = 'COM1300004'
            changes = []
            if 'name' in data and before_values['name'] != updated['name']:
                changes.append(f"이름: {before_values['name']} → {updated['name']}")
            if 'quantity' in data and before_values.get('quantity') != updated.get('quantity'):
                changes.append(f"수량: {before_values.get('quantity')} → {updated.get('quantity')}")
            if 'owner_user_id' in data and before_values.get('owner_user_id') != updated.get('owner_user_id'):
                changes.append("소유자 변경")
            
            log_remk = ', '.join(changes) if changes else '정보 수정'
            
            cur.execute(
                """
                INSERT INTO container_logs (
                    container_id, act_cd,
                    from_container_id, to_container_id,
                    from_owner_user_id, to_owner_user_id,
                    from_quantity, to_quantity,
                    from_remk, to_remk,
                    log_remk, created_user
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    container_id, act_cd,
                    before_values['up_container_id'], updated['up_container_id'],
                    before_values.get('owner_user_id'), updated.get('owner_user_id'),
                    before_values.get('quantity'), updated.get('quantity'),
                    before_values.get('remk'), updated.get('remk'),
                    log_remk, current_user_id
                )
            )
        
        conn.commit()
        
        # 수정된 컨테이너 정보 다시 조회
        cur.execute(
            """
            SELECT c.*, cd.nm as type_nm, u.name as owner_name
            FROM containers c
            LEFT JOIN com_code_d cd ON c.type_cd = cd.cd
            LEFT JOIN users u ON c.owner_user_id = u.id
            WHERE c.id = %s
            """,
            (container_id,)
        )
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'message': '수정 성공' if not house_changed else '집 이동 성공',
            'container': result
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500

        return jsonify({
            'message': '컨테이너가 수정되었습니다',
            'container': updated
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500


# 5. 컨테이너 삭제
@containers_bp.route('/<house_id>/containers/<container_id>', methods=['DELETE'])
@token_required
def delete_container(current_user_id, house_id, container_id):
    """
    컨테이너 삭제 (하위 항목도 CASCADE 삭제됨)
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '접근 권한이 없습니다'}), 403
        
        # 컨테이너 존재 확인 및 상세 정보 조회
        cur.execute(
            """
            SELECT name, up_container_id, quantity, owner_user_id, remk
            FROM containers 
            WHERE id = %s AND house_id = %s
            """,
            (container_id, house_id)
        )
        container = cur.fetchone()
        
        if not container:
            cur.close()
            conn.close()
            return jsonify({'error': '컨테이너를 찾을 수 없습니다'}), 404
        
        # ============================================
        # container_logs 기록 추가 (반출) - 삭제 전에 기록
        # ============================================
        log_remk = f"삭제: {container['name']}"
        if container['up_container_id']:
            log_remk += f", 위치: {container['up_container_id']}"
        
        cur.execute(
            """
            INSERT INTO container_logs 
            (container_id, act_cd, from_container_id, from_quantity, from_owner_user_id,
             from_remk, log_remk, created_user, updated_user)
            VALUES (%s, 'COM1300002', %s, %s, %s, %s, %s, %s, %s)
            """,
            (container_id, container['up_container_id'], container.get('quantity'), 
             container.get('owner_user_id'), container.get('remk'), log_remk,
             current_user_id, current_user_id)
        )
        
        # 삭제
        cur.execute(
            "DELETE FROM containers WHERE id = %s AND house_id = %s",
            (container_id, house_id)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'message': f'"{container["name"]}"이(가) 삭제되었습니다'
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500


# 6. 컨테이너 검색
@containers_bp.route('/<house_id>/containers/search', methods=['GET'])
@token_required
def search_containers(current_user_id, house_id):
    """
    Query Parameters:
    - q: 검색어 (필수)
    - type: 타입 필터 (optional: area, box, item)
    """
    try:
        query = request.args.get('q', '').strip()
        type_filter = request.args.get('type')
        
        if not query:
            return jsonify({'error': '검색어를 입력해주세요'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '접근 권한이 없습니다'}), 403
        
        # 검색 쿼리 구성 - ARRAY 타입 명시적 캐스팅
        sql = """
            WITH RECURSIVE parent_path AS (
                SELECT id, name, up_container_id, ARRAY[name::text] as path
                FROM containers
                WHERE house_id = %s AND up_container_id IS NULL
                
                UNION ALL
                
                SELECT c.id, c.name, c.up_container_id, pp.path || c.name::text
                FROM containers c
                JOIN parent_path pp ON c.up_container_id = pp.id
                WHERE c.house_id = %s
            )
            SELECT 
                c.id,
                c.name,
                c.type_cd,
                cd.nm as type_nm,
                c.quantity,
                c.owner_user_id,
                u.name as owner_name,
                array_to_string(pp.path, ' > ') as path
            FROM containers c
            LEFT JOIN com_code_d cd ON c.type_cd = cd.cd
            LEFT JOIN users u ON c.owner_user_id = u.id
            LEFT JOIN parent_path pp ON c.id = pp.id
            WHERE c.house_id = %s 
              AND c.name ILIKE %s
        """
        
        params = [house_id, house_id, house_id, f'%{query}%']
        
        # 타입 필터
        if type_filter:
            type_map = {
                'area': 'COM1200001',
                'box': 'COM1200002',
                'item': 'COM1200003'
            }
            if type_filter in type_map:
                sql += " AND c.type_cd = %s"
                params.append(type_map[type_filter])
        
        sql += " ORDER BY c.type_cd, c.name LIMIT 50"
        
        cur.execute(sql, params)
        results = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'results': results,
            'count': len(results)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 7. 컨테이너 히스토리 조회
@containers_bp.route('/<house_id>/containers/<container_id>/logs', methods=['GET'])
@token_required
def get_container_logs(current_user_id, house_id, container_id):
    """
    특정 컨테이너의 변경 이력 조회
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 권한 확인
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '접근 권한이 없습니다'}), 403
        
        # 컨테이너 존재 확인
        cur.execute(
            "SELECT id FROM containers WHERE id = %s AND house_id = %s",
            (container_id, house_id)
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '컨테이너를 찾을 수 없습니다'}), 404
        
        # 히스토리 조회 (상세 정보 포함)
        cur.execute(
            """
            SELECT 
                cl.id,
                cl.container_id,
                cl.act_cd,
                cd.nm as act_nm,
                
                -- 현재 컨테이너가 속한 집 정보
                c.house_id as current_house_id,
                ch.name as current_house_name,
                
                -- 집 간 이동 정보
                cl.from_house_id,
                fh.name as from_house_name,
                cl.to_house_id,
                th.name as to_house_name,
                
                -- 위치 정보
                cl.from_container_id,
                fc.name as from_container_name,
                cl.to_container_id,
                tc.name as to_container_name,
                
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
                TO_CHAR(cl.created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at,
                cl.created_user,
                creator.name as creator_name
                
            FROM container_logs cl
            LEFT JOIN containers c ON cl.container_id = c.id
            LEFT JOIN houses ch ON c.house_id = ch.id
            LEFT JOIN houses fh ON cl.from_house_id = fh.id
            LEFT JOIN houses th ON cl.to_house_id = th.id
            LEFT JOIN com_code_d cd ON cl.act_cd = cd.cd
            LEFT JOIN containers fc ON cl.from_container_id = fc.id
            LEFT JOIN containers tc ON cl.to_container_id = tc.id
            LEFT JOIN users fo ON cl.from_owner_user_id = fo.id
            LEFT JOIN users tou ON cl.to_owner_user_id = tou.id
            LEFT JOIN users creator ON cl.created_user = creator.id
            
            WHERE cl.container_id = %s
            ORDER BY cl.created_at DESC
            """,
            (container_id,)
        )
        
        logs = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'logs': logs,
            'count': len(logs)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500