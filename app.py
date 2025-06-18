import os
import tempfile
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import sqlite3
import openai
import pdfplumber
import docx
import logging
import uuid
import re
import google.generativeai as genai
from typing import Dict, List, Tuple, Optional, Any

app = Flask(__name__)
CORS(app) 

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 
app.config['DATABASE'] = 'cv_scanner.db'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'docx', 'doc'}

# uploads folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ai API key
# openai.api_key = os.environ.get('OPENAI_API_KEY', 'your-api-key')
genai.configure(api_key=os.getenv("GEMINI_API_KEY", "your-api-key"))

# Database setup
def init_db():
    """Initialize the SQLite database with required tables."""
    with sqlite3.connect(app.config['DATABASE']) as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # CVs table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS cvs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        
        # Job descriptions table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        
        # Analysis results table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            cv_id INTEGER,
            job_description_id INTEGER,
            score REAL,
            feedback TEXT,
            suggestions TEXT,
            improved_cv TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (cv_id) REFERENCES cvs (id),
            FOREIGN KEY (job_description_id) REFERENCES job_descriptions (id)
        )
        ''')
        
        conn.commit()

# Initialize database on startup
with app.app_context():
    init_db()

def allowed_file(filename: str) -> bool:
    """Check if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file."""
    try:
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        return ""

def extract_text_from_docx(file_path: str) -> str:
    """Extract text from a DOCX file."""
    try:
        doc = docx.Document(file_path)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])
    except Exception as e:
        logger.error(f"Error extracting text from DOCX: {str(e)}")
        return ""

def extract_text_from_file(file_path: str) -> str:
    """Extract text from different file types."""
    file_extension = file_path.split('.')[-1].lower()
    
    if file_extension == 'pdf':
        return extract_text_from_pdf(file_path)
    elif file_extension in ['docx', 'doc']:
        return extract_text_from_docx(file_path)
    else:
        return ""


# analyze with openai
# def analyze_cv_with_openai(cv_text: str, job_description: str) -> Dict[str, Any]:
#     """
#     Analyze the CV against a job description using OpenAI API.
#     Returns a dictionary with score, feedback, suggestions, and improved CV.
#     """
#     try:
#         prompt = f"""
#         You are an expert CV/resume analyzer and job application specialist. Your task is to provide detailed analysis on how well a CV matches a job description.
        
#         JOB DESCRIPTION:
#         {job_description}
        
#         CV CONTENT:
#         {cv_text}
        
#         Please provide the following in a JSON format:
#         1. A match score from 0 to 100 representing how well the CV matches the job requirements.
#         2. Detailed feedback on the CV's strengths and weaknesses relative to the job description.
#         3. Specific suggestions for improvement, including:
#            - Skills or experiences to highlight
#            - Sections to add or modify
#            - Keywords to include
#            - Formatting recommendations
#         4. A revised version of the CV that better matches the job description.
        
#         Format your response as a valid JSON object with the following keys:
#         - "score": (number)
#         - "feedback": (string with detailed analysis)
#         - "suggestions": (array of specific improvement points)
#         - "improved_cv": (string with the revised CV text)
#         """
        
#         response = openai.ChatCompletion.create(
#             model="gpt-4o",  # Use appropriate model
#             messages=[
#                 {"role": "system", "content": "You are a CV analysis specialist. Respond only with the requested JSON format."},
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.2,
#             max_tokens=4000
#         )
        
#         # Extract and parse the JSON response
#         content = response.choices[0].message.content.strip()
#         # Sometimes the API might wrap the JSON in ```json ``` blocks, so we need to extract it
#         if "```json" in content:
#             content = re.search(r'```json\s*([\s\S]*?)\s*```', content).group(1)
#         elif "```" in content:
#             content = re.search(r'```\s*([\s\S]*?)\s*```', content).group(1)
            
#         result = json.loads(content)
        
#         # Ensure all required fields are present
#         required_fields = ["score", "feedback", "suggestions", "improved_cv"]
#         for field in required_fields:
#             if field not in result:
#                 result[field] = "" if field != "suggestions" else []
        
#         return result
    
#     except Exception as e:
#         logger.error(f"Error in OpenAI analysis: {str(e)}")
#         # Return a default structure in case of error
#         return {
#             "score": 0,
#             "feedback": f"An error occurred during analysis: {str(e)}",
#             "suggestions": ["Unable to provide suggestions due to an error."],
#             "improved_cv": cv_text  # Return original CV
#         }


# analyze with gemini
def analyze_cv_with_gemini(cv_text: str, job_description: str) -> Dict[str, Any]:
    """
    Analyze the CV against a job description using Gemini API.
    Returns a dictionary with score, feedback, suggestions, and improved CV.
    """
    try:
        prompt = f"""
        You are an expert CV/resume analyzer and job application specialist. Your task is to provide detailed analysis on how well a CV matches a job description.

        JOB DESCRIPTION:
        {job_description}

        CV CONTENT:
        {cv_text}

        Please provide the following in a JSON format:
        1. A match score from 0 to 100 representing how well the CV matches the job requirements.
        2. Detailed feedback on the CV's strengths and weaknesses relative to the job description.
        3. Specific suggestions for improvement, including:
        - Skills or experiences to highlight
        - Sections to add or modify
        - Keywords to include
        - Formatting recommendations
        4. A revised version of the CV that better matches the job description.

        Format your response as a valid JSON object with the following keys:
        - "score": (number)
        - "feedback": (string with detailed analysis)
        - "suggestions": (array of specific improvement points)
        - "improved_cv": (string with the revised CV text)
        """

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        content = response.text.strip()

        # Clean response if wrapped in code block
        if "```json" in content:
            content = re.search(r'```json\s*([\s\S]*?)\s*```', content).group(1)
        elif "```" in content:
            content = re.search(r'```\s*([\s\S]*?)\s*```', content).group(1)

        result = json.loads(content)

        # Ensure all required fields are present
        required_fields = ["score", "feedback", "suggestions", "improved_cv"]
        for field in required_fields:
            if field not in result:
                result[field] = "" if field != "suggestions" else []

        return result

    except Exception as e:
        logger.error(f"Error in Gemini analysis: {str(e)}")
        return {
            "score": 0,
            "feedback": f"An error occurred during analysis: {str(e)}",
            "suggestions": ["Unable to provide suggestions due to an error."],
            "improved_cv": cv_text
        }


def save_analysis_result(user_id: int, cv_id: int, job_description_id: int, result: Dict[str, Any]) -> int:
    """Save analysis result to database and return the result ID."""
    try:
        with sqlite3.connect(app.config['DATABASE']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO analysis_results 
            (user_id, cv_id, job_description_id, score, feedback, suggestions, improved_cv, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (
                user_id,
                cv_id,
                job_description_id,
                result.get('score', 0),
                result.get('feedback', ''),
                json.dumps(result.get('suggestions', [])),
                result.get('improved_cv', ''),
            ))
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Error saving analysis result: {str(e)}")
        return -1

# Routes
@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "version": "1.0.0"})

# @app.route('/api/upload-cv', methods=['POST'])
# def upload_cv():
    """
    Endpoint to upload and store a CV file.
    Requires: file in request.files['cv']
    Optional: user_id in request.form
    """
    if 'cv' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['cv']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": f"File type not allowed. Supported types: {', '.join(app.config['ALLOWED_EXTENSIONS'])}"}), 400
    
    try:
        # Get user ID from request or use anonymous user (0)
        user_id = request.form.get('user_id', 0)
        logger.info(user_id + "263")
        # Generate a unique filename to avoid collisions
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower()
        logger.info(file_extension)
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save the file
        file.save(file_path)
        
        # Extract text from the file
        try:
            cv_text = extract_text_from_file(file_path)
        except Exception as e:
            logger.info(f"Text extraction failed: {e}")
            return jsonify({"error": "Text extraction failed"}), 500
        logger.info("extracted")
        # Save to database
        with sqlite3.connect(app.config['DATABASE']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO cvs (user_id, file_name, file_path, content, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ''', (user_id, original_filename, file_path, cv_text))
            conn.commit()
            cv_id = cursor.lastrowid
            logger.info("saved to db")
            logger.info(cv_id)
            logger.info(original_filename)
            logger.info(file_path)
            logger.info("returning")
            return jsonify({
                "success": True,
                "cv_id": cv_id,
                "filename": original_filename,
                "file_path": file_path,
                "content_preview": "..."
            })
        # cv_text[:200] + "..." if len(cv_text) > 200 else cv_text
    except Exception as e:
        logger.info(f"Error in upload_cv: {str(e)}")
        logger.error(f"Error in upload_cv: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/upload-cv', methods=['POST'])
def upload_cv():
    try:
        file = request.files['cv']
        user_id = request.form.get('user_id', 0)
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)

        logger.info("File saved")

        try:
            cv_text = extract_text_from_file(file_path)
            logger.info("Text extracted")
        except Exception as e:
            logger.error(f"Text extraction error: {e}")
            return jsonify({"error": "Text extraction failed"}), 500

        try:
            with sqlite3.connect(app.config['DATABASE']) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO cvs (user_id, file_name, file_path, content, created_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                ''', (user_id, original_filename, file_path, cv_text))
                conn.commit()
                cv_id = cursor.lastrowid
        except Exception as e:
            logger.error(f"Database error: {e}")
            return jsonify({"error": "Database insertion failed"}), 500

        try:
            preview = cv_text[:200] + "..." if len(cv_text) > 200 else cv_text
            preview = preview.encode("utf-8", "ignore").decode("utf-8")
            logger.info(preview)
        except Exception as e:
            logger.warning(f"Preview error: {e}")
            preview = "[Preview not available]"
        return jsonify({"success": True, "message": "Upload OK"})
        return jsonify({
            "success": True,
            "cv_id": cv_id,
            "filename": original_filename,
            "file_path": file_path,
            "content_preview": preview
        })

    except Exception as e:
        logger.error(f"Unhandled error in upload_cv: {e}")
        return jsonify({"error": "Unhandled server error"}), 500


@app.route('/api/job-description', methods=['POST'])
def save_job_description():
    """
    Endpoint to save a job description.
    Requires: title and content in request JSON
    Optional: user_id in request JSON
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        title = data.get('title')
        content = data.get('content')
        user_id = data.get('user_id', 0) 
        
        if not title or not content:
            return jsonify({"error": "Title and content are required"}), 400
        
        with sqlite3.connect(app.config['DATABASE']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO job_descriptions (user_id, title, content, created_at)
            VALUES (?, ?, ?, datetime('now'))
            ''', (user_id, title, content))
            conn.commit()
            job_id = cursor.lastrowid
        
        return jsonify({
            "success": True,
            "job_description_id": job_id,
            "title": title
        })
    
    except Exception as e:
        logger.error(f"Error in save_job_description: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze_cv():
    """
    Endpoint to analyze a CV against a job description.
    Requires: cv_id and job_description_id in request JSON
    Optional: user_id in request JSON
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        cv_id = data.get('cv_id')
        job_description_id = data.get('job_description_id')
        user_id = data.get('user_id', 0)
        
        if not cv_id or not job_description_id:
            return jsonify({"error": "CV ID and Job Description ID are required"}), 400
        
        with sqlite3.connect(app.config['DATABASE']) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT content FROM cvs WHERE id = ?', (cv_id,))
            cv_row = cursor.fetchone()
            if not cv_row:
                return jsonify({"error": "CV not found"}), 404
            cv_text = cv_row['content']
            
            cursor.execute('SELECT content FROM job_descriptions WHERE id = ?', (job_description_id,))
            job_row = cursor.fetchone()
            if not job_row:
                return jsonify({"error": "Job description not found"}), 404
            job_description = job_row['content']
        
        analysis_result = analyze_cv_with_gemini(cv_text, job_description)
        
        result_id = save_analysis_result(user_id, cv_id, job_description_id, analysis_result)
        
        return jsonify({
            "success": True,
            "result_id": result_id,
            "analysis": analysis_result
        })
    
    except Exception as e:
        logger.error(f"Error in analyze_cv: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/analysis-history', methods=['GET'])
def get_analysis_history():
    """
    Endpoint to retrieve analysis history for a user.
    Requires: user_id as query parameter
    """
    try:
        user_id = request.args.get('user_id', 0)
        
        with sqlite3.connect(app.config['DATABASE']) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT ar.id, ar.score, ar.created_at, 
                   c.file_name as cv_name, 
                   jd.title as job_title
            FROM analysis_results ar
            JOIN cvs c ON ar.cv_id = c.id
            JOIN job_descriptions jd ON ar.job_description_id = jd.id
            WHERE ar.user_id = ?
            ORDER BY ar.created_at DESC
            ''', (user_id,))
            
            rows = cursor.fetchall()
            results = []
            
            for row in rows:
                results.append({
                    "id": row['id'],
                    "score": row['score'],
                    "cv_name": row['cv_name'],
                    "job_title": row['job_title'],
                    "created_at": row['created_at']
                })
            
            return jsonify({
                "success": True,
                "history": results
            })
    
    except Exception as e:
        logger.error(f"Error in get_analysis_history: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/analysis-result/<int:result_id>', methods=['GET'])
def get_analysis_result(result_id):
    """
    Endpoint to retrieve a specific analysis result.
    Requires: result_id as path parameter
    """
    try:
        with sqlite3.connect(app.config['DATABASE']) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT ar.*, c.file_name as cv_name, c.content as cv_content,
                   jd.title as job_title, jd.content as job_description
            FROM analysis_results ar
            JOIN cvs c ON ar.cv_id = c.id
            JOIN job_descriptions jd ON ar.job_description_id = jd.id
            WHERE ar.id = ?
            ''', (result_id,))
            
            row = cursor.fetchone()
            if not row:
                return jsonify({"error": "Analysis result not found"}), 404
            
            # Parse the suggestions JSON string
            suggestions = json.loads(row['suggestions']) if row['suggestions'] else []
            
            result = {
                "id": row['id'],
                "score": row['score'],
                "feedback": row['feedback'],
                "suggestions": suggestions,
                "improved_cv": row['improved_cv'],
                "cv_name": row['cv_name'],
                "cv_content": row['cv_content'],
                "job_title": row['job_title'],
                "job_description": row['job_description'],
                "created_at": row['created_at']
            }
            
            return jsonify({
                "success": True,
                "result": result
            })
    
    except Exception as e:
        logger.error(f"Error in get_analysis_result: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/register', methods=['POST'])
def register_user():
    """
    Endpoint to register a new user.
    Requires: email and password in request JSON
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        
        password_hash = password 
        
        with sqlite3.connect(app.config['DATABASE']) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                INSERT INTO users (email, password_hash, created_at)
                VALUES (?, ?, datetime('now'))
                ''', (email, password_hash))
                conn.commit()
                user_id = cursor.lastrowid
                
                return jsonify({
                    "success": True,
                    "user_id": user_id,
                    "email": email
                })
            except sqlite3.IntegrityError:
                return jsonify({"error": "Email already registered"}), 409
    
    except Exception as e:
        logger.error(f"Error in register_user: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login_user():
    """
    Endpoint to login a user.
    Requires: email and password in request JSON
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        
        with sqlite3.connect(app.config['DATABASE']) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
            
            if not user or user['password_hash'] != password: 
                return jsonify({"error": "Invalid email or password"}), 401
            
            return jsonify({
                "success": True,
                "user_id": user['id'],
                "email": user['email']
            })
    
    except Exception as e:
        logger.error(f"Error in login_user: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/job-search', methods=['GET'])
def job_search():
    """
    Placeholder for job search functionality.
    In a real implementation, this would integrate with job search APIs or web scraping.
    """
    try:
        query = request.args.get('query', '')
        location = request.args.get('location', '')
        
        # Mock response with sample jobs
        sample_jobs = [
            {
                "id": 1,
                "title": "Software Engineer",
                "company": "TechCorp",
                "location": "Athens, Greece",
                "description": "Looking for a skilled software engineer...",
                "url": "https://example.com/jobs/1"
            },
            {
                "id": 2,
                "title": "Data Scientist",
                "company": "DataWorks",
                "location": "Thessaloniki, Greece",
                "description": "Data scientist position available...",
                "url": "https://example.com/jobs/2"
            },
            {
                "id": 3,
                "title": "Frontend Developer",
                "company": "WebSolutions",
                "location": "Remote",
                "description": "Frontend developer needed for...",
                "url": "https://example.com/jobs/3"
            }
        ]
        
        return jsonify({
            "success": True,
            "jobs": sample_jobs,
            "query": query,
            "location": location
        })
    
    except Exception as e:
        logger.error(f"Error in job_search: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/send-application', methods=['POST'])
def send_application():
    """
    Placeholder for sending a job application.
    In a real implementation, this would send emails or integrate with job application APIs.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        job_id = data.get('job_id')
        cv_id = data.get('cv_id')
        user_id = data.get('user_id')
        cover_letter = data.get('cover_letter', '')
        
        if not job_id or not cv_id:
            return jsonify({"error": "Job ID and CV ID are required"}), 400
        
        
        return jsonify({
            "success": True,
            "message": "Application sent successfully (simulation)",
            "job_id": job_id,
            "cv_id": cv_id
        })
    
    except Exception as e:
        logger.error(f"Error in send_application: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/export-cv/<int:result_id>', methods=['GET'])
def export_improved_cv(result_id):
    """
    Endpoint to export the improved CV as a downloadable file.
    Requires: result_id as path parameter
    """
    try:
        format_type = request.args.get('format', 'txt')
        
        with sqlite3.connect(app.config['DATABASE']) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT ar.improved_cv, c.file_name
            FROM analysis_results ar
            JOIN cvs c ON ar.cv_id = c.id
            WHERE ar.id = ?
            ''', (result_id,))
            
            row = cursor.fetchone()
            if not row:
                return jsonify({"error": "Analysis result not found"}), 404
            
            improved_cv = row['improved_cv']
            original_filename = row['file_name'].rsplit('.', 1)[0]  # Remove extension
            
            temp_dir = tempfile.gettempdir()
            
            if format_type == 'txt':
                file_path = os.path.join(temp_dir, f"{original_filename}_improved.txt")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(improved_cv)
                
                return send_from_directory(
                    directory=temp_dir,
                    path=f"{original_filename}_improved.txt",
                    as_attachment=True,
                    download_name=f"{original_filename}_improved.txt"
                )
            
            return jsonify({"error": f"Export format '{format_type}' not supported yet"}), 400
    
    except Exception as e:
        logger.error(f"Error in export_improved_cv: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/user-cvs', methods=['GET'])
def get_user_cvs():
    """
    Endpoint to retrieve all CVs for a user.
    Requires: user_id as query parameter
    """
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400
        
        with sqlite3.connect(app.config['DATABASE']) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT id, file_name, created_at
            FROM cvs
            WHERE user_id = ?
            ORDER BY created_at DESC
            ''', (user_id,))
            
            rows = cursor.fetchall()
            cvs = []
            
            for row in rows:
                cvs.append({
                    "id": row['id'],
                    "file_name": row['file_name'],
                    "created_at": row['created_at']
                })
            
            return jsonify({
                "success": True,
                "cvs": cvs
            })
    
    except Exception as e:
        logger.error(f"Error in get_user_cvs: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/user-job-descriptions', methods=['GET'])
def get_user_job_descriptions():
    """
    Endpoint to retrieve all job descriptions for a user.
    Requires: user_id as query parameter
    """
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400
        
        with sqlite3.connect(app.config['DATABASE']) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT id, title, created_at
            FROM job_descriptions
            WHERE user_id = ?
            ORDER BY created_at DESC
            ''', (user_id,))
            
            rows = cursor.fetchall()
            job_descriptions = []
            
            for row in rows:
                job_descriptions.append({
                    "id": row['id'],
                    "title": row['title'],
                    "created_at": row['created_at']
                })
            
            return jsonify({
                "success": True,
                "job_descriptions": job_descriptions
            })
    
    except Exception as e:
        logger.error(f"Error in get_user_job_descriptions: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)