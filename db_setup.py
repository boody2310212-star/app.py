import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

# 1. إنشاء أو الاتصال بقاعدة البيانات (سيتم إنشاء الملف تلقائياً)
conn = sqlite3.connect("users_database.db")
cursor = conn.cursor()

# 2. إنشاء جدول المستخدمين
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
''')

# 3. إدخال مستخدم تجريبي بكلمة مرور مشفرة
try:
    hashed_pass = generate_password_hash("123456") # تشفير كلمة المرور
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("admin", hashed_pass))
    conn.commit()
    print("✅ تم إنشاء قاعدة البيانات وإضافة المستخدم المشفّر بنجاح!")
except sqlite3.IntegrityError:
    print("⚠️ المستخدم موجود بالفعل في قاعدة البيانات.")

conn.close()