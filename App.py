from flask import Flask
from flask_cors import CORS
from config import Config
from routes import register_blueprints

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Blueprint 등록
register_blueprints(app)

# 헬스체크
@app.route('/api/health', methods=['GET'])
def health_check():
    return {'status': 'ok', 'message': 'API 서버가 정상 작동 중입니다'}

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Flask API 서버 시작")
    print("=" * 50)
    print("📍 서버 주소: http://0.0.0.0:3001")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=3001, debug=True)