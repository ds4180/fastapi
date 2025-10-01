const path = require('path');

module.exports = {
  apps: [
    {
      name: 'sveltekit-app', // SvelteKit 앱을 식별할 이름
      script: 'build/index.js', // SvelteKit 빌드 후 생성되는 서버 파일
      cwd: './svelte', // SvelteKit 프로젝트 디렉터리
      env: {
        // 이 부분이 CSRF 문제 해결의 핵심입니다.
        // Nginx가 전달하는 헤더를 신뢰하도록 SvelteKit에 알려줍니다.
        HOST_HEADER: 'x-forwarded-host',
        PROTOCOL_HEADER: 'x-forwarded-proto',

        // SvelteKit 서버가 FastAPI 서버와 통신할 API 주소를 설정합니다.
        // Nginx를 통해 외부에서 접근하는 경로를 사용합니다.
        SERVER_URL: 'http://localhost',
      },
    },
    {
      name: 'fastapi-app', // FastAPI 앱을 식별할 이름
      script: path.resolve(__dirname, '.venv/bin/uvicorn'), // uvicorn을 모듈로 실행
      interpreter: 'none',
      cwd: '.', // FastAPI 프로젝트 디렉터리 (현재 위치)
      // args를 배열로 분리하여 각 인자를 명확하게 전달합니다.
      args: ['main:app', '--host', '0.0.0.0', '--port', '8000'], // uvicorn에 전달할 인자들
    },
  ],
};
