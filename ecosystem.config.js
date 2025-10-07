const path = require('path');

module.exports = {
  apps: [
    {
      name: 'sveltekit-app', // SvelteKit 앱을 식별할 이름
      script: 'svelte/build/index.js', // SvelteKit 빌드 후 생성되는 서버 파일
      cwd: '.', // 프로젝트 루트 디렉터리에서 실행
      env: {
        // SvelteKit 앱이 'production' 모드로 실행되도록 설정합니다.
        // pm2는 기본적으로 NODE_ENV를 'production'으로 설정하지만, 명시적으로 작성하는 것이 좋습니다.
        // 이 설정은 SvelteKit이 .env.production 파일을 읽고 프로덕션 최적화를 적용하는 데 사용됩니다.
        NODE_ENV: 'production',
        // Nginx와 같은 리버스 프록시 뒤에서 실행될 때 CSRF 보호 오류를 방지하기 위한 설정입니다.
        // SvelteKit이 프록시가 전달하는 'x-forwarded-*' 헤더를 신뢰하여 원래 요청의 호스트와 프로토콜을 알 수 있게 합니다.
        HOST_HEADER: 'x-forwarded-host',
        PROTOCOL_HEADER: 'x-forwarded-proto',
        // SvelteKit 서버에서 FastAPI 백엔드 서버로 API 요청을 보낼 때 사용할 URL입니다.
        SERVER_URL: 'http://192.168.200.217:8000',
        // 파일 업로드 시 저장될 서버의 절대 경로입니다.
        UPLOAD_DIR: '/home/lee/uv-code/test/svelte/uploads',
        // SvelteKit 서버의 최대 요청 본문 크기 제한입니다. (100MB)
        BODY_SIZE_LIMIT: '104857600',

      },
    },
    {
      name: 'fastapi-app', // FastAPI 앱을 식별할 이름
      script: path.resolve(__dirname, '.venv/bin/uvicorn'), // uvicorn을 모듈로 실행
      interpreter: 'none',
      cwd: '.', // FastAPI 프로젝트 루트 디렉터리 (현재 위치)
      // args를 배열로 분리하여 각 인자를 명확하게 전달합니다.
      args: ['main:app', '--host', '0.0.0.0', '--port', '8000'], // uvicorn에 전달할 인자들
    },
  ],
};
