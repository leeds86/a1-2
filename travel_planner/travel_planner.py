"""
국내 여행 추천 프로그램 (보너스 과제 달성판)
1. 복수 지역 추천 및 반복(Loop) 처리
2. JSON 파일 유무에 따른 결과 캐싱(API 호출 생략)
"""

import argparse       # CLI(검은 화면)에서 사용자가 입력한 '날짜'를 받아내는 도구
import json           # 컴퓨터끼리 데이터를 주고받는 표준 문서 형식(JSON)을 다루는 도구
import os             # 내 컴퓨터의 폴더를 만들거나 환경 변수(비밀번호 등)를 읽는 도구
import re             # 수많은 글자 속에서 내가 원하는 패턴의 글자만 찾아내는 도구
import sys            # 프로그램 강제 종료 등 시스템과 관련된 명령을 내리는 도구
from datetime import datetime   # 달력과 시계를 다루는 도구 (날짜 형식이 맞는지 확인용)
from pathlib import Path        # 폴더나 파일 경로를 쉽게 다룰 수 있게 해주는 도구

import requests       # 파이썬이 웹사이트(API)에 접속하게 해주는 도구
import google.generativeai as genai  # 구글 제미나이(AI) 전용 도구
from dotenv import load_dotenv       # .env 파일(숨겨진 비밀번호 파일)을 여는 도구


def init_environment() -> str:
    """환경 변수 로드 및 API 키 검증"""
    load_dotenv()
    
    gemini_key = os.getenv("GEMINI_API_KEY")
    kakao_key = os.getenv("KAKAO_API_KEY")
    
    if not gemini_key or not kakao_key:
        print("❌ API 키가 없습니다. .env 파일에 키를 설정하세요.")
        sys.exit(1)
        
    genai.configure(api_key=gemini_key)
    return kakao_key


def parse_arguments() -> str:
    """CLI 인자 파싱 및 날짜 검증"""
    parser = argparse.ArgumentParser(description="국내 여행지 추천 프로그램")
    parser.add_argument("--date", required=True, help='여행 날짜 "YYYY-MM-DD"')
    args = parser.parse_args()
    
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
        return args.date
    except ValueError:
        print(f"❌ 날짜 형식이 올바르지 않습니다: {args.date}")
        sys.exit(1)


def get_recommendations(date_str: str) -> dict:
    """[과제1] LLM으로 복수의 여행지 추천받기"""
    model = genai.GenerativeModel("gemini-3.5-flash-lite")
    
    # 💡 프롬프트 변경: 1개의 도시가 아닌 2~3개의 도시를 배열(List)로 요구합니다.
    prompt = f"""당신은 한국 여행 전문가입니다. 
{date_str}에 한국에서 가장 추천할 만한 도시를 2~3곳 선택해주세요.
반드시 아래 JSON 형식으로만 답해주세요. 마크다운이나 다른 설명은 절대 포함하지 마세요.
{{
    "recommended_cities": [
        {{
            "city": "도시명1",
            "weather": "해당 시기 일반적 날씨 요약",
            "events": ["축제나 행사명 1~3개 사이로 작성"],
            "reason": "추천 근거 2~4문장"
        }},
        {{
            "city": "도시명2",
            "weather": "해당 시기 일반적 날씨 요약",
            "events": ["축제나 행사명 1~3개 사이로 작성"],
            "reason": "추천 근거 2~4문장"
        }}
    ]
}}
"""
    for attempt in range(2):
        try:
            res = model.generate_content(prompt)
            json_text = re.search(r'\{.*\}', res.text, re.DOTALL).group() #LLM JSON 파싱 방어
            return json.loads(json_text)
        except Exception as e:
            if attempt == 0:
                prompt += "\n경고: 반드시 순수 JSON만 출력해."
            else:
                print(f"⚠️ LLM JSON 파싱 실패: {e}") 
                return {"recommended_cities": []}


def search_restaurants(city: str, kakao_key: str, size: int = 5) -> list:
    """카카오로 특정 도시의 맛집 검색"""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {kakao_key}"}
    params = {"query": f"{city} 맛집", "size": size}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        # 401(권한 없음), 403(금지됨) 등의 상태 코드가 오면 여기서 에러를 발생시켜 프로그램 중단을 막고 except로 넘깁니다.
        response.raise_for_status()
        docs = response.json().get("documents", [])

        # 요구사항에 명시된 모든 필수 필드(name, address, category, url, x, y)를 추출합니다.
        return [{
            "name": d.get("place_name", ""),
            "address": d.get("address_name", ""),
            "category": d.get("category_name", ""),
            "url": d.get("place_url", ""),
            "x": d.get("x", ""),  # 경도(Longitude) 추가됨
            "y": d.get("y", "")   # 위도(Latitude) 추가됨
        } for d in docs]
    except Exception as e:
        print(f"⚠️ {city} 맛집 검색 실패: {e}")
        # 에러가 나거나 검색 결과가 0건이어도 프로그램이 중단되지 않고 빈 리스트를 반환하여 다음 단계로 넘어갑니다. 
        return []


# 💡 매개변수에 errors: list = None 을 추가
def generate_report(date_str: str, rec: dict, restaurants_by_city: dict, errors: list = None) -> str:
    """LLM으로 지역별 최종 리포트(Markdown) 생성"""

    # 에러 바구니가 비어있으면 안전하게 빈 리스트로 초기화
    if errors is None:
        errors = []

    model = genai.GenerativeModel("gemini-3.5-flash-lite")
    
    # 💡 지역별로 맛집 데이터를 예쁘게 포장합니다.
    rest_list = []
    for city, rests in restaurants_by_city.items():
        rest_list.append(f"### {city} 맛집")
        if rests:
            for r in rests:
                rest_list.append(f"- [{r['name']}]({r['url']}) ({r['category']}): {r['address']}")
        else:
            rest_list.append("- 검색된 맛집 없음")
            
    rest_text = "\n".join(rest_list)

    # 💡 누적된 에러를 텍스트로 변환하는 로직 추가
    error_text = "\n".join([f"- {err}" for err in errors]) if errors else "- 없음"
    
    prompt = f"""당신은 훌륭한 여행 가이드입니다.
아래 정보로 여행 리포트를 Markdown으로 작성해줘.
Markdown 서식만 사용하여 제목, 소제목, 본문을 작성해줘.
본문에는 각 지역별 추천 이유와 날씨, 행사/축제, 맛집 리스트, 1일 일정 제안, 그리고 오류 요약(errors) 결과{error_text}를 반드시 포함해줘.

날짜: {date_str}
추천정보: {json.dumps(rec, ensure_ascii=False)}

맛집 정보 (마크다운 링크 포함):
{rest_text}
"""
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"⚠️ 리포트 생성 실패: {e}"


def main():
    kakao_key = init_environment()
    date_str = parse_arguments()

    # 프로그램 시작 시 에러를 담을 빈 바구니 준비
    errors = []
    
    print(f"✅ 여행 날짜: {date_str}")
    
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    
    # 저장될 JSON 데이터 파일 경로
    data_file = results_dir / f"data_{date_str}.json"
    
    # 💡 결과 캐싱 적용
    # 만약 기존에 저장된 데이터가 있다면 API를 부르지 않고 바로 꺼내 씁니다.
    if data_file.exists():
        print("💾 기존에 저장된 데이터를 발견했습니다! (API 호출 생략)")
        with open(data_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
            recommendation = saved_data.get("recommendation", {})
            restaurants_by_city = saved_data.get("restaurants", {})
            
    # 저장된 데이터가 없다면 평소처럼 API를 호출해 새 데이터를 만듭니다.
    else:
        print("🤖 [1/3] 복수 추천 도시를 분석 중입니다(LLM)...")
        recommendation = get_recommendations(date_str)

        # LLM 응답 직후 필수 키 검증!
        required_keys = ["recommended_cities", "weather", "events", "reason"]
        for key in required_keys:
            if key not in recommendation:
                errors.append(f"1차 LLM 응답 에러: 필수 키 '{key}' 누락됨")
                
                # 프로그램이 뻗지 않도록 기본값 채워주기
                if key == "recommended_cities":
                    recommendation[key] = []  # 도시는 리스트 형태이므로 빈 리스트로 방어
                else:
                    recommendation[key] = "데이터 없음"

        # 이후 기존 로직 정상 실행
        cities = [item.get("city") for item in recommendation.get("recommended_cities", []) if item.get("city")]
        
        if not cities:
            print("❌ 추천 도시를 가져오지 못해 종료합니다.")
            sys.exit(1)
            
        print(f"  - 추천된 도시: {', '.join(cities)}")
        
        # 💡 복수 지역 맛집 검색 (Loop)
        print("🗺️  [2/3] 각 도시별 맛집을 검색 중입니다(지도 API)...")
        restaurants_by_city = {}
        for city in cities:
            print(f"    ▶ {city} 맛집 검색 중...")
            restaurants_by_city[city] = search_restaurants(city, kakao_key)
            
        # 처음 가져온 데이터를 다음 번 캐싱을 위해 저장해 둡니다.
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump({
                "recommendation": recommendation, 
                "restaurants": restaurants_by_city
            }, f, ensure_ascii=False, indent=2)

    # 3. 리포트는 매번 새롭게 생성합니다 (또는 문맥에 맞게 다듬기 위함)
    print("📝 [3/3] 최종 리포트 생성 중(LLM)...")
    report = generate_report(date_str, recommendation, restaurants_by_city, errors)
    
    with open(results_dir / f"report_{date_str}.md", "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"\n✨ 리포트 생성 완료 → {results_dir}/report_{date_str}.md")


if __name__ == "__main__":
    main()