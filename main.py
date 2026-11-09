import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from garminconnect import Garmin

# 환경변수 로드
GARMIN_EMAIL = os.environ.get("GARMIN_EMAIL")
GARMIN_PASSWORD = os.environ.get("GARMIN_PASSWORD")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")

def send_csv_email(file_name, csv_bytes, activity_date):
    """지메일 SMTP를 통해 본인 메일로 CSV 첨부파일 자동 발송"""
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_USER  # 나에게 보내기
    msg['Subject'] = f"🏃 [가민 데이터] {activity_date} 러닝 상세 CSV"

    body_text = f"기록 일시: {activity_date}\n가민 원본 랩/구간 상세 데이터 CSV 파일입니다."
    msg.attach(MIMEText(body_text, 'plain'))

    # CSV 파일 첨부
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(csv_bytes)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{file_name}"')
    msg.attach(part)

    # 지메일 SMTP 전송 (포트 465 SSL)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_USER, EMAIL_USER, msg.as_string())
    
    print(f"✅ 메일 발송 완료: {file_name}")

def main():
    if not all([GARMIN_EMAIL, GARMIN_PASSWORD, EMAIL_USER, EMAIL_APP_PASSWORD]):
        raise ValueError("필수 환경변수가 누락되었습니다. GitHub Secrets 설정을 확인하세요.")

    print("가민 커넥트 로그인 시도 중...")
    client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
    client.login()
    print("가민 로그인 성공.")

    # 가장 최근 활동 1건 조회
    activities = client.get_activities(0, 1)
    if not activities:
        print("조회된 활동이 없습니다.")
        return

    activity = activities[0]
    activity_type = activity.get('activityType', {}).get('typeKey', '')
    if 'running' not in activity_type:
        print(f"최근 활동이 러닝이 아닙니다: {activity_type}")
        return

    activity_id = activity.get('activityId')
    start_time_str = activity.get('startTimeLocal') # 예: 2026-11-08 17:43:00

    dt = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
    date_str = dt.strftime("%Y%m%d_%H%M")
    file_name = f"garmin_running_{date_str}.csv"

    print(f"새 러닝 데이터 발견 ({start_time_str}). CSV 다운로드 중...")
    csv_bytes = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.CSV)

    # 본인 지메일로 발송
    send_csv_email(file_name, csv_bytes, start_time_str)
    print("전체 동기화 작업 완료.")

if __name__ == "__main__":
    main()
