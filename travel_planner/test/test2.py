"""
국내 여행 추천 프로그램
LLM API(gemini-3.5-flash-lite)와 Kakao Map API를 이용한 여행 리포트 생성
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


def load_args_and_init() -> str:
    """
    CLI 인자 파싱 및 초기화
    - 날짜 형식 검증
    - API 키 확인
    - 결과 저장 디렉토리 생성
    """
    parser = argparse.ArgumentParser(
        description="국내 여행 추천 프로그램",
        usage="python travel_recommender.py --date YYYY-MM-DD"
    )
    parser.add_argument(
        "--date",
        type=str,
        required=True,
        help="여행 날짜 (형식: YYYY-MM-DD)"
    )
    
    args = parser.parse_args()
    date_str = args.date
    
    # 날짜 형식 검증
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        parser.error(f"날짜 형식이 올바르지 않습니다: {date_str}\n사용법: python travel_recommender.py --date YYYY-MM-DD")
        sys.exit(1)
    
    # .env 파일에서 API 키 읽기
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ 오류: .env 파일을 찾을 수 없습니다.")
        print("다음 내용으로 .env 파일을 생성하세요:")
        print("GEMINI_API_KEY=your_api_key_here")
        print("KAKAO_API_KEY=your_api_key_here")
        sys.exit(1)
    
    env_vars = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    
    if "GEMINI_API_KEY" not in env_vars or not env_vars["GEMINI_API_KEY"]:
        print("❌ 오류: GEMINI_API_KEY가 .env에 설정되지 않았습니다.")
        sys.exit(1)
    
    if "KAKAO_API_KEY" not in env_vars or not env_vars["KAKAO_API_KEY"]:
        print("❌ 오류: KAKAO_API_KEY가 .env에 설정되지 않았습니다.")
        sys.exit(1)
    
    # 환경 변수 설정
    os.environ["GEMINI_API_KEY"] = env_vars["GEMINI_API_KEY"]
    os.environ["KAKAO_API_KEY"] = env_vars["KAKAO_API_KEY"]
    
    # 결과 저장 디렉토리 생성
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    
    return date_str


def call_llm(prompt: str) -> str:
    """
    gemini-3.5-flash-lite API 호출
    urllib를 이용한 HTTP 요청
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={api_key}"
    
    request_body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    
    json_data = json.dumps(request_body).encode("utf-8")
    
    try:
        req = urllib.request.Request(
            url,
            data=json_data,
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))
            
            # 응답에서 텍스트 추출
            if "candidates" in response_data and len(response_data["candidates"]) > 0:
                candidate = response_data["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    if len(parts) > 0 and "text" in parts[0]:
                        return parts[0]["text"]
            
            raise ValueError("LLM 응답 형식이 올바르지 않습니다.")
    
    except urllib.error.URLError as e:
        raise RuntimeError(f"API 호출 실패: {e}")


def recommend_city(date_str: str) -> Dict[str, Any]:
    """
    LLM을 이용한 1차 추천 (도시, 날씨, 행사)
    """
    prompt = f"""당신은 한국 여행 전문가입니다. 
주어진 날짜에 한국에서 가장 추천할 만한 도시를 선택하고, 그 이유를 설명해주세요.

여행 날짜: {date_str}

다음 JSON 형식으로 응답하세요:
{{
    "recommended_city": "도시명",
    "weather": "날씨 설명",
    "events": ["행사1", "행사2", "행사3"],
    "reason": "추천 이유"
}}

JSON만 응답하세요."""
    
    response = call_llm(prompt)
    
    # JSON 추출 (마크다운 코드블록 제거)
    response = response.strip()
    if response.startswith("```"):
        response = response.split("```")[1]
        if response.startswith("json"):
            response = response[4:]
    response = response.strip()
    
    try:
        result = json.loads(response)
        return result
    except json.JSONDecodeError:
        raise ValueError(f"LLM 응답을 JSON으로 파싱할 수 없습니다: {response}")


def search_restaurants(city: str, size: int = 5) -> List[Dict[str, Any]]:
    """
    Kakao Map API를 이용한 맛집 검색
    """
    api_key = os.environ.get("KAKAO_API_KEY")
    if not api_key:
        return []
    
    # 검색 쿼리: "도시명 맛집"
    query = f"{city} 맛집"
    encoded_query = urllib.parse.quote(query)
    
    url = f"https://dapi.kakao.com/v2/local/search/keyword.json?query={encoded_query}&size={size}"
    
    try:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"KakaoAK {api_key}"}
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))
            
            restaurants = []
            if "documents" in response_data:
                for doc in response_data["documents"]:
                    restaurant = {
                        "name": doc.get("place_name", ""),
                        "address": doc.get("address_name", ""),
                        "category": doc.get("category_name", ""),
                        "url": doc.get("place_url", ""),
                        "x": doc.get("x", ""),
                        "y": doc.get("y", "")
                    }
                    restaurants.append(restaurant)
            
            return restaurants
    
    except urllib.error.URLError as e:
        print(f"⚠️  맛집 검색 실패: {e}")
        return []


def generate_report(date_str: str, rec: Dict[str, Any], foods: List[Dict[str, Any]]) -> str:
    """
    LLM을 이용한 최종 여행 리포트 생성 (Markdown 형식)
    """
    # 맛집 정보를 텍스트로 변환
    restaurants_text = "\n".join([
        f"- {f['name']} ({f['category']}): {f['address']}"
        for f in foods
    ])
    
    if not restaurants_text:
        restaurants_text = "- 검색 결과 없음"
    
    prompt = f"""당신은 한국 여행 가이드입니다.
다음 정보를 바탕으로 매력적인 여행 리포트를 Markdown 형식으로 작성해주세요.

여행 날짜: {date_str}
추천 도시: {rec.get('recommended_city', '')}
날씨: {rec.get('weather', '')}
행사: {', '.join(rec.get('events', []))}
추천 이유: {rec.get('reason', '')}

추천 맛집:
{restaurants_text}

Markdown 형식의 리포트를 작성하세요. 제목, 소제목, 본문, 맛집 정보 등을 포함하세요.
Markdown만 응답하세요."""
    
    report = call_llm(prompt)
    return report.strip()


def main():
    """메인 실행 함수"""
    try:
        # 1. 초기화 및 인자 파싱
        date_str = load_args_and_init()
        print(f"✅ 여행 날짜: {date_str}")
        
        # 2. LLM으로 도시/날씨/행사 추천
        print("🤖 LLM에서 추천 도시를 검색 중...")
        recommendation = recommend_city(date_str)
        print(f"✅ 추천 도시: {recommendation['recommended_city']}")
        
        # 3. Kakao Map에서 맛집 검색
        print("🗺️  맛집을 검색 중...")
        restaurants = search_restaurants(recommendation['recommended_city'])
        print(f"✅ 맛집 {len(restaurants)}곳 검색 완료")
        
        # 4. LLM으로 최종 리포트 생성
        print("📝 최종 리포트를 생성 중...")
        report = generate_report(date_str, recommendation, restaurants)
        
        # 5. 결과 저장
        results_dir = Path("results")
        
        # Markdown 리포트 저장
        report_path = results_dir / f"report_{date_str}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        # 원본 데이터 (JSON) 저장
        data = {
            "date": date_str,
            "recommendation": recommendation,
            "restaurants": restaurants
        }
        data_path = results_dir / f"data_{date_str}.json"
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 리포트 저장 완료:")
        print(f"   - {report_path}")
        print(f"   - {data_path}")
        
        # 6. 결과 출력
        print("\n" + "="*60)
        print(report)
        print("="*60)
    
    except KeyboardInterrupt:
        print("\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
