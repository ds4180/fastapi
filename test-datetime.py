from datetime import datetime, timedelta

# 시작 날짜
start_date = datetime.strptime("2025-06-27", "%Y-%m-%d")

# 날짜 리스트 생성
date_list = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]

print(date_list)
