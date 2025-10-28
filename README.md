# postgreSQLRestAPI

# PM2
## PM2로 실행
pm2 start app.py --name flask-api --interpreter python3

## PM2 로그 확인
pm2 logs flask-api



# psql

## postgres 사용자로 접속
sudo -u postgres psql

## 특정 데이터베이스 지정
sudo -u postgres psql -d postgres

## 데이터베이스 목록
\l

## 테이블 목록
\dt

## 테이블 구조 보기
\d users
\d+ users  -- 상세 정보

## 현재 데이터베이스 확인
\c

## 데이터베이스 변경
\c postgres

## 사용자 목록
\du

## 종료
\q

## 도움말
\?

## SQL 명령어 도움말
\h SELECT
