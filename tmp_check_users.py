import sqlite3

conn = sqlite3.connect('booknest.db')
cur = conn.cursor()
try:
    cur.execute('SELECT count(*) FROM users')
    print(cur.fetchone())
except Exception as e:
    print('ERROR', e)
finally:
    conn.close()
