import os
import mysql.connector
from dotenv import load_dotenv
import bcrypt
from datetime import datetime, timedelta

# Load env
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root")
DB_NAME = os.getenv("DB_NAME", "sewasetu_db")

def get_db_connection(include_db=True):
    if include_db:
        return mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
    else:
        return mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def init_db():
    print("[DB Init] Connecting to MySQL...")
    conn = get_db_connection(include_db=False)
    cursor = conn.cursor()
    
    print(f"[DB Init] Dropping database '{DB_NAME}' if it exists...")
    cursor.execute(f"DROP DATABASE IF EXISTS {DB_NAME};")
    print(f"[DB Init] Creating database '{DB_NAME}'...")
    cursor.execute(f"CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    conn.commit()
    cursor.close()
    conn.close()
    
    # Connect to the database
    conn = get_db_connection(include_db=True)
    cursor = conn.cursor()
    
    # 1. Services table
    print("[DB Init] Creating 'services' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS services (
        service_id INT AUTO_INCREMENT PRIMARY KEY,
        service_name VARCHAR(255) NOT NULL UNIQUE,
        sla_days INT NOT NULL
    ) ENGINE=InnoDB;
    """)
    
    # 2. Users table
    print("[DB Init] Creating 'users' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        phone VARCHAR(20) NOT NULL UNIQUE,
        email VARCHAR(255) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        role ENUM('citizen', 'officer') NOT NULL,
        aadhaar_number VARCHAR(12) NOT NULL,
        address TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """)
    
    # 3. Officers table
    print("[DB Init] Creating 'officers' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS officers (
        officer_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        service_id INT NOT NULL,
        designation VARCHAR(100),
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)
    
    # 4. Applications table
    print("[DB Init] Creating 'applications' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS applications (
        application_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        service_id INT NOT NULL,
        status ENUM('submitted', 'under_review', 'approved', 'rejected') NOT NULL DEFAULT 'submitted',
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sla_deadline DATETIME NOT NULL,
        assigned_officer_id INT,
        last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE CASCADE,
        FOREIGN KEY (assigned_officer_id) REFERENCES officers(officer_id) ON DELETE SET NULL
    ) ENGINE=InnoDB;
    """)
    
    # 5. Documents table
    print("[DB Init] Creating 'documents' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        document_id INT AUTO_INCREMENT PRIMARY KEY,
        application_id INT NOT NULL,
        doc_type VARCHAR(255) NOT NULL,
        file_path VARCHAR(500) NOT NULL,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        verified_status ENUM('pending', 'verified', 'rejected') NOT NULL DEFAULT 'pending',
        FOREIGN KEY (application_id) REFERENCES applications(application_id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)
    
    # 6. Application status history log table
    print("[DB Init] Creating 'application_status_history' table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS application_status_history (
        log_id INT AUTO_INCREMENT PRIMARY KEY,
        application_id INT NOT NULL,
        old_status VARCHAR(50),
        new_status VARCHAR(50),
        changed_by INT,
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (application_id) REFERENCES applications(application_id) ON DELETE CASCADE,
        FOREIGN KEY (changed_by) REFERENCES users(user_id) ON DELETE SET NULL
    ) ENGINE=InnoDB;
    """)
    
    conn.commit()
    
    # --- Seeding Data ---
    
    # Seed Services
    print("[DB Init] Seeding services...")
    services_to_seed = [
        (3, "Marriage Certificate", 15),
        (8, "ST Certificate", 15),
        (4, "SC Certificate", 15),
        (5, "OBC Caste Certificate", 22),
        (201, "Gazette Notification", 30),
        (7, "Domicile Certificate", 15)
    ]
    for sid, sname, sla in services_to_seed:
        cursor.execute("SELECT service_id FROM services WHERE service_name = %s", (sname,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO services (service_id, service_name, sla_days) VALUES (%s, %s, %s)", (sid, sname, sla))
    conn.commit()
    
    # Fetch service IDs for referencing
    cursor.execute("SELECT service_name, service_id FROM services")
    services_map = dict(cursor.fetchall())
    
    # Seed Users
    print("[DB Init] Seeding users...")
    hashed_pwd = hash_password("password123")
    users_to_seed = [
        # Citizens
        ("Rahul Sharma", "9876543210", "rahul@gmail.com", hashed_pwd, "citizen", "123456789012", "Shastri Nagar, Raipur, CG"),
        ("Priya Patel", "9876543211", "priya@gmail.com", hashed_pwd, "citizen", "987654321098", "Indira Chowk, Bilaspur, CG"),
        # Officers
        ("Officer Verma", "9876543220", "verma@gmail.com", hashed_pwd, "officer", "111122223333", "Collectorate Campus, Raipur, CG"),
        ("Officer Mandavi", "9876543221", "mandavi@gmail.com", hashed_pwd, "officer", "444455556666", "Tahsil Office, Durg, CG")
    ]
    for name, phone, email, pwd_h, role, adhar, addr in users_to_seed:
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (name, phone, email, password_hash, role, aadhaar_number, address) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (name, phone, email, pwd_h, role, adhar, addr))
    conn.commit()
    
    # Fetch user IDs for referencing
    cursor.execute("SELECT email, user_id FROM users")
    users_map = dict(cursor.fetchall())
    
    # Seed Officers
    print("[DB Init] Seeding officers...")
    officers_to_seed = [
        # Officer Verma handles Marriage Certificate
        (users_map["verma@gmail.com"], services_map["Marriage Certificate"], "Senior Marriage Registrar"),
        # Officer Verma also handles Domicile Certificate
        (users_map["verma@gmail.com"], services_map["Domicile Certificate"], "Revenue Officer"),
        # Officer Mandavi handles OBC Caste Certificate
        (users_map["mandavi@gmail.com"], services_map["OBC Caste Certificate"], "Tehsildar"),
        # Officer Mandavi handles SC Certificate
        (users_map["mandavi@gmail.com"], services_map["SC Certificate"], "Tehsildar")
    ]
    for uid, sid, desg in officers_to_seed:
        cursor.execute("SELECT officer_id FROM officers WHERE user_id = %s AND service_id = %s", (uid, sid))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO officers (user_id, service_id, designation) VALUES (%s, %s, %s)", (uid, sid, desg))
    conn.commit()
    
    # Fetch officer IDs for referencing
    cursor.execute("SELECT user_id, service_id, officer_id FROM officers")
    officers_list = cursor.fetchall()
    # map (user_id, service_id) -> officer_id
    officers_map = {(row[0], row[1]): row[2] for row in officers_list}
    
    # Seed Applications
    print("[DB Init] Seeding applications...")
    now = datetime.now()
    
    # We want to seed some approved, some submitted, some past SLA (breached)
    # 1. Rahul's Domicile Application (submitted 20 days ago, SLA 15 days -> Breached!)
    # Assigned to Officer Verma (who handles Domicile)
    verma_dom_off_id = officers_map[(users_map["verma@gmail.com"], services_map["Domicile Certificate"])]
    sub_date_1 = now - timedelta(days=20)
    sla_deadline_1 = sub_date_1 + timedelta(days=15)
    
    cursor.execute("SELECT application_id FROM applications WHERE user_id = %s AND service_id = %s", 
                   (users_map["rahul@gmail.com"], services_map["Domicile Certificate"]))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO applications (user_id, service_id, status, submitted_at, sla_deadline, assigned_officer_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (users_map["rahul@gmail.com"], services_map["Domicile Certificate"], "under_review", sub_date_1, sla_deadline_1, verma_dom_off_id))
        app_id_1 = cursor.lastrowid
        
        # Seed status log
        cursor.execute("""
            INSERT INTO application_status_history (application_id, old_status, new_status, changed_by)
            VALUES (%s, %s, %s, %s)
        """, (app_id_1, "submitted", "under_review", users_map["verma@gmail.com"]))
        
        # Seed Documents (1 verified, 1 pending)
        cursor.execute("""
            INSERT INTO documents (application_id, doc_type, file_path, verified_status)
            VALUES 
            (%s, 'Aadhaar Card', '/uploads/rahul_aadhaar.pdf', 'verified'),
            (%s, 'Ration Card', '/uploads/rahul_ration.pdf', 'pending')
        """, (app_id_1, app_id_1))
        
    # 2. Rahul's Marriage Application (submitted 5 days ago, SLA 15 days -> Within SLA, approved!)
    verma_marr_off_id = officers_map[(users_map["verma@gmail.com"], services_map["Marriage Certificate"])]
    sub_date_2 = now - timedelta(days=5)
    sla_deadline_2 = sub_date_2 + timedelta(days=15)
    cursor.execute("SELECT application_id FROM applications WHERE user_id = %s AND service_id = %s", 
                   (users_map["rahul@gmail.com"], services_map["Marriage Certificate"]))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO applications (user_id, service_id, status, submitted_at, sla_deadline, assigned_officer_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (users_map["rahul@gmail.com"], services_map["Marriage Certificate"], "approved", sub_date_2, sla_deadline_2, verma_marr_off_id))
        app_id_2 = cursor.lastrowid
        
        # Seed status log
        cursor.execute("""
            INSERT INTO application_status_history (application_id, old_status, new_status, changed_by)
            VALUES (%s, %s, %s, %s)
        """, (app_id_2, "submitted", "approved", users_map["verma@gmail.com"]))
        
        # Seed Documents (all verified)
        cursor.execute("""
            INSERT INTO documents (application_id, doc_type, file_path, verified_status)
            VALUES 
            (%s, 'Marriage Photo', '/uploads/rahul_marriage_photo.jpg', 'verified'),
            (%s, 'Affidavit', '/uploads/rahul_affidavit.pdf', 'verified')
        """, (app_id_2, app_id_2))
        
    # 3. Priya's OBC Certificate Application (submitted 2 days ago, SLA 22 days -> Within SLA, pending, missing docs!)
    mandavi_obc_off_id = officers_map[(users_map["mandavi@gmail.com"], services_map["OBC Caste Certificate"])]
    sub_date_3 = now - timedelta(days=2)
    sla_deadline_3 = sub_date_3 + timedelta(days=22)
    cursor.execute("SELECT application_id FROM applications WHERE user_id = %s AND service_id = %s", 
                   (users_map["priya@gmail.com"], services_map["OBC Caste Certificate"]))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO applications (user_id, service_id, status, submitted_at, sla_deadline, assigned_officer_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (users_map["priya@gmail.com"], services_map["OBC Caste Certificate"], "submitted", sub_date_3, sla_deadline_3, mandavi_obc_off_id))
        app_id_3 = cursor.lastrowid
        
        # Seed status log
        cursor.execute("""
            INSERT INTO application_status_history (application_id, old_status, new_status, changed_by)
            VALUES (%s, %s, %s, %s)
        """, (app_id_3, None, "submitted", users_map["priya@gmail.com"]))
        
        # Seed Documents (1 pending, missing others)
        cursor.execute("""
            INSERT INTO documents (application_id, doc_type, file_path, verified_status)
            VALUES 
            (%s, 'Income Certificate', '/uploads/priya_income.pdf', 'pending')
        """, (app_id_3,))
        
    conn.commit()
    cursor.close()
    conn.close()
    print("[DB Init] Success! Database populated successfully.")

if __name__ == "__main__":
    init_db()
