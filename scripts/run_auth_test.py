from db import authenticate_user

res = authenticate_user('admin','admin123')
print('authenticate_user returned:', res)
