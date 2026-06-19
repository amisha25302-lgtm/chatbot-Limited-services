import os
import json
import time
import sys
import requests
import re
import jwt
import bcrypt
import mysql.connector
from mysql.connector import pooling
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# Force stdout/stderr to UTF-8 to prevent encoding issues (e.g. UnicodeEncodeError on Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Load env variables
load_dotenv()

# We default to qwen2.5-coder:7b as requested for faster inference
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEBUG_PRINT_CHUNKS = os.getenv("DEBUG_PRINT_CHUNKS", "false").lower() == "true"
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_MANIFEST_PATH = os.path.join(WORKSPACE_DIR, "processed_data", "rag_kb_manifest.json")

# Sarvam AI API Configuration
USE_SARVAM_API = os.getenv("USE_SARVAM_API", "false").lower() == "true"
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_MODEL = os.getenv("SARVAM_MODEL", "sarvam-30b")

app = FastAPI(title="SewaSetu RAG API Server")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory manifest cache
MANIFEST_DATA = None
SERVICES_MAP = {}

DB_POOL = None

def init_db_pool():
    global DB_POOL
    if DB_POOL is None:
        try:
            DB_POOL = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="sewasetu_pool",
                pool_size=10,
                host=os.getenv("DB_HOST", "localhost"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD", "root"),
                database=os.getenv("DB_NAME", "sewasetu_db")
            )
            print("[Database] Connection pool initialized successfully.")
        except Exception as e:
            print(f"[Database] Error initializing connection pool: {e}")

def get_db():
    global DB_POOL
    if DB_POOL is None:
        init_db_pool()
    if DB_POOL:
        return DB_POOL.get_connection()
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "root"),
        database=os.getenv("DB_NAME", "sewasetu_db")
    )

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET", "sewasetu_super_secret_key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

def create_jwt_token(user_id: int, role: str, officer_id: Optional[int] = None) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "officer_id": officer_id,
        "exp": datetime.utcnow() + timedelta(minutes=int(os.getenv("JWT_EXPIRATION_MINUTES", "1440")))
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

# Custom datetime serializer
def serialize_data(val):
    if isinstance(val, list):
        return [serialize_data(v) for v in val]
    if isinstance(val, dict):
        return {k: serialize_data(v) for k, v in val.items()}
    if isinstance(val, (datetime, timedelta)):
        return str(val)
    return val

# Auth schemas
class UserRegister(BaseModel):
    name: str
    phone: str
    email: str
    password: str
    role: str # 'citizen' or 'officer'
    aadhaar_number: str
    address: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

@app.post("/api/auth/register")
def register_user(req: UserRegister):
    if req.role not in ('citizen', 'officer'):
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'citizen' or 'officer'.")
    conn = get_db()
    cursor = conn.cursor()
    try:
        username = req.email.split("@")[0]
        cursor.execute("SELECT user_id FROM users WHERE email = %s OR mobile = %s OR username = %s", 
                       (req.email, req.phone, username))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email, Phone, or Username already registered.")
            
        role_type = "citizen" if req.role == "citizen" else "govt_officer"
        hashed_pwd = hash_password(req.password)
        cursor.execute("""
            INSERT INTO users (username, password, role_type, email, mobile, full_name)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (username, hashed_pwd, role_type, req.email, req.phone, req.name))
        user_id = cursor.lastrowid
        
        if role_type == "citizen":
            cursor.execute("""
                INSERT INTO citizens (user_id, full_name, dob, gender, aadhaar_number, samgra_id, category, annual_income, address_line, pincode)
                VALUES (%s, %s, '1990-01-01', 'male', %s, '123456789', 'general', 150000.00, %s, '492001')
            """, (user_id, req.name, req.aadhaar_number, req.address))
        else:
            cursor.execute("""
                INSERT INTO officers (user_id, dept_id, designation, district_id, employee_code, joining_date)
                VALUES (%s, 1, 'Registrar', 1, %s, '2024-01-01')
            """, (user_id, f"EMP-{user_id}"))
            
        conn.commit()
        return {"message": "Registration successful.", "user_id": user_id}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/auth/login")
def login_user(req: UserLogin):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT user_id, full_name, role_type, password 
            FROM users 
            WHERE email = %s OR username = %s OR mobile = %s
        """, (req.email, req.email, req.email))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
            
        pwd_match = False
        db_pwd = user["password"]
        if db_pwd.startswith("$2b$") or db_pwd.startswith("$2a$"):
            try:
                pwd_match = bcrypt.checkpw(req.password.encode('utf-8'), db_pwd.encode('utf-8'))
            except Exception:
                pass
        else:
            pwd_match = (db_pwd == req.password)
            
        if not pwd_match:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
            
        role_type = user["role_type"]
        mapped_role = "anonymous"
        if role_type == "citizen":
            mapped_role = "citizen"
        elif role_type in ("govt_officer", "admin", "edm"):
            mapped_role = "officer"
            
        officer_id = None
        if mapped_role == "officer":
            cursor.execute("SELECT officer_id FROM officers WHERE user_id = %s LIMIT 1", (user["user_id"],))
            off_row = cursor.fetchone()
            if off_row:
                officer_id = off_row["officer_id"]
                
        token = create_jwt_token(user["user_id"], mapped_role, officer_id)
        return {
            "token": token,
            "user": {
                "user_id": user["user_id"],
                "name": user["full_name"],
                "role": mapped_role,
                "officer_id": officer_id
            }
        }
    finally:
        cursor.close()
        conn.close()

# Helper to look up citizen_id from user_id
def get_citizen_id(user_id: int) -> Optional[int]:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT citizen_id FROM citizens WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()
        conn.close()

# Citizen scope data access
def get_my_applications(user_id: int):
    citizen_id = get_citizen_id(user_id)
    if not citizen_id:
        return []
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT a.application_id, s.service_name, a.status, a.submitted_at, s.sla_days
            FROM applications a
            JOIN services s ON a.service_id = s.service_id
            WHERE a.citizen_id = %s
            ORDER BY a.submitted_at DESC
        """, (citizen_id,))
        apps = cursor.fetchall()
        for app in apps:
            if app.get("submitted_at") and app.get("sla_days") is not None:
                app["sla_deadline"] = app["submitted_at"] + timedelta(days=app["sla_days"])
            else:
                app["sla_deadline"] = None
        return apps
    finally:
        cursor.close()
        conn.close()

def get_application_status(user_id: int, application_id: str):
    citizen_id = get_citizen_id(user_id)
    if not citizen_id:
        return {"error": "Citizen profile not found."}
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT a.application_id, s.service_name, a.status, a.submitted_at, a.last_updated_at, s.sla_days,
                   u_off.full_name as reviewer_name, o.designation as reviewer_designation
            FROM applications a
            JOIN services s ON a.service_id = s.service_id
            LEFT JOIN users u_off ON a.assigned_officer = u_off.user_id
            LEFT JOIN officers o ON u_off.user_id = o.user_id
            WHERE a.citizen_id = %s AND a.application_id = %s
        """, (citizen_id, application_id))
        app = cursor.fetchone()
        if not app:
            return {"error": "Application not found or access denied."}
            
        if app.get("submitted_at") and app.get("sla_days") is not None:
            app["sla_deadline"] = app["submitted_at"] + timedelta(days=app["sla_days"])
        else:
            app["sla_deadline"] = None
            
        cursor.execute("""
            SELECT from_status as old_status, to_status as new_status, changed_at, remarks
            FROM application_timeline
            WHERE application_id = %s
            ORDER BY changed_at ASC
        """, (application_id,))
        app["history"] = cursor.fetchall()
        return app
    finally:
        cursor.close()
        conn.close()

def get_missing_documents(user_id: int, application_id: str):
    citizen_id = get_citizen_id(user_id)
    if not citizen_id:
        return {"error": "Citizen profile not found."}
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT a.service_id, s.service_name, s.required_docs, a.documents_json, a.status
            FROM applications a
            JOIN services s ON a.service_id = s.service_id
            WHERE a.citizen_id = %s AND a.application_id = %s
        """, (citizen_id, application_id))
        app = cursor.fetchone()
        if not app:
            return {"error": "Application not found or access denied."}
            
        service_id = app["service_id"]
        
        required_docs_list = []
        if app.get("required_docs"):
            try:
                required_docs_list = json.loads(app["required_docs"]) if isinstance(app["required_docs"], str) else app["required_docs"]
            except Exception:
                pass
                
        uploaded_dict = {}
        if app.get("documents_json"):
            try:
                uploaded_dict = json.loads(app["documents_json"]) if isinstance(app["documents_json"], str) else app["documents_json"]
            except Exception:
                pass
                
        missing_docs = []
        for doc_name in required_docs_list:
            is_uploaded = False
            req_clean = doc_name.lower().replace(" ", "").replace("card", "").replace("certificate", "").replace("report", "")
            for up_key in uploaded_dict.keys():
                up_clean = up_key.lower().replace(" ", "").replace("card", "").replace("certificate", "").replace("report", "")
                if up_clean in req_clean or req_clean in up_clean:
                    is_uploaded = True
                    break
                    
            if not is_uploaded:
                reason = "Not uploaded"
                if app["status"] == "pending_docs":
                    reason = "Requested by Officer"
                missing_docs.append({
                    "document_type": doc_name,
                    "mandatory": "Yes",
                    "reason": reason
                })
                
        return {
            "application_id": application_id,
            "service_name": app["service_name"],
            "missing_documents": missing_docs
        }
    finally:
        cursor.close()
        conn.close()

# Officer scope data access
def get_pending_applications(officer_id: int, service_id: Optional[int] = None):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT dept_id, district_id FROM officers WHERE officer_id = %s", (officer_id,))
        off_row = cursor.fetchone()
        if not off_row:
            return {"error": "Officer details not found."}
            
        dept_id = off_row["dept_id"]
        district_id = off_row["district_id"]
        
        if service_id is not None:
            cursor.execute("SELECT department_id FROM services WHERE service_id = %s", (service_id,))
            srv_row = cursor.fetchone()
            if not srv_row or srv_row["department_id"] != dept_id:
                return {"error": "Access denied to this service."}
            services_to_query = [service_id]
        else:
            cursor.execute("SELECT service_id FROM services WHERE department_id = %s", (dept_id,))
            services_to_query = [row["service_id"] for row in cursor.fetchall()]
            
        if not services_to_query:
            return []
            
        format_strings = ','.join(['%s'] * len(services_to_query))
        query = f"""
            SELECT a.application_id, s.service_name, u_cit.full_name as applicant_name, a.status, a.submitted_at
            FROM applications a
            JOIN services s ON a.service_id = s.service_id
            JOIN citizens c ON a.citizen_id = c.citizen_id
            JOIN users u_cit ON c.user_id = u_cit.user_id
            WHERE a.status IN ('submitted', 'under_review', 'pending_docs') 
              AND a.service_id IN ({format_strings})
              AND a.district_id = %s
            ORDER BY a.submitted_at ASC
        """
        cursor.execute(query, tuple(services_to_query) + (district_id,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

def get_application_detail_officer(officer_id: int, application_id: str):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT dept_id, district_id FROM officers WHERE officer_id = %s", (officer_id,))
        off_row = cursor.fetchone()
        if not off_row:
            return {"error": "Officer details not found."}
            
        dept_id = off_row["dept_id"]
        district_id = off_row["district_id"]
        
        cursor.execute("""
            SELECT a.application_id, a.service_id, a.department_id, a.district_id, a.status, a.submitted_at, a.last_updated_at,
                   u_cit.full_name as applicant_name, u_cit.email as applicant_email, u_cit.mobile as applicant_phone, c.address_line as applicant_address,
                   a.documents_json
            FROM applications a
            JOIN citizens c ON a.citizen_id = c.citizen_id
            JOIN users u_cit ON c.user_id = u_cit.user_id
            WHERE a.application_id = %s
        """, (application_id,))
        app = cursor.fetchone()
        if not app:
            return {"error": "Application not found."}
            
        if app["department_id"] != dept_id or app["district_id"] != district_id:
            return {"error": "Access denied to this application."}
            
        docs_list = []
        if app.get("documents_json"):
            try:
                uploaded_dict = json.loads(app["documents_json"]) if isinstance(app["documents_json"], str) else app["documents_json"]
                for key in uploaded_dict.keys():
                    docs_list.append({"doc_type": key, "verified_status": "uploaded"})
            except Exception:
                pass
                
        app["documents"] = docs_list
        if "documents_json" in app:
            del app["documents_json"]
        if "department_id" in app:
            del app["department_id"]
        if "district_id" in app:
            del app["district_id"]
            
        return app
    finally:
        cursor.close()
        conn.close()

def get_sla_status(officer_id: int, service_id: Optional[int] = None):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT dept_id, district_id FROM officers WHERE officer_id = %s", (officer_id,))
        off_row = cursor.fetchone()
        if not off_row:
            return {"error": "Officer details not found."}
            
        dept_id = off_row["dept_id"]
        district_id = off_row["district_id"]
        
        if service_id is not None:
            cursor.execute("SELECT department_id FROM services WHERE service_id = %s", (service_id,))
            srv_row = cursor.fetchone()
            if not srv_row or srv_row["department_id"] != dept_id:
                return {"error": "Access denied to this service."}
            services_to_query = [service_id]
        else:
            cursor.execute("SELECT service_id FROM services WHERE department_id = %s", (dept_id,))
            services_to_query = [row["service_id"] for row in cursor.fetchall()]
            
        if not services_to_query:
            return []
            
        format_strings = ','.join(['%s'] * len(services_to_query))
        query = f"""
            SELECT a.application_id, s.service_name, u_cit.full_name as applicant_name, a.status, a.submitted_at, s.sla_days,
                   a.sla_breach
            FROM applications a
            JOIN services s ON a.service_id = s.service_id
            JOIN citizens c ON a.citizen_id = c.citizen_id
            JOIN users u_cit ON c.user_id = u_cit.user_id
            WHERE a.service_id IN ({format_strings})
              AND a.district_id = %s
            ORDER BY a.submitted_at ASC
        """
        cursor.execute(query, tuple(services_to_query) + (district_id,))
        apps = cursor.fetchall()
        for app in apps:
            app["is_breached"] = (app.get("sla_breach") == 1)
            if app.get("submitted_at") and app.get("sla_days") is not None:
                app["sla_deadline"] = app["submitted_at"] + timedelta(days=app["sla_days"])
            else:
                app["sla_deadline"] = None
        return apps
    finally:
        cursor.close()
        conn.close()

# Shared FAQ Search RAG tool
def faq_search(query: str, language: str = "en", selected_sno: Optional[str] = None):
    try:
        from backend.vector_store.chroma_store import query_vector_store
        candidates = query_vector_store(query, lang=language, limit=3, sno=selected_sno)
        context_parts = []
        for res in candidates:
            doc_text = res["document"]
            source_label = "[User Manual & Guidelines]" if res["metadata"].get("type") == "manual" else "[Official Service Specification Profile]"
            context_parts.append(f"{source_label}\n{doc_text}")
        return "\n\n---\n\n".join(context_parts)
    except Exception as e:
        return f"Error executing RAG search: {str(e)}"

# Execute tool helper
def execute_tool(name: str, arguments: Dict[str, Any], user_context: Dict[str, Any], language: str):
    role = user_context.get("role")
    user_id = user_context.get("user_id")
    officer_id = user_context.get("officer_id")
    
    # Secure role verification at code level
    if name == "faq_search":
        return faq_search(arguments.get("query", ""), language=language)
        
    elif name == "get_my_applications":
        if role != "citizen":
            return {"error": "Unauthorized."}
        return get_my_applications(user_id)
        
    elif name == "get_application_status":
        if role != "citizen":
            return {"error": "Unauthorized."}
        app_id = str(arguments.get("application_id", ""))
        return get_application_status(user_id, app_id)
        
    elif name == "get_missing_documents":
        if role != "citizen":
            return {"error": "Unauthorized."}
        app_id = str(arguments.get("application_id", ""))
        return get_missing_documents(user_id, app_id)
        
    elif name == "get_pending_applications":
        if role != "officer":
            return {"error": "Unauthorized."}
        service_id = arguments.get("service_id")
        if service_id is not None:
            service_id = int(service_id)
        return get_pending_applications(officer_id, service_id)
        
    elif name == "get_application_detail_officer":
        if role != "officer":
            return {"error": "Unauthorized."}
        app_id = str(arguments.get("application_id", ""))
        return get_application_detail_officer(officer_id, app_id)
        
    elif name == "get_sla_status":
        if role != "officer":
            return {"error": "Unauthorized."}
        service_id = arguments.get("service_id")
        if service_id is not None:
            service_id = int(service_id)
        return get_sla_status(officer_id, service_id)
        
    else:
        return {"error": f"Unknown tool: {name}"}

# Claude format tools specifications
CLAUDE_TOOLS = {
    "citizen": [
        {
            "name": "get_my_applications",
            "description": "Lists all submitted applications with their status for the authenticated user",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "get_application_status",
            "description": "Retrieves the detailed status and historical stage logs of a specific application",
            "input_schema": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "string",
                        "description": "The ID of the application to query"
                    }
                },
                "required": ["application_id"]
            }
        },
        {
            "name": "get_missing_documents",
            "description": "Lists required documents that are either not yet uploaded or have been rejected",
            "input_schema": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "string",
                        "description": "The ID of the application to query"
                    }
                },
                "required": ["application_id"]
            }
        },
        {
            "name": "faq_search",
            "description": "Queries the general Seva Setu services catalog and citizen manuals (RAG FAQ)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user query/topic to search (e.g. eligibility, documents required, SLA)"
                    }
                },
                "required": ["query"]
            }
        }
    ],
    "officer": [
        {
            "name": "get_pending_applications",
            "description": "Lists pending applications in the queue for the officer's assigned services",
            "input_schema": {
                "type": "object",
                "properties": {
                    "service_id": {
                        "type": "integer",
                        "description": "Optional filter for a specific service ID"
                    }
                },
                "required": []
            }
        },
        {
            "name": "get_application_detail_officer",
            "description": "Retrieves applicant information and document verification metadata (excludes file path/file content)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "string",
                        "description": "The ID of the application to query"
                    }
                },
                "required": ["application_id"]
            }
        },
        {
            "name": "get_sla_status",
            "description": "Lists SLA deadlines and flags applications that breached SLA limits",
            "input_schema": {
                "type": "object",
                "properties": {
                    "service_id": {
                        "type": "integer",
                        "description": "Optional filter for a specific service ID"
                    }
                },
                "required": []
            }
        },
        {
            "name": "faq_search",
            "description": "Queries the general Seva Setu services catalog and citizen manuals (RAG FAQ)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user query/topic to search (e.g. eligibility, documents required, SLA)"
                    }
                },
                "required": ["query"]
            }
        }
    ],
    "anonymous": [
        {
            "name": "faq_search",
            "description": "Queries the general Seva Setu services catalog and citizen manuals (RAG FAQ)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user query/topic to search (e.g. eligibility, documents required, SLA)"
                    }
                },
                "required": ["query"]
            }
        }
    ]
}

def load_manifest():
    global MANIFEST_DATA, SERVICES_MAP
    if not os.path.exists(DATA_MANIFEST_PATH):
        print(f"[API] Warning: Manifest file not found at: {DATA_MANIFEST_PATH}")
        return
        
    try:
        with open(DATA_MANIFEST_PATH, "r", encoding="utf-8") as f:
            MANIFEST_DATA = json.load(f)
            
        for s in MANIFEST_DATA.get("services", []):
            SERVICES_MAP[str(s.get("sno"))] = s
        print(f"[API] Cached {len(SERVICES_MAP)} services from manifest.")
    except Exception as e:
        print(f"[API] Error loading manifest catalog: {e}")

    # Pre-load embedder model on startup to avoid first-query latency
    try:
        from backend.embeddings.embedder import get_embedder_model
        print("[API] Pre-loading embedding model on startup...")
        get_embedder_model()
        print("[API] Embedding model pre-loaded successfully.")
    except Exception as e:
        print(f"[API] Error pre-loading embedding model: {e}")

@app.on_event("startup")
def startup_handler():
    load_manifest()
    init_db_pool()

# API Validation schemas
class Message(BaseModel):
    role: str # 'user' or 'assistant'
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    selected_sno: Optional[str] = None
    language: str = "en" # 'en' or 'hi'

class SearchRequest(BaseModel):
    query: str
    language: str = "en"

@app.get("/api/services")
def list_services():
    """
    Returns the list of all services in the catalog for browsing.
    """
    if not MANIFEST_DATA:
        # Try loading manifest on the fly if not loaded yet
        load_manifest()
        if not MANIFEST_DATA:
            raise HTTPException(status_code=500, detail="Manifest database not loaded on the backend.")
    return MANIFEST_DATA.get("services", [])

@app.get("/api/services/{sno}")
def get_service_details(sno: str, lang: str = "en"):
    """
    Retrieves the detailed JSON profile of a specific service.
    """
    if not SERVICES_MAP:
        load_manifest()
        
    if sno not in SERVICES_MAP:
        raise HTTPException(status_code=404, detail="Service not found.")
        
    service_meta = SERVICES_MAP[sno]
    path_key = "path_hi" if lang == "hi" else "path_en"
    rel_path = service_meta.get(path_key)
    
    if not rel_path:
        raise HTTPException(status_code=404, detail=f"Service details path not found for language: {lang}")
        
    full_path = os.path.join(WORKSPACE_DIR, rel_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Service details file missing on disk.")
        
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            details_json = json.load(f)
            
        if lang == "hi":
            # Also try to load the English version for fallback values
            en_rel_path = service_meta.get("path_en")
            if en_rel_path:
                en_full_path = os.path.join(WORKSPACE_DIR, en_rel_path)
                if os.path.exists(en_full_path):
                    with open(en_full_path, "r", encoding="utf-8") as en_f:
                        en_details = json.load(en_f)
                    
                    # Merge keys if they are empty or missing in Hindi
                    for key in ["sla", "time_limit", "contact_details"]:
                        if not details_json.get(key) and en_details.get(key):
                            val = en_details.get(key)
                            if key in ["sla", "time_limit"] and isinstance(val, str):
                                val_translated = val.replace("Days", "दिन").replace("Day", "दिन")
                                details_json[key] = val_translated
                            elif key == "contact_details" and val == "Sewa Setu Kendra":
                                details_json[key] = "सेवा सेतु केंद्र"
                            else:
                                details_json[key] = val
                                
                    # Merge fees
                    hi_fees = details_json.get("fees")
                    en_fees = en_details.get("fees")
                    if en_fees:
                        if not hi_fees:
                            details_json["fees"] = en_fees
                        else:
                            for fee_key in ["kiosk_fee", "online_fee", "where_to_apply", "raw_text"]:
                                if not hi_fees.get(fee_key) and en_fees.get(fee_key):
                                    val = en_fees.get(fee_key)
                                    if fee_key == "raw_text" and isinstance(val, str):
                                        val_translated = val.replace("Where to Apply?", "कहाँ आवेदन करें?").replace("Sewa Setu Kendra", "सेवा सेतु केंद्र").replace("Online", "ऑनलाइन")
                                        hi_fees[fee_key] = val_translated
                                    elif fee_key == "where_to_apply" and val == "Sewa Setu Kendra":
                                        hi_fees[fee_key] = "सेवा सेतु केंद्र"
                                    else:
                                        hi_fees[fee_key] = val
                                        
                    # Merge downloaded_pdfs
                    if not details_json.get("downloaded_pdfs") and en_details.get("downloaded_pdfs"):
                        details_json["downloaded_pdfs"] = en_details.get("downloaded_pdfs")
                        
        return details_json
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading details file: {str(e)}")

@app.post("/api/chat")
def chat_with_bot(request: ChatRequest, authorization: Optional[str] = Header(None)):
    """
    Core RAG & database-scoped Chat endpoint.
    Checks user's role from JWT token and dynamically provisions tools.
    """
    user_query = request.messages[-1].content
    language = request.language
    
    # 1. Parse authentication header and role context
    user_context = {"role": "anonymous", "user_id": None, "officer_id": None}
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        payload = decode_jwt_token(token)
        if payload:
            user_context = {
                "role": payload.get("role", "anonymous"),
                "user_id": payload.get("user_id"),
                "officer_id": payload.get("officer_id")
            }
            
    role = user_context["role"]
    print(f"[Agent] Authenticated context: {user_context}")
    
    # 2. Query Chroma vector store (RAG retrieval)
    candidates = []
    metadata_doc = None
    retrieval_start = time.perf_counter()
    try:
        from backend.vector_store.chroma_store import query_vector_store, get_collection
        
        # If a service is selected, retrieve its metadata profile directly
        if request.selected_sno:
            try:
                collection = get_collection()
                doc_id = f"meta_{request.selected_sno}_{language}_0"
                res = collection.get(ids=[doc_id])
                if res and "documents" in res and len(res["documents"]) > 0 and res["documents"][0]:
                    metadata_doc = res["documents"][0]
            except Exception as e:
                print(f"[API] Error fetching direct metadata doc: {e}")
                
        # Retrieve top chunks
        candidates = query_vector_store(user_query, lang=language, limit=3, sno=request.selected_sno)
    except Exception as e:
        print(f"[API] Error querying vector store: {e}")
    finally:
        retrieval_elapsed = time.perf_counter() - retrieval_start
        print(f"\n[TIMING] Chunk retrieval took: {retrieval_elapsed:.3f}s")
        
    # Budget-based context compile
    context_parts = []
    current_length = 0
    budget = 10000
    
    if metadata_doc:
        header = "[Official Service Specification Profile]"
        context_parts.append(f"{header}\n{metadata_doc}")
        current_length += len(header) + len(metadata_doc)
        
    for res in candidates:
        if res["metadata"].get("type") == "metadata" and metadata_doc:
            continue
        doc_text = res["document"]
        source_label = "[User Manual & Guidelines]" if res["metadata"].get("type") == "manual" else "[Official Service Specification Profile]"
        chunk_text = f"{source_label}\n{doc_text}"
        chunk_len = len(chunk_text)
        
        if current_length + chunk_len > budget:
            break
            
        context_parts.append(chunk_text)
        current_length += chunk_len
        
    retrieved_context = "\n\n---\n\n".join(context_parts)
    
    # Construct System prompt instructions depending on role and language
    system_instruction = ""
    if language == "hi":
        system_instruction = (
            "आप SewaSetu (सेवा सेतु) छत्तीसगढ़ पोर्टल के एक विशेषज्ञ सहायक हैं।\n"
            "आपका उद्देश्य नागरिकों को सरकारी सेवाओं के आवेदन, आवश्यक दस्तावेजों, शुल्कों और उनके आवेदन की स्थिति को समझने में मदद करना है।\n\n"
            f"उपयोगकर्ता की भूमिका (Role): {role}\n"
        )
        if role == "anonymous":
            system_instruction += (
                "यदि उपयोगकर्ता अपने किसी आवेदन की स्थिति या दस्तावेजों के बारे में पूछता है, तो उसे बताएं कि वह अपने आवेदन की स्थिति देखने के लिए पोर्टल पर लॉग इन करे।\n"
            )
        system_instruction += (
            "सामान्य प्रश्नों (जैसे पात्रता, शुल्क, नियम) के लिए 'faq_search' टूल का उपयोग करें।\n"
            "उत्तर देने के लिए केवल और केवल प्रदान किए गए संदर्भ (Context) का उपयोग करें। यदि संदर्भ में उपयोगकर्ता के प्रश्न का उत्तर पर्याप्त रूप से उपलब्ध नहीं है, तो 'जानकारी उपलब्ध नहीं है।' उत्तर दें।\n\n"
        )
        if retrieved_context:
            system_instruction += f"संदर्भ दस्तावेज़:\n{retrieved_context}\n\n"
    else:
        system_instruction = (
            "You are an expert assistant for the SewaSetu Chhattisgarh portal.\n"
            "Your goal is to help citizens understand how to apply for services, check required documents, kiosk/online fees, timelines, and check application status.\n\n"
            f"User Role: {role}\n"
        )
        if role == "anonymous":
            system_instruction += (
                "If the user asks about their own application status, missing documents, or officer actions, inform them that they must log in to view or manage application details.\n"
            )
        system_instruction += (
            "For general queries (e.g. eligibility, fees, rules), use the 'faq_search' tool.\n"
            "If they ask about their own live application data, use the appropriate database tools provided to you. "
            "Never make up application status, application IDs, or missing documents - always call the tools to fetch the real data.\n\n"
            "Answer the question using ONLY the relevant context. If there is insufficient information to answer the question, respond with: 'Information not available.'\n\n"
        )
        if retrieved_context:
            system_instruction += f"Relevant Context:\n{retrieved_context}\n\n"
            
    # Format message history
    history = request.messages[-7:-1] if len(request.messages) > 1 else []
    
    # Check if we should use Sarvam AI API or fall back to local Ollama
    if USE_SARVAM_API and SARVAM_API_KEY:
        generation_start = time.perf_counter()
        try:
            # Construct standard chat messages format
            sarvam_messages = [{"role": "system", "content": system_instruction}]
            for msg in history:
                sarvam_messages.append({"role": msg.role, "content": msg.content})
            sarvam_messages.append({"role": "user", "content": user_query})
            
            # Fetch tools corresponding to role
            role_tools = CLAUDE_TOOLS.get(role, CLAUDE_TOOLS["anonymous"])
            openai_tools = []
            for t in role_tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"]
                    }
                })
                
            url = "https://api.sarvam.ai/v1/chat/completions"
            headers = {
                "api-subscription-key": SARVAM_API_KEY,
                "Authorization": f"Bearer {SARVAM_API_KEY}",
                "Content-Type": "application/json"
            }
            
            # Agent Loop (up to 3 iterations)
            max_iterations = 3
            for iteration in range(max_iterations):
                payload = {
                    "model": SARVAM_MODEL,
                    "messages": sarvam_messages,
                    "temperature": 0.0,
                    "tools": openai_tools,
                    "tool_choice": "auto"
                }
                
                print(f"[Agent] Iteration {iteration+1}: Querying Sarvam AI...")
                res = requests.post(url, json=payload, headers=headers, timeout=120)
                
                if res.status_code != 200:
                    raise Exception(f"Sarvam AI API returned code {res.status_code}: {res.text}")
                    
                res_json = res.json()
                choice = res_json["choices"][0]
                message = choice["message"]
                
                # If tool calls are requested
                if "tool_calls" in message and message["tool_calls"]:
                    # Append assistant message (containing tool calls) to message list
                    # OpenAI specs require keeping the assistant message in history to follow up
                    sarvam_messages.append(message)
                    
                    for tc in message["tool_calls"]:
                        tc_id = tc.get("id")
                        func_name = tc["function"]["name"]
                        func_args = {}
                        try:
                            func_args = json.loads(tc["function"]["arguments"] or "{}")
                        except Exception:
                            pass
                            
                        # Execute the tool safely passing the trusted user_context
                        print(f"[Agent] Executing tool '{func_name}' with args: {func_args}")
                        tool_res = execute_tool(func_name, func_args, user_context, language)
                        serialized_res = serialize_data(tool_res)
                        
                        # Append tool response
                        sarvam_messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": func_name,
                            "content": json.dumps(serialized_res)
                        })
                    # Continue loop to call model again with tool output
                    continue
                else:
                    # No tool call, return the response text
                    bot_reply = message.get("content", "").strip()
                    bot_reply = re.sub(r'<think>.*?</think>', '', bot_reply, flags=re.DOTALL).strip()
                    
                    generation_elapsed = time.perf_counter() - generation_start
                    print(f"[TIMING] Agent generation took: {generation_elapsed:.3f}s")
                    return {"response": bot_reply}
                    
            # If we reached maximum iterations without text response
            return {"response": "I ran into a loop trying to fetch your details. Please try asking again."}
            
        except Exception as e:
            print(f"[API] Sarvam AI API execution exception: {e}")
            raise HTTPException(status_code=500, detail=f"Error communicating with Sarvam AI: {str(e)}")
            
    else:
        # Fallback: Query Ollama HTTP API (with simple text search for tools context)
        # To support basic local fallback without complex tool execution loops, we can pre-execute RAG search
        rag_context = faq_search(user_query, language=language, selected_sno=request.selected_sno)
        
        prompt_parts = [f"System: {system_instruction}"]
        if rag_context:
            prompt_parts.append(f"Chroma Context:\n{rag_context}")
        for msg in history:
            role_label = "User" if msg.role == "user" else "Assistant"
            prompt_parts.append(f"{role_label}: {msg.content}")
        prompt_parts.append(f"User: {user_query}")
        prompt_parts.append("Assistant: ")
        
        full_prompt = "\n\n".join(prompt_parts)
        
        generation_start = time.perf_counter()
        try:
            url = f"{OLLAMA_BASE_URL}/api/generate"
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0
                }
            }
            res = requests.post(url, json=payload, timeout=150)
            if res.status_code == 200:
                generation_elapsed = time.perf_counter() - generation_start
                print(f"[TIMING] Answer generation took: {generation_elapsed:.3f}s")
                bot_reply = res.json().get("response", "").strip()
                bot_reply = re.sub(r'<think>.*?</think>', '', bot_reply, flags=re.DOTALL).strip()
                return {"response": bot_reply}
            else:
                raise HTTPException(status_code=500, detail=f"Ollama server returned code {res.status_code}")
        except Exception as e:
            print(f"[API] Ollama HTTP execution exception: {e}")
            raise HTTPException(status_code=500, detail=f"Error communicating with local LLM: {str(e)}")

@app.post("/api/search")
def search_services(request: SearchRequest):
    """
    LLM-based Search endpoint to identify the closest matching service catalog item.
    Supports English, Hindi, and Hinglish.
    """
    query = request.query.strip()
    if not query:
        return {"sno": None, "service_id": None}
        
    # Load manifest services dynamically to build the catalog list dynamically
    services = []
    if MANIFEST_DATA and "services" in MANIFEST_DATA:
        services = MANIFEST_DATA["services"]
    else:
        # Fallback load manifest on the fly if not cached yet
        load_manifest()
        services = MANIFEST_DATA.get("services", []) if MANIFEST_DATA else []
        
    services_list = []
    for s in services:
        services_list.append(
            f"{s.get('sno')}. Serial Number {s.get('sno')} (Service ID: {s.get('service_id')}): {s.get('name_en')} | {s.get('name_hi')}"
        )
    services_catalog_desc = "\n".join(services_list)
    
    prompt = (
        "You are an expert service mapping assistant for the SewaSetu Chhattisgarh portal.\n"
        "Your task is to identify which specific service from the catalog is the closest match to the user query.\n"
        "The query could be in English, Hindi, or Hinglish (e.g. 'shadi certificate', 'aay praman', 'pani connection').\n\n"
        "Here is the catalog of services:\n"
        f"{services_catalog_desc}\n\n"
        f"User Query: '{query}'\n\n"
        "Instructions:\n"
        "- Match the query to a service ONLY if the query explicitly mentions or clearly target that specific service (e.g., marriage, income, domicile, water tap, CMEGP, or film subsidy).\n"
        "- Do NOT match generic queries like 'certificate', 'fees', 'documents', 'registration', 'apply', or 'how to apply' to any specific service if the query does not specify which service it is about.\n"
        "- If the query is generic, ambiguous, or does not clearly map to a specific service in the catalog, you MUST return {\"sno\": null, \"service_id\": null}.\n"
        "- Return ONLY a JSON object containing the mapped 'sno' and 'service_id' as strings. For example: {\"sno\": \"1\", \"service_id\": \"3\"}\n"
        "- Do not explain your choice. Do not output markdown, only raw JSON.\n\n"
        "Output JSON:"
    )
    
    if USE_SARVAM_API and SARVAM_API_KEY:
        try:
            url = "https://api.sarvam.ai/v1/chat/completions"
            headers = {
                "api-subscription-key": SARVAM_API_KEY,
                "Authorization": f"Bearer {SARVAM_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": SARVAM_MODEL,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0
            }
            print(f"[API] Querying Sarvam AI API for service mapping (Model: {SARVAM_MODEL})...")
            res = requests.post(url, json=payload, headers=headers, timeout=60)
            if res.status_code == 200:
                reply = res.json()["choices"][0]["message"]["content"].strip()
                # Extract JSON from reply using Regex
                json_match = re.search(r'\{.*?\}', reply, re.DOTALL)
                if json_match:
                    json_data = json.loads(json_match.group(0))
                    sno_val = json_data.get("sno")
                    sid_val = json_data.get("service_id")
                    if sno_val and str(sno_val).lower() != "null":
                        return {
                            "sno": str(sno_val),
                            "service_id": str(sid_val) if sid_val else None
                        }
                else:
                    print(f"[Search API] Failed to extract JSON from Sarvam reply: {reply}")
            else:
                print(f"[Search API] Sarvam AI API returned code {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[Search API] Mapping via Sarvam failed: {e}")
    else:
        # Fallback: Query local Ollama
        try:
            url = f"{OLLAMA_BASE_URL}/api/generate"
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0 # Force deterministic output
                }
            }
            res = requests.post(url, json=payload, timeout=60) # Higher timeout for first run loading
            if res.status_code == 200:
                reply = res.json().get("response", "").strip()
                
                # Extract JSON from reply using Regex
                json_match = re.search(r'\{.*?\}', reply, re.DOTALL)
                if json_match:
                    json_data = json.loads(json_match.group(0))
                    sno_val = json_data.get("sno")
                    sid_val = json_data.get("service_id")
                    if sno_val and str(sno_val).lower() != "null":
                        return {
                            "sno": str(sno_val),
                            "service_id": str(sid_val) if sid_val else None
                        }
                else:
                    print(f"[Search API] Failed to extract JSON from reply: {reply}")
        except Exception as e:
            print(f"[Search API] Mapping failed with error: {e}")
        
    return {"sno": None, "service_id": None}

@app.post("/api/ingest")
def trigger_ingestion(background_tasks: BackgroundTasks):
    def run_process():
        try:
            from data_pipeline.data_processor import run_ingestion
            run_ingestion()
        except Exception as e:
            print(f"[API] Ingestion Failed: {e}")
            
    background_tasks.add_task(run_process)
    return {"message": "Ingestion pipeline triggered in the background."}

# Trigger Uvicorn Reload for manifest update
