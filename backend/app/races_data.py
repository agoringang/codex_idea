from datetime import datetime, timedelta

# Generate race data dynamically based on the current time
now = datetime.now()

# Helper to format date and time
def d(days_offset=0):
    return (now + timedelta(days=days_offset)).strftime("%Y-%m-%d")

def t(minutes_offset=0):
    return (now + timedelta(minutes=minutes_offset)).strftime("%H:%M")

races = [
    # A race that just finished
    {
        "id": "tokyo-finished-1",
        "date": d(), "day": "日", "venue": "東京", "raceNo": "1R",
        "title": "終了直後のレース", "grade": None, "course": "ダート 1400m",
        "start": t(-5),  # Started 5 minutes ago
        "status": "prediction-ready",  # Will be updated to 'finished' by the background job
        "meeting": "第2回東京5日目", "officialNote": "JRA公式発表の出馬表を元にしています。",
        "runners": [
            {"number": 1, "name": "フィニッシャー", "jockey": "横山琉", "gate": "1", "odds": 12.5, "rating": 88, "tags": ["先行"]},
            {"number": 2, "name": "ラストラン", "jockey": "木幡初", "gate": "2", "odds": 8.2, "rating": 92, "tags": ["差し"]},
        ],
    },
    # A race that is about to start
    {
        "id": "kyoto-upcoming-11",
        "date": d(), "day": "日", "venue": "京都", "raceNo": "11R",
        "title": "まもなく開始のレース", "grade": "G1", "course": "芝 3200m",
        "start": t(10),  # Starts in 10 minutes
        "status": "prediction-ready",
        "meeting": "第3回京都4日目", "officialNote": "JRA公式発表の出馬表を元にしています。",
        "runners": [
            {"number": 4, "name": "アップカマー", "jockey": "戸崎圭", "gate": "4", "odds": 2.1, "rating": 115, "tags": ["期待の新星"]},
            {"number": 5, "name": "イレギュラー", "jockey": "菱田", "gate": "5", "odds": 3.9, "rating": 112, "tags": ["調子上向き"]},
        ],
    },
    # A race whose card is available but prediction is not yet ready
    {
        "id": "hakodate-card-ready-8",
        "date": d(), "day": "日", "venue": "函館", "raceNo": "8R",
        "title": "出馬表のみのレース", "grade": None, "course": "芝 2000m",
        "start": t(45),  # Starts in 45 minutes
        "status": "racecard-available", # Will become 'prediction-ready' 30 mins before start
        "meeting": "第1回函館2日目", "officialNote": "JRA公式発表の出馬表を元にしています。",
        "runners": [
            {"number": 1, "name": "カードマン", "jockey": "幸", "gate": "1", "odds": 5.0, "rating": 100, "tags": []},
            {"number": 2, "name": "レイター", "jockey": "武豊", "gate": "2", "odds": 3.1, "rating": 102, "tags": []},
        ],
    },
    # A race that is scheduled for much later
    {
        "id": "kyoto-scheduled-12",
        "date": d(), "day": "日", "venue": "京都", "raceNo": "12R",
        "title": "まだ先のレース", "grade": None, "course": "ダート 1200m",
        "start": t(120), # Starts in 2 hours
        "status": "schedule-only",
        "meeting": "第3回京都4日目", "officialNote": "JRA公式発表の出馬表を元にしています。",
        "runners": [],
    },
]