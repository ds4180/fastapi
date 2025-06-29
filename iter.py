# 리스트 생성 (이터러블)
my_list = ['서울', '부산', '대구', '광주', '제주', '미국']

print("리스트:", my_list)

# 리스트로부터 이터레이터 객체 얻기
my_iterator = iter(my_list)
# my_iterator = iter(['한국', '미국', '영국'])

print("\n이터레이터 객체의 __next__() 메서드를 사용하여 요소 하나씩 가져오기:")

# while True 루프와 try-except StopIteration 패턴 사용
while True:
    try:
        # 이터레이터 객체의 __next__() 메서드를 직접 호출
        item = my_iterator.__next__()
        print(item)

    except StopIteration:
        # 더 이상 가져올 요소가 없으면 StopIteration 예외 발생
        print("순회 완료: StopIteration 예외 발생 확인.")
        break # 예외 발생 시 루프 종료
