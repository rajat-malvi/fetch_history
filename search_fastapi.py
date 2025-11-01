"""
Education Counselor Platform - Browser History Service
Step 1: Students download their own browser history
Step 2: Upload it for counseling context
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import shutil
import sqlite3
import csv
import os
import uuid
import platform
from urllib.parse import urlparse, parse_qs
import io
import zipfile

app = FastAPI(
    title="Education Counselor Browser History Service",
    description="Download your browser history, then upload for counseling",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage
TEMP_DIR = Path("./temp_history_data")
TEMP_DIR.mkdir(exist_ok=True)

SESSIONS = {}


def get_browser_paths():
    """Get browser history paths based on OS."""
    system = platform.system()
    home = Path.home()
    
    paths = {}
    
    if system == 'Linux':
        paths = {
            'Chrome': home / '.config/google-chrome/Default/History',
            'Chromium': home / '.config/chromium/Default/History',
            'Brave': home / '.config/BraveSoftware/Brave-Browser/Default/History',
            'Edge': home / '.config/microsoft-edge/Default/History',
            'Firefox': home / '.mozilla/firefox'
        }
    elif system == 'Darwin':  # macOS
        paths = {
            'Chrome': home / 'Library/Application Support/Google/Chrome/Default/History',
            'Chromium': home / 'Library/Application Support/Chromium/Default/History',
            'Brave': home / 'Library/Application Support/BraveSoftware/Brave-Browser/Default/History',
            'Edge': home / 'Library/Application Support/Microsoft Edge/Default/History',
            'Firefox': home / 'Library/Application Support/Firefox/Profiles'
        }
    elif system == 'Windows':
        appdata = Path(os.getenv('LOCALAPPDATA', ''))
        appdata_roaming = Path(os.getenv('APPDATA', ''))
        paths = {
            'Chrome': appdata / 'Google/Chrome/User Data/Default/History',
            'Chromium': appdata / 'Chromium/User Data/Default/History',
            'Brave': appdata / 'BraveSoftware/Brave-Browser/User Data/Default/History',
            'Edge': appdata / 'Microsoft/Edge/User Data/Default/History',
            'Firefox': appdata_roaming / 'Mozilla/Firefox/Profiles'
        }
    
    return paths


def find_firefox_db():
    """Find Firefox places.sqlite."""
    paths = get_browser_paths()
    if 'Firefox' not in paths:
        return None
    
    firefox_dir = paths['Firefox']
    if not firefox_dir.exists():
        return None
    
    for profile_dir in firefox_dir.iterdir():
        if profile_dir.is_dir() and 'default' in profile_dir.name.lower():
            places_db = profile_dir / 'places.sqlite'
            if places_db.exists():
                return places_db
    return None


def chromium_timestamp_to_iso(timestamp: int) -> str:
    """Convert Chromium timestamp to ISO 8601."""
    if timestamp == 0:
        return ''
    try:
        unix_timestamp = (timestamp - 11644473600000000) / 1000000
        dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
        return dt.isoformat()
    except (ValueError, OSError):
        return ''


def firefox_timestamp_to_iso(timestamp: int) -> str:
    """Convert Firefox timestamp to ISO 8601."""
    if timestamp == 0:
        return ''
    try:
        if timestamp > 10000000000000000:
            unix_timestamp = timestamp / 1000000
        elif timestamp > 10000000000:
            unix_timestamp = timestamp / 1000
        else:
            unix_timestamp = timestamp
        dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
        return dt.isoformat()
    except (ValueError, OSError):
        return ''


def is_search_url(url: str) -> bool:
    """Check if URL is a search engine query."""
    try:
        parsed = urlparse(url.lower())
        domain = parsed.netloc.replace('www.', '')
        if 'google' in domain and ('/search' in parsed.path or 'tbm=' in parsed.query):
            return 'q=' in parsed.query or 'query=' in parsed.query
        if 'bing.com' in domain and '/search' in parsed.path:
            return 'q=' in parsed.query
        if 'duckduckgo.com' in domain:
            return 'q=' in parsed.query
        if 'yahoo.com' in domain and '/search' in parsed.path:
            return 'p=' in parsed.query
        return False
    except:
        return False


def extract_search_query(url: str) -> str:
    """Extract search query from URL."""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        for param in ['q', 'p', 'query']:
            if param in params and params[param]:
                return params[param][0]
        return ''
    except:
        return ''


def is_educational_domain(url: str) -> bool:
    """Check if domain is educational."""
    educational_keywords = [
        'edu', 'coursera', 'udemy', 'khan', 'edx', 'youtube.com/watch',
        'stackoverflow', 'github', 'medium', 'wikipedia', 'scholar',
        'arxiv', 'researchgate', 'quora', 'reddit.com/r/learn',
        'tutorial', 'learn', 'course', 'lecture', 'study'
    ]
    url_lower = url.lower()
    return any(keyword in url_lower for keyword in educational_keywords)


def export_chromium_to_csv(db_path: Path, days_back: int = 7) -> str:
    """Export Chromium history to CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['URL', 'Title', 'Visit Count', 'Last Visit Time', 'Search Query', 'Is Educational'])
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        unix_ts = cutoff_date.timestamp()
        chromium_ts = int((unix_ts + 11644473600) * 1000000)
        
        query = """
            SELECT url, title, visit_count, last_visit_time 
            FROM urls 
            WHERE last_visit_time >= ?
            ORDER BY last_visit_time DESC
        """
        
        cursor.execute(query, (chromium_ts,))
        
        for row in cursor.fetchall():
            url, title, visit_count, last_visit_time = row
            search_query = extract_search_query(url) if is_search_url(url) else ''
            is_edu = is_educational_domain(url)
            
            writer.writerow([
                url,
                title or '',
                visit_count or 0,
                chromium_timestamp_to_iso(last_visit_time),
                search_query,
                is_edu
            ])
        
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading database: {str(e)}")
    
    return output.getvalue()


def export_firefox_to_csv(db_path: Path, days_back: int = 7) -> str:
    """Export Firefox history to CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['URL', 'Title', 'Visit Count', 'Last Visit Time', 'Search Query', 'Is Educational'])
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        firefox_ts = int(cutoff_date.timestamp() * 1000000)
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='moz_historyvisits'")
        has_history_visits = cursor.fetchone() is not None
        
        if has_history_visits:
            query = """
                SELECT DISTINCT p.url, p.title, p.visit_count, 
                       MAX(h.visit_date) as last_visit_date
                FROM moz_places p
                LEFT JOIN moz_historyvisits h ON p.id = h.place_id
                WHERE p.url IS NOT NULL AND h.visit_date >= ?
                GROUP BY p.id
                ORDER BY last_visit_date DESC
            """
        else:
            query = """
                SELECT url, title, visit_count, last_visit_date
                FROM moz_places
                WHERE url IS NOT NULL AND last_visit_date >= ?
                ORDER BY last_visit_date DESC
            """
        
        cursor.execute(query, (firefox_ts,))
        
        for row in cursor.fetchall():
            url, title, visit_count, last_visit_date = row
            search_query = extract_search_query(url) if is_search_url(url) else ''
            is_edu = is_educational_domain(url)
            
            writer.writerow([
                url,
                title or '',
                visit_count or 0,
                firefox_timestamp_to_iso(last_visit_date) if last_visit_date else '',
                search_query,
                is_edu
            ])
        
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading Firefox database: {str(e)}")
    
    return output.getvalue()


def categorize_interests(rows: List[dict]) -> dict:
    """Categorize student interests."""
    categories = {
        'programming': ['python', 'java', 'javascript', 'coding', 'programming', 'algorithm'],
        'data_science': ['data science', 'machine learning', 'ai', 'deep learning'],
        'web_development': ['html', 'css', 'react', 'angular', 'web development'],
        'mathematics': ['math', 'calculus', 'algebra', 'statistics', 'probability'],
        'science': ['physics', 'chemistry', 'biology', 'science'],
        'business': ['business', 'management', 'marketing', 'finance'],
        'design': ['design', 'ui', 'ux', 'graphic'],
        'career': ['job', 'career', 'interview', 'resume', 'salary'],
        'exam_prep': ['exam', 'test', 'preparation', 'gate', 'jee', 'neet']
    }
    
    interest_counts = {cat: 0 for cat in categories}
    
    all_text = ' '.join([
        row.get('URL', '') + ' ' + 
        row.get('Title', '') + ' ' + 
        row.get('Search Query', '')
        for row in rows
    ]).lower()
    
    for category, keywords in categories.items():
        for keyword in keywords:
            interest_counts[category] += all_text.count(keyword)
    
    top_interests = sorted(interest_counts.items(), key=lambda x: x[1], reverse=True)
    return [cat.replace('_', ' ').title() for cat, count in top_interests[:5] if count > 0]


def analyze_csv(csv_content: str) -> dict:
    """Analyze CSV and generate counseling context."""
    rows = []
    reader = csv.DictReader(io.StringIO(csv_content))
    
    for row in reader:
        rows.append(row)
    
    search_queries = [row['Search Query'] for row in rows if row.get('Search Query')]
    educational_visits = [row for row in rows if row.get('Is Educational') == 'True']
    
    educational_domains = []
    for row in educational_visits[:20]:
        try:
            domain = urlparse(row['URL']).netloc.replace('www.', '')
            if domain not in educational_domains:
                educational_domains.append(domain)
        except:
            pass
    
    top_interests = categorize_interests(rows)
    
    return {
        'total_visits': len(rows),
        'search_queries_count': len(search_queries),
        'educational_visits': len(educational_visits),
        'search_queries': search_queries[:20],
        'educational_domains': educational_domains[:10],
        'top_interests': top_interests,
        'study_topics': list(set(search_queries[:15]))
    }


@app.get("/")
async def root():
    """API documentation."""
    return {
        "service": "Education Counselor Browser History Service",
        "version": "2.0.0",
        "workflow": {
            "step_1": "Download your browser history: GET /download/my-history",
            "step_2": "Upload for counseling: POST /upload/for-counseling"
        },
        "endpoints": {
            "/download/my-history": "Download your own browser history as CSV",
            "/upload/for-counseling": "Upload history CSV for counseling context",
            "/context/{session_id}": "Get counseling context for a session"
        }
    }


@app.get("/download/my-history")
async def download_my_history(
    days_back: int = 7,
    browser: Optional[str] = None
):
    """
    Download your own browser history as CSV.
    This endpoint reads your local browser database and returns CSV.
    
    Query params:
    - days_back: Number of days to export (default: 7)
    - browser: chrome, firefox, brave, edge (optional, auto-detects if not specified)
    """
    
    browser_paths = get_browser_paths()
    
    # Try to find browser automatically
    csv_content = None
    detected_browser = None
    
    if browser:
        browser = browser.lower()
        if browser == 'firefox':
            firefox_db = find_firefox_db()
            if firefox_db and firefox_db.exists():
                with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
                    shutil.copy2(firefox_db, tmp.name)
                    tmp_path = Path(tmp.name)
                
                try:
                    csv_content = export_firefox_to_csv(tmp_path, days_back)
                    detected_browser = 'Firefox'
                finally:
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
        else:
            # Chromium-based
            browser_map = {
                'chrome': 'Chrome',
                'chromium': 'Chromium',
                'brave': 'Brave',
                'edge': 'Edge'
            }
            browser_key = browser_map.get(browser)
            
            if browser_key and browser_key in browser_paths:
                db_path = browser_paths[browser_key]
                if db_path.exists():
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
                        shutil.copy2(db_path, tmp.name)
                        tmp_path = Path(tmp.name)
                    
                    try:
                        csv_content = export_chromium_to_csv(tmp_path, days_back)
                        detected_browser = browser_key
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except:
                            pass
    else:
        # Auto-detect browser
        for browser_name, db_path in browser_paths.items():
            if browser_name == 'Firefox':
                firefox_db = find_firefox_db()
                if firefox_db and firefox_db.exists():
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
                        shutil.copy2(firefox_db, tmp.name)
                        tmp_path = Path(tmp.name)
                    
                    try:
                        csv_content = export_firefox_to_csv(tmp_path, days_back)
                        detected_browser = 'Firefox'
                        break
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except:
                            pass
            elif db_path.exists():
                with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
                    shutil.copy2(db_path, tmp.name)
                    tmp_path = Path(tmp.name)
                
                try:
                    csv_content = export_chromium_to_csv(tmp_path, days_back)
                    detected_browser = browser_name
                    break
                finally:
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
    
    if not csv_content:
        raise HTTPException(
            status_code=404, 
            detail="No browser history found. Make sure your browser is installed and has browsing history."
        )
    
    # Return as downloadable CSV
    filename = f"my_browser_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Detected-Browser": detected_browser
        }
    )


@app.post("/upload/for-counseling")
async def upload_for_counseling(
    student_id: str = Form(...),
    history_file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    Upload your browser history CSV for counseling context.
    
    Form data:
    - student_id: Your student ID or email
    - history_file: The CSV file downloaded from /download/my-history
    """
    
    # Read uploaded CSV
    content = await history_file.read()
    csv_content = content.decode('utf-8')
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    
    
    # Save CSV to temp folder
    csv_filename = f"{session_id}_{student_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = TEMP_DIR / csv_filename
    
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write(csv_content)
    
    # Analyze CSV
    try:
        context = analyze_csv(csv_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error analyzing CSV: {str(e)}")
    
    # Store session
    SESSIONS[session_id] = {
        'student_id': student_id,
        'csv_path': str(csv_path),
        'created_at': datetime.now().isoformat(),
        'context': context
    }
    
    # Cleanup old files
    if background_tasks:
        background_tasks.add_task(cleanup_old_files)
    
    return {
        'status': 'success',
        'session_id': session_id,
        'student_id': student_id,
        'counseling_context': context,
        'message': 'History uploaded successfully. Share this session_id with your counselor.'
    }


@app.get("/context/{session_id}")
async def get_counseling_context(session_id: str):
    """
    Get counseling context for a session.
    Counselors use this endpoint to understand student's interests.
    """
    
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    session = SESSIONS[session_id]
    
    return {
        'session_id': session_id,
        'student_id': session['student_id'],
        'created_at': session['created_at'],
        'context': session['context']
    }


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete session data for privacy."""
    
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = SESSIONS[session_id]
    
    # Delete CSV
    try:
        csv_path = Path(session['csv_path'])
        if csv_path.exists():
            csv_path.unlink()
    except Exception as e:
        print(f"Error deleting CSV: {e}")
    
    del SESSIONS[session_id]
    
    return {'status': 'deleted', 'session_id': session_id}


def cleanup_old_files():
    """Remove files older than 24 hours."""
    try:
        now = datetime.now()
        for file in TEMP_DIR.glob("*.csv"):
            file_time = datetime.fromtimestamp(file.stat().st_mtime)
            if (now - file_time).days >= 1:
                file.unlink()
    except Exception as e:
        print(f"Cleanup error: {e}")


@app.get("/health")
async def health_check():
    """Health check."""
    return {
        "status": "healthy",
        "sessions": len(SESSIONS),
        "temp_files": len(list(TEMP_DIR.glob("*.csv")))
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)