# test_db.py
import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

try:
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME", "bantay"),
    )

    if conn.is_connected():
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE(), NOW(), VERSION()")
        db_name, now, version = cursor.fetchone()
        print(f"✅ Connected successfully!")
        print(f"   Database : {db_name}")
        print(f"   Time     : {now}")
        print(f"   MySQL    : {version}")
        cursor.close()
        conn.close()

except mysql.connector.Error as e:
    print(f"❌ Connection failed: {e}")