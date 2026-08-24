import argparse       # CLI에서 사용자가 입력한 '날짜'를 받아내는 도구
import json           # 컴퓨터끼리 데이터를 주고받는 표준 문서 형식(JSON)을 다루는 도구
import os             # 내 컴퓨터의 폴더를 만들거나 환경 변수(비밀번호 등)를 읽는 도구
import re             # 수많은 글자 속에서 내가 원하는 패턴의 글자만 돋보기처럼 찾아내는 도구
from datetime import datetime   # 달력과 시계를 다루는 도구 (날짜 형식이 맞는지 확인용)
import requests       # 파이썬이 웹사이트에 접속하게 해주는 도구 (지도 API 호출용)
import google.generativeai as genai  # 구글 제미나이(AI)에게 일을 시키기 위한 전용 도구
from dotenv import load_dotenv       # .env 파일을 여는 도구

load_dotenv()  # .env 파일에서 키 불러오기

# --- 1. 키 확인 (미설정 시 즉시 종료) ---
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
KAKAO_KEY = os.getenv("KAKAO_API_KEY")

if not GEMINI_KEY or not KAKAO_KEY:    # 만약 둘 중 하나라도 없으면?
    print("❌ API 키가 없습니다. .env 파일에 키를 설정하세요.")     # 경고 메시지를 보여주고
    print("예시) GEMINI_API_KEY=AIzaSy...  /  KAKAO_API_KEY=...")
    exit()                             # 프로그램을 즉시 종료합니다.

# 제미나이 API 설정 및 모델 지정
genai.configure(api_key=GEMINI_KEY) # 제미나이에게 내 키를 보여주며 사용 설정을 합니다.
model = genai.GenerativeModel("gemini-3.5-flash-lite")

errors = []  # 오류를 모아 리포트에 남김


# --- 2. LLM으로 1차 추천 (JSON 받기) ---
def get_recommendation(date):
    prompt = f"""
{date}에 국내 여행하기 좋은 곳을 추천해줘.
반드시 아래 JSON 형식으로만 답해줘. 다른 말은 하지 마.
{{
  "recommended_city": "도시명",
  "weather": "그 시기 날씨 요약",
  "events": ["행사1", "행사2"],
  "reason": "추천 이유 2~4문장"
}}
"""
    # 파싱 실패하면 1회만 재시도
    for attempt in range(2):
        try:
            # 제미나이 모델 호출
            res = model.generate_content(prompt) # AI에게 질문을 던져서 답변을 받습니다.
            text = res.text # 답변에서 글자만 뽑아냅니다.
            
            # 코드블록 등 불필요한 글자 제거 후 진짜 데이터(JSON)만 돋보기(re)로 추출
            json_text = re.search(r'\{.*\}', text, re.DOTALL).group()
            return json.loads(json_text) # 찾아낸 글자를 컴퓨터가 읽을 수 있는 데이터로 변환해서 반환(보고)합니다.
        except Exception as e: # 만약 AI가 양식을 틀려서 에러가 났다면?
            if attempt == 0: # 첫 번째 시도였다면
                prompt += "\n반드시 순수 JSON만 출력해."  # 경고를 추가해서 재시도
            else:
                errors.append(f"LLM JSON 파싱 실패: {e}") # 오류 수첩에 적고
                return None # 포기하고 '빈손(None)'으로 돌아옵니다.


# --- 3. 카카오로 맛집 검색 ---
def search_restaurants(city):
    try:
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"  # 카카오 맛집 검색 창구 주소
        headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"} # 카카오에게 내 API 키를 보여줍니다.
        params = {"query": f"{city} 맛집", "size": 5}
        # 카카오 서버에 요청을 보냅니다. (10초 안에 답이 안 오면 끊어버림)
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.raise_for_status() # 카카오가 혹시 에러(예: 키 오류)를 뱉었는지 확인
        docs = res.json()["documents"] # 정상 작동한다면 카카오가 준 답변 중 '가게 정보(documents)'만 꺼냅니다.
        # 복잡한 카카오의 답변 중에서 내가 필요한 것(가게명, 주소, 종류, 지도링크)만 깔끔하게 추려서 반환
        return [{
            "name": d["place_name"],
            "address": d["address_name"],
            "category": d["category_name"],
            "url": d["place_url"],
        } for d in docs]
    except Exception as e: # 만약 인터넷이 끊겼거나 카카오가 응답하지 않는다면?
        errors.append(f"맛집 검색 실패: {e}") # 오류 수첩에 적고
        return []  # 실패해도 빈 리스트로 계속 진행


# --- 4. LLM으로 최종 리포트(Markdown) 생성 ---
def make_report(rec, restaurants, date):
    rest_text = "데이터 없음" if not restaurants else json.dumps(restaurants, ensure_ascii=False)
    prompt = f"""
아래 정보로 여행 리포트를 Markdown으로 작성해줘.
날짜: {date}
추천정보: {json.dumps(rec, ensure_ascii=False)}
맛집: {rest_text}

포함 항목: 추천지역+이유, 날씨 요약, 행사/축제, 맛집 리스트(없으면 '데이터 없음'), 1일 일정(오전/오후/저녁)
"""
    # 제미나이 모델 호출
    res = model.generate_content(prompt)
    return res.text


# --- 5. 메인 실행 ---
def main():
    parser = argparse.ArgumentParser(description="국내 여행지 추천 프로그램")
    parser.add_argument("--date", required=True, help='여행 날짜 "YYYY-MM-DD"')
    args = parser.parse_args()

    # 날짜 형식 검증
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print('❌ 날짜 형식 오류. 예: --date "2025-03-15"')
        exit()

    os.makedirs("results", exist_ok=True)

    print("[1/3] 1차 추천 생성 중(LLM)...")
    rec = get_recommendation(args.date)
    if not rec:
        print("추천 생성 실패로 종료합니다.")
        exit()
    print(f'  - recommended_city: "{rec["recommended_city"]}"')

    print("[2/3] 맛집 검색 중(지도 API)...")
    restaurants = search_restaurants(rec["recommended_city"])
    print(f"  - 맛집 {len(restaurants)}곳 검색 완료")

    print("[3/3] 최종 리포트 생성 중(LLM)...")
    report = make_report(rec, restaurants, args.date)

    # 결과 저장
    raw = {"recommendation": rec, "restaurants": restaurants, "errors": errors}
    with open(f"results/{args.date}_raw.json", "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    with open(f"results/{args.date}_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    print(f"  - 리포트 생성 완료 → results/{args.date}_report.md")


if __name__ == "__main__":
    main()