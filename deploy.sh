!/bin/bash
# 1. 최신 코드 가져오기
git pull origin main
# 2. 백엔드 업데이트 (Venv 환경 유지)
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head # DB 마이그레이션 자동 실행
# 3. 프론트엔드 빌드
cd svelte
npm install
npm run build
cd ..
# 4. PM2 안전하게 재시작 (Graceful Reload)
# restart 대신 reload를 쓰면 무중단 배포를 시도합니다.
pm2 reload ecosystem.config.js --env production
echo "배포 완료!"
