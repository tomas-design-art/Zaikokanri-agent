from db import get_db_connection

with get_db_connection() as conn:
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, username, display_name, user_role, department, password_hash, is_active FROM users WHERE username='admin'")
        row = cur.fetchone()
        if row:
            print('FOUND')
            print('id:', row['id'])
            print('username:', row['username'])
            print('display_name:', row['display_name'])
            print('user_role:', row['user_role'])
            print('department:', row['department'])
            pw = row['password_hash']
            print('password_hash (truncated):', (pw[:20] + '...') if pw else 'NULL')
            print('is_active:', row['is_active'])
        else:
            print('NOT FOUND')
    except Exception as e:
        print('ERROR', e)
