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
@containers_bp.route('/<house_id>/containers/<container_id>', methods=['PATCH'])
@token_required
def update_container(current_user_id, house_id, container_id):
    """
    Request Body:
    {
        "name": "새 이름" (optional),
        "up_container_id": "C202500002" (optional, 다른 위치로 이동),
        "quantity": 2 (물품일 때만, optional),
        "owner_user_id": "0000000001" (물품일 때만, optional),
        "remk": "메모" (물품일 때만, optional)
    }
    """
    try:
        data = request.json
        
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
            "SELECT type_cd FROM containers WHERE id = %s AND house_id = %s",
            (container_id, house_id)
        )
        container = cur.fetchone()
        
        if not container:
            cur.close()
            conn.close()
            return jsonify({'error': '컨테이너를 찾을 수 없습니다'}), 404
        
        # 업데이트할 필드 구성
        update_fields = []
        params = []
        
        if 'name' in data:
            update_fields.append("name = %s")
            params.append(data['name'])
        
        # up_container_id 수정 (이동 기능) - 새로 추가된 부분
        if 'up_container_id' in data:
            # 부모 컨테이너 유효성 검사
            new_parent_id = data['up_container_id']
            if new_parent_id is not None:
                cur.execute(
                    "SELECT id, type_cd FROM containers WHERE id = %s AND house_id = %s",
                    (new_parent_id, house_id)
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
                if data['quantity'] < 0:
                    cur.close()
                    conn.close()
                    return jsonify({'error': '수량은 0 이상이어야 합니다'}), 400
                update_fields.append("quantity = %s")
                params.append(data['quantity'])
            
            if 'owner_user_id' in data:
                update_fields.append("owner_user_id = %s")
                params.append(data['owner_user_id'])
            
            if 'remk' in data:
                update_fields.append("remk = %s")
                params.append(data['remk'])
        
        if not update_fields:
            cur.close()
            conn.close()
            return jsonify({'error': '수정할 내용이 없습니다'}), 400
        
        # ============================================
        # 원본 데이터 조회 (로그용) - UPDATE 전에 조회!
        # ============================================
        cur.execute(
            """
            SELECT name, up_container_id, quantity, owner_user_id, remk
            FROM containers
            WHERE id = %s AND house_id = %s
            """,
            (container_id, house_id)
        )
        original = cur.fetchone()
        
        # updated_user 추가
        update_fields.append("updated_user = %s")
        params.append(current_user_id)
        
        # 쿼리 실행
        params.extend([container_id, house_id])
        query = f"""
            UPDATE containers 
            SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND house_id = %s
            RETURNING id, name, updated_at
        """
        
        cur.execute(query, params)
        updated = cur.fetchone()
        
        # ============================================
        # container_logs 기록 추가
        # ============================================
        
        # 변경 내용 체크
        location_changed = 'up_container_id' in data and data['up_container_id'] != original.get('up_container_id')
        name_changed = 'name' in data and data['name'] != original.get('name')
        quantity_changed = 'quantity' in data and data['quantity'] != original.get('quantity')
        owner_changed = 'owner_user_id' in data and data['owner_user_id'] != original.get('owner_user_id')
        remk_changed = 'remk' in data and data['remk'] != original.get('remk')
        
        # 1. 위치 이동만 변경된 경우 - 이동 로그
        if location_changed and not (name_changed or quantity_changed or owner_changed or remk_changed):
            cur.execute(
                """
                INSERT INTO container_logs
                (container_id, act_cd, from_container_id, to_container_id,
                 from_house_id, to_house_id, created_user, updated_user)
                VALUES (%s, 'COM1300003', %s, %s, %s, %s, %s, %s)
                """,
                (container_id, original.get('up_container_id'), data['up_container_id'],
                 house_id, house_id, current_user_id, current_user_id)
            )
        
        # 2. 위치 이동 외 변경사항이 있으면 - 통합 수정 로그
        elif name_changed or quantity_changed or owner_changed or remk_changed or location_changed:
            log_parts = []
            
            # 위치 변경
            if location_changed:
                log_parts.append(f"위치 이동")
            
            # 이름 변경
            if name_changed:
                log_parts.append(f"이름 변경: {original.get('name', '')} → {data['name']}")
            
            # 수량 변경
            if quantity_changed:
                log_parts.append(f"수량 변경: {original.get('quantity', 0)}개 → {data['quantity']}개")
            
            # 소유자 변경
            if owner_changed:
                # 소유자 이름 조회
                from_owner_name = None
                to_owner_name = None
                
                if original.get('owner_user_id'):
                    cur.execute("SELECT name FROM users WHERE id = %s", (original['owner_user_id'],))
                    from_owner = cur.fetchone()
                    from_owner_name = from_owner['name'] if from_owner else None
                
                if data.get('owner_user_id'):
                    cur.execute("SELECT name FROM users WHERE id = %s", (data['owner_user_id'],))
                    to_owner = cur.fetchone()
                    to_owner_name = to_owner['name'] if to_owner else None
                
                from_text = from_owner_name or '없음'
                to_text = to_owner_name or '없음'
                log_parts.append(f"소유자 변경: {from_text} → {to_text}")
            
            # 메모 변경
            if remk_changed:
                from_remk = original.get('remk') or '없음'
                to_remk = data.get('remk') or '없음'
                log_parts.append(f"메모 변경: {from_remk} → {to_remk}")
            
            # 통합 수정 로그 생성
            cur.execute(
                """
                INSERT INTO container_logs
                (container_id, act_cd, from_container_id, to_container_id,
                 from_house_id, to_house_id,
                 from_quantity, to_quantity, from_owner_user_id, to_owner_user_id,
                 from_remk, to_remk, log_remk, created_user, updated_user)
                VALUES (%s, 'COM1300004', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (container_id,
                 original.get('up_container_id') if location_changed else None,
                 data.get('up_container_id') if location_changed else None,
                 house_id if location_changed else None,
                 house_id if location_changed else None,
                 original.get('quantity') if quantity_changed else None,
                 data.get('quantity') if quantity_changed else None,
                 original.get('owner_user_id') if owner_changed else None,
                 data.get('owner_user_id') if owner_changed else None,
                 original.get('remk') if remk_changed else None,
                 data.get('remk') if remk_changed else None,
                 '\n'.join(log_parts),
                 current_user_id, current_user_id)
            )
        
        conn.commit()
        cur.close()
        conn.close()
        
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
        
        # 현재 컨테이너가 속한 집 이름 조회
        cur.execute(
            """
            SELECT h.name
            FROM houses h
            WHERE h.id = %s
            """,
            (house_id,)
        )
        house_result = cur.fetchone()
        current_house_name = house_result['name'] if house_result else ''

        # 히스토리 조회 (상세 정보 포함)
        cur.execute(
            """
            SELECT
                cl.id,
                cl.container_id,
                cl.act_cd,
                cd.nm as act_nm,

                -- 위치 정보
                cl.from_container_id,
                fc.name as from_container_name,
                cl.to_container_id,
                tc.name as to_container_name,

                -- 집 간 이동 정보
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
                TO_CHAR(cl.created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at,
                cl.created_user,
                creator.name as creator_name

            FROM container_logs cl
            LEFT JOIN com_code_d cd ON cl.act_cd = cd.cd
            LEFT JOIN containers fc ON cl.from_container_id = fc.id
            LEFT JOIN containers tc ON cl.to_container_id = tc.id
            LEFT JOIN houses fh ON cl.from_house_id = fh.id
            LEFT JOIN houses th ON cl.to_house_id = th.id
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
            'count': len(logs),
            'current_house_name': current_house_name
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# 9. 집 간 컨테이너 이동 (새 API)
@containers_bp.route('/<house_id>/containers/<container_id>/move', methods=['PATCH'])
@token_required
def move_container_cross_house(current_user_id, house_id, container_id):
    """
    집 간 컨테이너 이동 (house_id 변경 가능)
    
    Request Body:
    {
        "parent_id": "C202500002" (optional, null이면 최상위로 이동),
        "to_house_id": "H202400002" (optional, 다른 집으로 이동)
    }
    """
    try:
        data = request.json
        parent_id = data.get('parent_id')
        to_house_id = data.get('to_house_id', house_id)  # 기본값은 같은 집
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 출발지 집 권한 확인
        cur.execute(
            "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
            (house_id, current_user_id)
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': '출발지 집에 대한 권한이 없습니다'}), 403
        
        # 목적지 집 권한 확인 (다른 집으로 이동하는 경우)
        if to_house_id != house_id:
            cur.execute(
                "SELECT role_cd FROM house_members WHERE house_id = %s AND user_id = %s",
                (to_house_id, current_user_id)
            )
            if not cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({'error': '목적지 집에 대한 권한이 없습니다'}), 403
        
        # 컨테이너 존재 확인 및 원본 데이터 조회
        cur.execute(
            """
            SELECT c.id, c.house_id, c.up_container_id, c.type_cd, c.name,
                   c.quantity, c.owner_user_id, c.remk
            FROM containers c
            WHERE c.id = %s AND c.house_id = %s
            """,
            (container_id, house_id)
        )
        container = cur.fetchone()
        
        if not container:
            cur.close()
            conn.close()
            return jsonify({'error': '컨테이너를 찾을 수 없습니다'}), 404
        
        # 목적지 부모 컨테이너 유효성 검사
        if parent_id is not None:
            cur.execute(
                "SELECT id, type_cd FROM containers WHERE id = %s AND house_id = %s",
                (parent_id, to_house_id)
            )
            parent = cur.fetchone()
            if not parent:
                cur.close()
                conn.close()
                return jsonify({'error': '목적지 부모 컨테이너를 찾을 수 없습니다'}), 404
            
            # 물품은 물품 안에 들어갈 수 없음
            if parent['type_cd'] == 'COM1200003':
                cur.close()
                conn.close()
                return jsonify({'error': '물품 안에는 다른 항목을 넣을 수 없습니다'}), 400
        
        # 컨테이너 업데이트 (house_id와 up_container_id 변경)
        cur.execute(
            """
            UPDATE containers
            SET house_id = %s,
                up_container_id = %s,
                updated_at = CURRENT_TIMESTAMP,
                updated_user = %s
            WHERE id = %s
            """,
            (to_house_id, parent_id, current_user_id, container_id)
        )
        
        # 하위 컨테이너들도 재귀적으로 house_id 업데이트 (중요!)
        if to_house_id != house_id:
            cur.execute(
                """
                WITH RECURSIVE descendants AS (
                    SELECT id FROM containers WHERE up_container_id = %s
                    UNION ALL
                    SELECT c.id FROM containers c
                    INNER JOIN descendants d ON c.up_container_id = d.id
                )
                UPDATE containers
                SET house_id = %s,
                    updated_at = CURRENT_TIMESTAMP,
                    updated_user = %s
                WHERE id IN (SELECT id FROM descendants)
                """,
                (container_id, to_house_id, current_user_id)
            )
        
        # 로그 기록
        cur.execute(
            """
            INSERT INTO container_logs (
                container_id,
                act_cd,
                from_container_id,
                to_container_id,
                from_house_id,
                to_house_id,
                log_remk,
                created_user,
                updated_user
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                container_id,
                'COM1300003',  # 이동 (수정: COM1300002 -> COM1300003)
                container['up_container_id'],
                parent_id,
                house_id,
                to_house_id,
                f"{'같은 집 내' if house_id == to_house_id else '집 간'} 이동",
                current_user_id,
                current_user_id  # updated_user 추가!
            )
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'message': '이동이 완료되었습니다',
            'container_id': container_id,
            'from_house_id': house_id,
            'to_house_id': to_house_id
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500