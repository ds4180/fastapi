import os
import time
import stat
from datetime import datetime

# 설정
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
LOG_FILE = "gc_log.txt"
TMP_RETENTION_HOURS = 24
DELETE_RETENTION_DAYS = 7

def run_gc():
    now = time.time()
    tmp_limit = now - (TMP_RETENTION_HOURS * 3600)
    delete_limit = now - (DELETE_RETENTION_DAYS * 86400)

    # 통계 변수
    f_scanned, f_deleted, f_failed = 0, 0, 0
    d_scanned, d_deleted, d_failed = 0, 0, 0

    for root, dirs, files in os.walk(UPLOAD_DIR, topdown=False):
        d_scanned += 1
        for file in files:
            f_scanned += 1
            file_path = os.path.join(root, file)
            
            try:
                file_mtime = os.path.getmtime(file_path)
                should_delete = False
                
                # 삭제 조건 판단
                if "/tmp/" in file_path.replace("\\", "/"):
                    if file_mtime < tmp_limit:
                        should_delete = True
                elif file.startswith("delete_"):
                    if file_mtime < delete_limit:
                        should_delete = True

                if should_delete:
                    # [대응책] 권한 강제 변경 시도 후 삭제
                    try:
                        os.chmod(file_path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
                        os.remove(file_path)
                        f_deleted += 1
                    except Exception as e:
                        print(f"GC Error (File): {file_path} -> {e}")
                        f_failed += 1
            except:
                f_failed += 1

        # 빈 폴더 정리
        if root != UPLOAD_DIR and not os.listdir(root):
            try:
                # [대응책] 폴더 권한 변경 후 삭제 시도
                os.chmod(root, 0o777)
                os.rmdir(root)
                d_deleted += 1
            except Exception as e:
                if root != UPLOAD_DIR:
                    # print(f"GC Error (Dir): {root} -> {e}")
                    d_failed += 1

    # 결과 한 줄 로그 생성 (에러 카운트 추가)
    exec_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = (f"[{exec_time}] "
                 f"파일(검색:{f_scanned}/삭제:{f_deleted}/실패:{f_failed}) "
                 f"폴더(검색:{d_scanned}/삭제:{d_deleted}/실패:{d_failed})\n")

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)

    print(log_entry.strip())

if __name__ == "__main__":
    run_gc()
