-- ============================================
-- ShareItem 데이터베이스 전체 초기화 스크립트
-- ============================================
-- 주요 변경사항:
-- 1. items 테이블 제거 → containers로 통합
-- 2. item_logs → container_logs로 변경
-- 3. users 테이블에 account_status 추가
-- 4. 초기 관리자 계정 생성 (0000000000)
-- ============================================

-- ============================================
-- 기존 테이블 및 관련 객체 삭제
-- ============================================

-- 기존 데이터 완전 삭제를 위한 트리거/함수/시퀀스 먼저 제거
DROP TRIGGER IF EXISTS set_container_log_id ON container_logs CASCADE;
DROP TRIGGER IF EXISTS set_container_id ON containers CASCADE;
DROP TRIGGER IF EXISTS set_item_log_id ON item_logs CASCADE;
DROP TRIGGER IF EXISTS set_item_id ON items CASCADE;
DROP TRIGGER IF EXISTS set_invitation_id ON house_invitations CASCADE;
DROP TRIGGER IF EXISTS set_house_member_seq ON house_members CASCADE;
DROP TRIGGER IF EXISTS set_house_id ON houses CASCADE;
DROP TRIGGER IF EXISTS set_updated_at ON users CASCADE;
DROP TRIGGER IF EXISTS set_user_id ON users CASCADE;

DROP FUNCTION IF EXISTS generate_container_log_id() CASCADE;
DROP FUNCTION IF EXISTS generate_container_id() CASCADE;
DROP FUNCTION IF EXISTS generate_item_log_id() CASCADE;
DROP FUNCTION IF EXISTS generate_item_id() CASCADE;
DROP FUNCTION IF EXISTS generate_invitation_id() CASCADE;
DROP FUNCTION IF EXISTS generate_house_member_seq() CASCADE;
DROP FUNCTION IF EXISTS generate_house_id() CASCADE;
DROP FUNCTION IF EXISTS update_updated_at() CASCADE;
DROP FUNCTION IF EXISTS generate_user_id() CASCADE;

DROP SEQUENCE IF EXISTS container_logs_id_seq CASCADE;
DROP SEQUENCE IF EXISTS containers_id_seq CASCADE;
DROP SEQUENCE IF EXISTS item_logs_id_seq CASCADE;
DROP SEQUENCE IF EXISTS items_id_seq CASCADE;
DROP SEQUENCE IF EXISTS invitations_id_seq CASCADE;
DROP SEQUENCE IF EXISTS houses_id_seq CASCADE;
DROP SEQUENCE IF EXISTS users_id_seq CASCADE;

-- 테이블 삭제 (의존성 역순으로)
DROP TABLE IF EXISTS container_logs CASCADE;
DROP TABLE IF EXISTS item_logs CASCADE;
DROP TABLE IF EXISTS items CASCADE;
DROP TABLE IF EXISTS containers CASCADE;
DROP TABLE IF EXISTS house_invitations CASCADE;
DROP TABLE IF EXISTS house_members CASCADE;
DROP TABLE IF EXISTS houses CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS com_code_d CASCADE;
DROP TABLE IF EXISTS com_code_m CASCADE;

-- ============================================
-- 공통코드 마스터 (FK 없이 먼저 생성)
-- ============================================
CREATE TABLE com_code_m (
    cd VARCHAR(20) PRIMARY KEY,
    nm VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_user VARCHAR(10),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_user VARCHAR(10)
);

-- ============================================
-- 공통코드 상세 (users FK 없이 먼저 생성)
-- ============================================
CREATE TABLE com_code_d (
    cd VARCHAR(20) PRIMARY KEY,
    nm VARCHAR(100) NOT NULL,
    up_cd VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_user VARCHAR(10),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_user VARCHAR(10),
    
    FOREIGN KEY (up_cd) REFERENCES com_code_m(cd) ON DELETE CASCADE
);

-- ============================================
-- 사용자
-- ============================================
CREATE TABLE users (
    id VARCHAR(10) PRIMARY KEY,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    account_status VARCHAR(20) NOT NULL DEFAULT 'COM1500001',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (account_status) REFERENCES com_code_d(cd) ON DELETE RESTRICT
);

CREATE SEQUENCE users_id_seq START 1;

CREATE OR REPLACE FUNCTION generate_user_id()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.id IS NULL OR NEW.id = '' THEN
        NEW.id := LPAD(nextval('users_id_seq')::TEXT, 10, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_user_id
    BEFORE INSERT ON users
    FOR EACH ROW
    EXECUTE FUNCTION generate_user_id();

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================
-- 집
-- ============================================
CREATE TABLE houses (
    id VARCHAR(11) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_user VARCHAR(10) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_user VARCHAR(10) NOT NULL,
    
    FOREIGN KEY (created_user) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (updated_user) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE SEQUENCE houses_id_seq START 1;

CREATE OR REPLACE FUNCTION generate_house_id()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.id IS NULL OR NEW.id = '' THEN
        NEW.id := 'H' || TO_CHAR(CURRENT_DATE, 'YYYY') || LPAD(nextval('houses_id_seq')::TEXT, 5, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_house_id
    BEFORE INSERT ON houses
    FOR EACH ROW
    EXECUTE FUNCTION generate_house_id();

-- ============================================
-- 집 구성원
-- ============================================
CREATE TABLE house_members (
    house_id VARCHAR(11) NOT NULL,
    user_id VARCHAR(10) NOT NULL,
    seq INT NOT NULL,
    role_cd VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_user VARCHAR(10) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_user VARCHAR(10) NOT NULL,
    
    PRIMARY KEY (house_id, user_id),
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_cd) REFERENCES com_code_d(cd) ON DELETE RESTRICT,
    FOREIGN KEY (created_user) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (updated_user) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION generate_house_member_seq()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.seq IS NULL THEN
        SELECT COALESCE(MAX(seq), 0) + 1 
        INTO NEW.seq 
        FROM house_members 
        WHERE house_id = NEW.house_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_house_member_seq
    BEFORE INSERT ON house_members
    FOR EACH ROW
    EXECUTE FUNCTION generate_house_member_seq();

-- ============================================
-- 집 멤버 초대
-- ============================================
CREATE TABLE house_invitations (
    id VARCHAR(11) PRIMARY KEY,
    house_id VARCHAR(11) NOT NULL,
    inviter_user_id VARCHAR(10) NOT NULL,
    invitee_user_id VARCHAR(10) NOT NULL,
    status_cd VARCHAR(20) NOT NULL DEFAULT 'COM1400001',
    responded_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_user VARCHAR(10) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_user VARCHAR(10) NOT NULL,
    
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE CASCADE,
    FOREIGN KEY (inviter_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (invitee_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (status_cd) REFERENCES com_code_d(cd) ON DELETE RESTRICT,
    FOREIGN KEY (created_user) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (updated_user) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE SEQUENCE invitations_id_seq START 1;

CREATE OR REPLACE FUNCTION generate_invitation_id()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.id IS NULL OR NEW.id = '' THEN
        NEW.id := 'V' || TO_CHAR(CURRENT_DATE, 'YYYY') || LPAD(nextval('invitations_id_seq')::TEXT, 5, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_invitation_id
    BEFORE INSERT ON house_invitations
    FOR EACH ROW
    EXECUTE FUNCTION generate_invitation_id();

-- 대기중인 초대만 중복 방지
CREATE UNIQUE INDEX idx_unique_pending_invitation 
ON house_invitations(house_id, invitee_user_id) 
WHERE status_cd = 'COM1400001';

-- ============================================
-- 컨테이너 (영역/박스/물품 통합)
-- ============================================
CREATE TABLE containers (
    id VARCHAR(11) PRIMARY KEY,
    house_id VARCHAR(11) NOT NULL,
    up_container_id VARCHAR(11),
    type_cd VARCHAR(20) NOT NULL,
    name VARCHAR(200) NOT NULL,
    
    -- 물품 전용 컬럼
    quantity INT,
    remk TEXT,
    owner_user_id VARCHAR(10),
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_user VARCHAR(10) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_user VARCHAR(10) NOT NULL,
    
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE CASCADE,
    FOREIGN KEY (up_container_id) REFERENCES containers(id) ON DELETE CASCADE,
    FOREIGN KEY (type_cd) REFERENCES com_code_d(cd) ON DELETE RESTRICT,
    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (created_user) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (updated_user) REFERENCES users(id) ON DELETE RESTRICT,
    
    -- 물품일 때: quantity 필수이고 0 이상
    CHECK (type_cd != 'COM1200003' OR (quantity IS NOT NULL AND quantity >= 0)),
    
    -- 영역/박스일 때: quantity, owner_user_id는 NULL
    CHECK (type_cd = 'COM1200003' OR (quantity IS NULL AND owner_user_id IS NULL))
);

CREATE SEQUENCE containers_id_seq START 1;

CREATE OR REPLACE FUNCTION generate_container_id()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.id IS NULL OR NEW.id = '' THEN
        NEW.id := 'C' || TO_CHAR(CURRENT_DATE, 'YYYY') || LPAD(nextval('containers_id_seq')::TEXT, 5, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_container_id
    BEFORE INSERT ON containers
    FOR EACH ROW
    EXECUTE FUNCTION generate_container_id();

-- ============================================
-- 컨테이너 이력 (이동, 수정 등)
-- ============================================
CREATE TABLE container_logs (
    id VARCHAR(11) PRIMARY KEY,
    container_id VARCHAR(11),
    act_cd VARCHAR(20) NOT NULL,

    -- 컨테이너 정보 (삭제 대비)
    container_name VARCHAR(200),
    container_type_cd VARCHAR(20),

    -- 위치 변경
    from_container_id VARCHAR(11),
    to_container_id VARCHAR(11),

    -- 집 변경 (집 간 이동 시)
    from_house_id VARCHAR(11),
    to_house_id VARCHAR(11),

    -- 소유자 변경
    from_owner_user_id VARCHAR(10),
    to_owner_user_id VARCHAR(10),

    -- 수량 변경
    from_quantity INT,
    to_quantity INT,

    -- 메모 변경
    from_remk TEXT,
    to_remk TEXT,

    -- 이력 메모
    log_remk TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_user VARCHAR(10) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_user VARCHAR(10) NOT NULL,

    FOREIGN KEY (container_id) REFERENCES containers(id) ON DELETE SET NULL,
    FOREIGN KEY (act_cd) REFERENCES com_code_d(cd) ON DELETE RESTRICT,
    FOREIGN KEY (container_type_cd) REFERENCES com_code_d(cd) ON DELETE RESTRICT,
    FOREIGN KEY (from_container_id) REFERENCES containers(id) ON DELETE SET NULL,
    FOREIGN KEY (to_container_id) REFERENCES containers(id) ON DELETE SET NULL,
    FOREIGN KEY (from_house_id) REFERENCES houses(id) ON DELETE CASCADE,
    FOREIGN KEY (to_house_id) REFERENCES houses(id) ON DELETE CASCADE,
    FOREIGN KEY (created_user) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (updated_user) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE SEQUENCE container_logs_id_seq START 1;

CREATE OR REPLACE FUNCTION generate_container_log_id()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.id IS NULL OR NEW.id = '' THEN
        NEW.id := 'L' || TO_CHAR(CURRENT_DATE, 'YYYY') || LPAD(nextval('container_logs_id_seq')::TEXT, 5, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_container_log_id
    BEFORE INSERT ON container_logs
    FOR EACH ROW
    EXECUTE FUNCTION generate_container_log_id();

-- ============================================
-- 인덱스 생성
-- ============================================
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_account_status ON users(account_status);
CREATE INDEX idx_com_code_d_up_cd ON com_code_d(up_cd);
CREATE INDEX idx_house_members_house ON house_members(house_id);
CREATE INDEX idx_house_members_user ON house_members(user_id);
CREATE INDEX idx_invitations_house ON house_invitations(house_id);
CREATE INDEX idx_invitations_inviter ON house_invitations(inviter_user_id);
CREATE INDEX idx_invitations_invitee ON house_invitations(invitee_user_id);
CREATE INDEX idx_invitations_status ON house_invitations(status_cd);
CREATE INDEX idx_containers_house ON containers(house_id);
CREATE INDEX idx_containers_parent ON containers(up_container_id);
CREATE INDEX idx_containers_type ON containers(type_cd);
CREATE INDEX idx_containers_owner ON containers(owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX idx_containers_parent_type ON containers(up_container_id, type_cd);
CREATE INDEX idx_container_logs_container ON container_logs(container_id);
CREATE INDEX idx_container_logs_created ON container_logs(created_at);
CREATE INDEX idx_container_logs_from_house ON container_logs(from_house_id) WHERE from_house_id IS NOT NULL;
CREATE INDEX idx_container_logs_to_house ON container_logs(to_house_id) WHERE to_house_id IS NOT NULL;

-- ============================================
-- 코멘트
-- ============================================
COMMENT ON TABLE users IS '사용자';
COMMENT ON TABLE houses IS '집 정보';
COMMENT ON TABLE house_members IS '집 구성원';
COMMENT ON TABLE house_invitations IS '집 멤버 초대';
COMMENT ON TABLE containers IS '컨테이너 (영역/박스/물품 통합)';
COMMENT ON TABLE container_logs IS '컨테이너 이력 (이동, 수정 등)';
COMMENT ON TABLE com_code_m IS '공통코드 마스터';
COMMENT ON TABLE com_code_d IS '공통코드 상세';

COMMENT ON COLUMN users.account_status IS '계정 상태 (COM1500001: 활성, COM1500002: 삭제됨, COM1500003: 정지됨)';
COMMENT ON COLUMN containers.type_cd IS '컨테이너 유형 (COM1200001: 영역, COM1200002: 박스, COM1200003: 물품)';
COMMENT ON COLUMN containers.up_container_id IS '부모 컨테이너 (NULL이면 최상위)';
COMMENT ON COLUMN containers.quantity IS '수량 (물품일 때만 사용)';
COMMENT ON COLUMN containers.remk IS '메모 (물품일 때만 사용)';
COMMENT ON COLUMN containers.owner_user_id IS '소유자 (물품일 때만 사용)';
COMMENT ON COLUMN house_members.seq IS '집 내 구성원 순번 (자동 증가)';
COMMENT ON COLUMN container_logs.from_house_id IS '출발 집 (집 간 이동 시)';
COMMENT ON COLUMN container_logs.to_house_id IS '도착 집 (집 간 이동 시)';

-- ============================================
-- 공통코드 초기 데이터 (관리자 계정보다 먼저!)
-- ============================================

-- 공통코드 마스터 (created_user NULL로 먼저 생성)
INSERT INTO com_code_m (cd, nm, created_at, updated_at) VALUES 
('COM110', '권한', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM120', '컨테이너 종류', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM130', '행위', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM140', '초대 상태', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM150', '계정 상태', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 공통코드 상세 - 권한
INSERT INTO com_code_d (cd, nm, up_cd, created_at, updated_at) VALUES 
('COM1100001', '관리자', 'COM110', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1100002', '멤버', 'COM110', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 공통코드 상세 - 컨테이너 종류
INSERT INTO com_code_d (cd, nm, up_cd, created_at, updated_at) VALUES 
('COM1200001', '영역', 'COM120', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1200002', '박스', 'COM120', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1200003', '물품', 'COM120', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 공통코드 상세 - 행위
INSERT INTO com_code_d (cd, nm, up_cd, created_at, updated_at) VALUES 
('COM1300001', '생성', 'COM130', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1300002', '반출', 'COM130', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1300003', '이동', 'COM130', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1300004', '수정', 'COM130', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1300005', '수량변경', 'COM130', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1300006', '소유자변경', 'COM130', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 공통코드 상세 - 초대 상태
INSERT INTO com_code_d (cd, nm, up_cd, created_at, updated_at) VALUES 
('COM1400001', '대기', 'COM140', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1400002', '수락', 'COM140', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1400003', '거절', 'COM140', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1400004', '취소', 'COM140', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 공통코드 상세 - 계정 상태
INSERT INTO com_code_d (cd, nm, up_cd, created_at, updated_at) VALUES 
('COM1500001', '사용', 'COM150', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1500002', '삭제', 'COM150', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('COM1500003', '정지', 'COM150', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- ============================================
-- 초기 관리자 계정 생성
-- ============================================
-- ID: 0000000000
-- Email: admin@shareitem.com
-- Password: rhksflwk1! (bcrypt 암호화)
INSERT INTO users (id, email, password, name, account_status, created_at, updated_at) 
VALUES (
    '0000000000', 
    'admin@shareitem.com', 
    '$2b$12$.48NO56u0M8aMfXgSCfWoeyoVcVXtZV2rI5TsgaPEvoIMDdYRRkhS', 
    '시스템관리자', 
    'COM1500001',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- ============================================
-- 공통코드에 users FK 추가 및 created_user 업데이트
-- ============================================
-- FK 추가
ALTER TABLE com_code_m
    ADD FOREIGN KEY (created_user) REFERENCES users(id) ON DELETE SET NULL,
    ADD FOREIGN KEY (updated_user) REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE com_code_d
    ADD FOREIGN KEY (created_user) REFERENCES users(id) ON DELETE SET NULL,
    ADD FOREIGN KEY (updated_user) REFERENCES users(id) ON DELETE SET NULL;

-- created_user/updated_user 업데이트
UPDATE com_code_m SET created_user = '0000000000', updated_user = '0000000000';
UPDATE com_code_d SET created_user = '0000000000', updated_user = '0000000000';