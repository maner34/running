import os
import io
import json
from datetime import datetime, timezone, timedelta
from garminconnect import Garmin
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# 환경변수 로드
GARMIN_EMAIL = os.environ.get("GARMIN_EMAIL")
GARMIN_PASSWORD = os.environ.get("GARMIN_PASSWORD")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service():
    """서비스 계정 JSON으로 구글 드라이브 API 서비스 생성"""
    info = json.loads(GOOGLE_CREDENTIALS)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def file_exists_in_folder(service, folder_id, file_name):
    """드라이브 지정 폴더에 이미 동일한 이름의 파일이 있는지 확인 (중복 방지)"""
    query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])
    return len(files) > 0

def upload_csv_to_drive(service, folder_id, file_name, csv_data):
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(io.BytesIO(csv_data), mimetype='text/csv', resumable=False)
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name',
        supportsAllDrives=True
    ).execute()
    print(f"✅ 구글 드라이브 업로드 완료: {uploaded_file.get('name')}")

def main():
    if not all([GARMIN_EMAIL, GARMIN_PASSWORD, GOOGLE_CREDENTIALS, DRIVE_FOLDER_ID]):
        raise ValueError("필수 환경변수가 누락되었습니다. GitHub Secrets 설정을 확인하세요.")

    # 1. 가민 커넥트 로그인
    print("가민 커넥트 로그인 시도 중...")
    client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
    client.login()
    print("가민 로그인 성공.")

    # 2. 최근 활동 목록 조회 (최근 5건)
    activities = client.get_activities(0, 5)
    if not activities:
        print("조회된 활동이 없습니다.")
        return

    # 구글 드라이브 서비스 연결
    drive_service = get_drive_service()

    # 한국 시간 기준 (KST)
    kst = timezone(timedelta(hours=9))

    for activity in activities:
        # 러닝 계열 활동만 필터링 (running, treadmill_running 등)
        activity_type = activity.get('activityType', {}).get('typeKey', '')
        if 'running' not in activity_type:
            continue

        activity_id = activity.get('activityId')
        start_time_str = activity.get('startTimeLocal') # 형식 예: 2026-11-09 18:30:00
        
        # 파일명 생성: garmin_running_YYYYMMDD_HHMM.csv
        dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
        date_str = dt.strftime("%Y%m%d_%H%M")
        file_name = f"garmin_running_{date_str}.csv"

        # 3. 중복 업로드 방지 체크
        if file_exists_in_folder(drive_service, DRIVE_FOLDER_ID, file_name):
            print(f"이미 업로드된 기록입니다: {file_name}")
            continue

        print(f"새 러닝 데이터 발견 ({start_time_str}). CSV 다운로드 중...")
        
        # 4. 가민에서 원본 CSV 다운로드
        csv_bytes = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.CSV)

        # 5. 구글 드라이브 지정 폴더로 업로드
        upload_csv_to_drive(drive_service, DRIVE_FOLDER_ID, file_name, csv_bytes)

    print("전체 동기화 작업 완료.")

if __name__ == "__main__":
    main()
