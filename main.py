import os
import json
from datetime import date, datetime, timedelta
from garminconnect import Garmin
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

GARMIN_EMAIL = os.environ.get("GARMIN_EMAIL")
GARMIN_PASSWORD = os.environ.get("GARMIN_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")

SCOPES = ['https://www.googleapis.com/auth/calendar.events']

def get_calendar_service():
    info = json.loads(GOOGLE_CREDENTIALS)
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
    return build('calendar', 'v3', credentials=creds)

def fetch_today_running():
    try:
        client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        client.login()
    except Exception as e:
        print(f"가민 로그인 실패: {e}")
        return None, None

    # 최근 활동 5건 조회
    activities = client.get_activities(0, 5)
    
    running_list = [
        act for act in activities 
        if act.get("activityType", {}).get("typeKey") == "running"
    ]
    
    if not running_list:
        print("최근 러닝 데이터가 없습니다.")
        return None, None
    
    # 가장 최근 러닝 1건 선택
    target_act = running_list[0]
    activity_id = target_act["activityId"]
    splits = client.get_activity_splits(activity_id)
    return target_act, splits

def analyze_with_gemini(activity, splits):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.configure(api_key=GEMINI_API_KEY)
    
    # 내 계정에서 사용 가능한 최신 모델 자동 선택
    available_models = genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-3.8-flash")

    distance_km = round(activity.get("distance", 0) / 1000, 2)
    duration_sec = activity.get("duration", 0)
    avg_pace_sec = duration_sec / distance_km if distance_km > 0 else 0
    avg_pace = f"{int(avg_pace_sec // 60)}:{int(avg_pace_sec % 60):02d}/km"
    
    lap_summaries = []
    lap_list = splits.get("lapDTOs", []) if splits else []
    for idx, lap in enumerate(lap_list):
        lap_dist = round(lap.get("distance", 0) / 1000, 2)
        lap_dur = lap.get("duration", 0)
        l_pace_sec = lap_dur / lap_dist if lap_dist > 0 else 0
        l_pace = f"{int(l_pace_sec // 60)}:{int(l_pace_sec % 60):02d}"
        lap_summaries.append({
            "구간": f"{idx+1}km",
            "페이스": l_pace,
            "평균심박": lap.get("averageHR", "-"),
            "케이던스": lap.get("averageRunCadence", "-")
        })

    summary_data = {
        "총거리(km)": distance_km,
        "평균페이스": avg_pace,
        "평균심박": activity.get("averageHR", "-"),
        "최대심박": activity.get("maxHR", "-"),
        "평균케이던스": activity.get("averageRunningCadenceInStepsPerMinute", "-"),
        "수직진폭(mm)": activity.get("avgVerticalOscillation", "-"),
        "랩별데이터": lap_summaries
    }

    prompt = f"""
당신은 엘리트 러닝 코치입니다. 아래 오늘 가민 러닝 로그(랩별 데이터 포함)를 분석해 주세요.

[러닝 데이터]
{json.dumps(summary_data, ensure_ascii=False, indent=2)}

[요구사항]
1. 훈련 성격 분류 (조깅, 템포런, 빌드업, 인터벌 등)
2. 랩별 페이스 및 심박 밸런스 분석 (초반 대비 후반 페이스/심박 드리프트 여부)
3. 케이던스 및 러닝 역학 효율 평가
4. 코칭 처방 3줄 요약 (잘된 점, 보완할 점, 내일 추천 운동)

명확하고 전문적인 개조식 어조로 작성해 주세요.
"""
    response = model.generate_content(prompt)
    return summary_data, response.text

def register_to_calendar(service, activity, summary_data, report_text):
    activity_id = str(activity["activityId"])
    start_time_str = activity.get("startTimeLocal")
    start_dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
    end_dt = start_dt + timedelta(seconds=int(activity.get("duration", 1800)))

    # 중복 체크
    time_min = start_dt.replace(hour=0, minute=0, second=0).isoformat() + 'Z'
    time_max = start_dt.replace(hour=23, minute=59, second=59).isoformat() + 'Z'
    events = service.events().list(calendarId='primary', timeMin=time_min, timeMax=time_max).execute()
    
    for ev in events.get('items', []):
        if f"Garmin_ID: {activity_id}" in ev.get('description', ''):
            print(f"이미 등록된 일정입니다 (ID: {activity_id}).")
            return

    title = f"🏃 [러닝] {summary_data['총거리(km)']}km ({summary_data['평균페이스']}) | 심박 {summary_data['평균심박']}bpm"
    desc = f"""[Garmin_ID: {activity_id}]

📊 훈련 요약
- 거리: {summary_data['총거리(km)']} km ({summary_data['평균페이스']})
- 심박: 평균 {summary_data['평균심박']} / 최대 {summary_data['최대심박']} bpm
- 케이던스: {summary_data['평균케이던스']} spm

-------------------------------------------
🤖 Gemini AI 코칭 리포트
-------------------------------------------
{report_text}
"""
    event = {
        'summary': title,
        'description': desc,
        'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Seoul'},
        'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Seoul'},
        'colorId': '10'
    }
    service.events().insert(calendarId='primary', body=event).execute()
    print("캘린더 등록 완료")

if __name__ == "__main__":
    act, splits = fetch_today_running()
    if act:
        summary, analysis = analyze_with_gemini(act, splits)
        service = get_calendar_service()
        register_to_calendar(service, act, summary, analysis)
