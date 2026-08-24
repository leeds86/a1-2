"""
국내 여행 추천 프로그램 (통합 개선판)
Gemini API와 Kakao Map API를 이용한 여행 리포트 자동 생성
"""

import argparse       # CLI(검은 화면)에서 사용자가 입력한 '날짜'를 받아내는 도구[cite: 2]
import json           # 컴퓨터끼리 데이터를 주고받는 표준 문서 형식(JSON)을 다루는 도구[cite: 2]
import os             # 내 컴퓨터의 폴더를 만들거나 환경 변수(비밀번호 등)를 읽는 도구[cite: 2]
import re             # 수많은 글자 속에서 내가 원하는 패턴의 글자만 돋보기처럼 찾아내는 도구[cite: 2]
import sys            # 프로그램 강제 종료 등 시스템과 관련된 명령을 내리는 도구
from datetime import datetime   # 달력과 시계를 다루는 도구 (날짜 형식이 맞는지 확인용)[cite: 2]
from pathlib import Path        # 폴더나 파일 경로를 쉽게 다룰 수 있게 해주는 도구

import requests       # 파이썬이 웹사이트(API)에 접속하게 해주는 도구 (지도 API 호출용)[cite: 2]
import google.generativeai as genai  # 구글 제미나이(AI)에게 일을 시키기 위한 전용 도구[cite: 2]
from dotenv import load_dotenv       # .env 파일(숨겨진 비밀번호 파일)을 여는 도구[cite: 2]


def init_environment() -> str:
    """환경 변수 로드 및 API 키 검증 (시작 전 준비 운동)"""
    load_dotenv()  # .env 파일에서 키 불러오기[cite: 2]
    
    # 1. 키 확인 (미설정 시 즉시 종료)[cite: 2]
    gemini_key = os.getenv("GEMINI_API_KEY")
    kakao_key = os.getenv("KAKAO_API_KEY")
    
    if not gemini_key or not kakao_key:  # 만약 둘 중 하나라도 없으면?[cite: 2]
        print("❌ API 키가 없습니다. .env 파일에 키를 설정하세요.")  # 경고 메시지를 보여주고[cite: 2]
        print("예시) GEMINI_API_KEY=AIzaSy...  /  KAKAO_API_KEY=...")
        sys.exit(1)  # 프로그램을 즉시(에러 상태로) 종료합니다.[cite: 2]
        
    # 제미나이 API 설정 및 모델 지정[cite: 2]
    genai.configure(api_key=gemini_key) # 제미나이에게 내 키를 보여주며 사용 설정을 합니다.[cite: 2]
    return kakao_key


def parse_arguments() -> str:
    """CLI 인자 파싱 및 날짜 검증 (사용자가 입력한 날짜 확인하기)"""
    parser = argparse.ArgumentParser(description="국내 여행지 추천 프로그램") #[cite: 2]
    parser.add_argument("--date", required=True, help='여행 날짜 "YYYY-MM-DD"') #[cite: 2]
    args = parser.parse_args()
    
    # 날짜 형식 검증[cite: 2]
    try:
        # 사용자가 입력한 글자가 진짜 날짜 형식이 맞는지 달력 도구로 확인합니다.
        datetime.strptime(args.date, "%Y-%m-%d")
        return args.date
    except ValueError:
        print(f"❌ 날짜 형식이 올바르지 않습니다: {args.date}\n사용법 예시: --date 2024-12-25")
        sys.exit(1)


def get_recommendation(date_str: str) -> dict:
    """LLM으로 1차 추천 (JSON 받기)[cite: 2]"""
    model = genai.GenerativeModel("gemini-3.5-flash-lite")
    
    # AI에게 부탁할 내용을 꼼꼼하게 적습니다.
    prompt = f"""당신은 한국 여행 전문가입니다. 
{date_str}에 한국에서 가장 추천할 만한 도시를 선택해주세요.
반드시 아래 JSON 형식으로만 답해주세요. 마크다운이나 다른 설명은 절대 포함하지 마세요.
{{
    "recommended_city": "도시명",
    "weather": "해당 시기 날씨 요약",
    "events": ["행사1", "행사2", "행사3"],
    "reason": "추천 이유 2~3문장"
}}
"""
    # 파싱 실패하면 1회만 재시도[cite: 2]
    for attempt in range(2):
        try:
            # 제미나이 모델 호출[cite: 2]
            res = model.generate_content(prompt) # AI에게 질문을 던져서 답변을 받습니다.[cite: 2]
            
            # 코드블록 등 불필요한 글자 제거 후 진짜 데이터(JSON)만 돋보기(re)로 추출[cite: 2]
            json_text = re.search(r'\{.*\}', res.text, re.DOTALL).group()
            return json.loads(json_text) # 찾아낸 글자를 컴퓨터가 읽을 수 있는 데이터로 변환해서 반환(보고)합니다.[cite: 2]
        except Exception as e: # 만약 AI가 양식을 틀려서 에러가 났다면?[cite: 2]
            if attempt == 0: # 첫 번째 시도였다면[cite: 2]
                prompt += "\n경고: 반드시 순수 JSON만 출력해." # 경고를 추가해서 재시도[cite: 2]
            else:
                print(f"⚠️ LLM JSON 파싱 실패: {e}") 
                return {} # 포기하고 '빈손'으로 돌아옵니다.


def search_restaurants(city: str, kakao_key: str, size: int = 5) -> list:
    """카카오로 맛집 검색[cite: 2]"""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json" # 카카오 맛집 검색 창구 주소[cite: 2]
    headers = {"Authorization": f"KakaoAK {kakao_key}"} # 카카오에게 내 API 키를 보여줍니다.[cite: 2]
    params = {"query": f"{city} 맛집", "size": size}
    
    try:
        # 카카오 서버에 요청을 보냅니다. (10초 안에 답이 안 오면 끊어버림)[cite: 2]
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status() # 카카오가 혹시 에러(예: 키 오류)를 뱉었는지 확인[cite: 2]
        
        docs = response.json().get("documents", []) # 정상 작동한다면 카카오가 준 답변 중 '가게 정보(documents)'만 꺼냅니다.[cite: 2]
        
        # 복잡한 카카오의 답변 중에서 내가 필요한 것(가게명, 주소, 종류, 지도링크)만 깔끔하게 추려서 반환[cite: 2]
        return [{
            "name": d.get("place_name", ""),
            "address": d.get("address_name", ""),
            "category": d.get("category_name", ""),
            "url": d.get("place_url", "")
        } for d in docs]
    except Exception as e: # 만약 인터넷이 끊겼거나 카카오가 응답하지 않는다면?[cite: 2]
        print(f"⚠️ 맛집 검색 실패: {e}") 
        return [] # 실패해도 빈 리스트로 계속 진행[cite: 2]


def generate_report(date_str: str, rec: dict, restaurants: list) -> str:
    """LLM으로 최종 리포트(Markdown) 생성[cite: 2]"""
    model = genai.GenerativeModel("gemini-3.5-flash-lite")
    
    # 맛집 데이터가 있다면 마크다운 링크 문법 [가게명](URL) 형식으로 변환하여 AI에게 전달합니다.
    # 이렇게 하면 AI가 리포트를 쓸 때 링크를 클릭할 수 있게 만들어줍니다.
    if restaurants:
        rest_list = []
        for r in restaurants:
            # ex) - [스타벅스](http://place.map.kakao...) (카페): 서울 강남구...
            rest_list.append(f"- [{r['name']}]({r['url']}) ({r['category']}): {r['address']}")
        rest_text = "\n".join(rest_list)
    else:
        rest_text = "- 검색된 맛집 없음"
    
    prompt = f"""당신은 훌륭한 여행 가이드입니다.
아래 정보로 여행 리포트를 Markdown으로 작성해줘.[cite: 2]

날짜: {date_str}[cite: 2]
추천정보: {json.dumps(rec, ensure_ascii=False)}[cite: 2]

맛집 정보 (이미 마크다운 링크로 포맷팅되어 있음):
{rest_text}

Markdown 서식만 사용하여 제목, 소제목, 본문을 작성하세요.
특히 맛집 리스트는 제가 제공한 링크 형식( [가게명](URL) )을 그대로 출력해서 사용자가 클릭할 수 있도록 해주세요.
"""
    try:
        # 제미나이 모델 호출[cite: 2]
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"⚠️ 리포트 생성 실패: {e}"


def main():
    """메인 실행[cite: 2] (프로그램의 시작점)"""
    # 1. 준비 작업 (키 확인 및 날짜 받아오기)
    kakao_key = init_environment()
    date_str = parse_arguments()
    
    print(f"✅ 여행 날짜: {date_str}")
    
    # 2. AI에게 여행지 추천 받기
    print("[1/3] 1차 추천 생성 중(LLM)...") #[cite: 2]
    recommendation = get_recommendation(date_str)
    if not recommendation:
        print("❌ 추천 생성 실패로 종료합니다.") #[cite: 2]
        sys.exit(1)
    
    city = recommendation.get("recommended_city", "서울")
    print(f"  - recommended_city: \"{city}\"") #[cite: 2]
    
    # 3. 카카오맵에서 맛집 찾기
    print("[2/3] 맛집 검색 중(지도 API)...") #[cite: 2]
    restaurants = search_restaurants(city, kakao_key)
    print(f"  - 맛집 {len(restaurants)}곳 검색 완료") #[cite: 2]
    
    # 4. 종합해서 최종 마크다운 보고서 만들기
    print("[3/3] 최종 리포트 생성 중(LLM)...") #[cite: 2]
    report = generate_report(date_str, recommendation, restaurants)
    
    # 5. 결과 저장[cite: 2]
    # 폴더가 없으면 에러가 나지 않게 만들어줍니다 (exist_ok=True)[cite: 2]
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    
    # 컴퓨터가 읽을 원본 데이터(JSON)와 사람이 읽을 리포트(MD)를 각각 저장합니다.
    with open(results_dir / f"data_{date_str}.json", "w", encoding="utf-8") as f:
        json.dump({"recommendation": recommendation, "restaurants": restaurants}, f, ensure_ascii=False, indent=2)
        
    with open(results_dir / f"report_{date_str}.md", "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"\n✨ 리포트 생성 완료 → {results_dir}/report_{date_str}.md") #[cite: 2]
    
    # 완성된 결과물을 화면에도 보여줍니다.
    print("\n" + "="*60)
    print(report)
    print("="*60)


if __name__ == "__main__":
    main()