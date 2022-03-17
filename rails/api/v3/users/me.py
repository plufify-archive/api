import json
import quart
import re
from ..snowflakes import snowflake_with_blast, invite_code
from ..data_bodys import error_bodys
from ..database import users, user_settings
from ..encrypt import get_hash_for
from ..checks import check_session_
from ..rate import rater

users_me = quart.Blueprint('users_me-v3', __name__)

# regex for emails
email_regex = '^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,3}$'


@users_me.post('')
@rater.limit('1/hour')
async def create_user():
    d: dict = await quart.request.get_json()

    if d['separator'] == int:
        return quart.Response(error_bodys['invalid_data'], status=400)

    if len(d['separator']) != 4:
        return quart.Response(body=error_bodys['invalid_data'], status=400)

    if d['separator'] == 0000:
        return quart.Response(error_bodys['invalid_data'], status=400)

    email_code = await invite_code()

    if re.search(email_regex, d.get('email')):
        pass
    else:
        return quart.Response(error_bodys['invalid_data'], status=400)
    
    em = users.find_one({'email': d.get('email')})

    if em != None:
        return quart.Response(error_bodys['invalid_data'], status=400)

    _id = snowflake_with_blast()

    try:
        given = {
            'id': _id,
            'username': d['username'],
            'separator': d['separator'],
            'bio': d.get('bio', ''),
            'avatar_url': None,
            'banner_url': None,
            'flags': ['Early Adopter'],
            'verified': False,
            'email': d['email'],
            'password': get_hash_for(d.pop('password')),
            'system': False,
            'email_verified': False,
            'session_ids': [str(snowflake_with_blast())],
            'email_code': email_code,
            'blocked_users': []
        }
    except KeyError:
        return quart.Response(body=error_bodys['invalid_data'], status=400)
    else:
        r = quart.Response(json.dumps(given), status=201)
        await user_settings.insert_one({'id': _id, 'accept_friend_requests': True})
        # email.send(f'Welcome to hatsu! Your verification code is: {email_code}')
        await users.insert_one(given)
        return r


@users_me.post('/verify')
async def verify_me():
    user = await check_session_(quart.request.headers.get('Authorization'))

    if user == None:
        return quart.Response(error_bodys['no_auth'], 401)

    d: dict = await quart.request.get_json(True)

    code = d.get('code', '')

    if code != user['email_code']:
        return quart.Response(error_bodys['no_perms'], 403)


@users_me.patch('')
async def edit_user():
    auth = quart.request.headers.get('Authorization', '')
    allow = False
    async for session_id in users.find({'session_ids': [auth]}):
        if session_id == quart.request.headers.get('Authorization'):
            allow = True

    if allow == False:
        return quart.Response(error_bodys['no_auth'], status=401)

    d: dict = await quart.request.get_json()

    if d.get('separator'):
        if len(d['separator']) != 4:
            return quart.Response(error_bodys['invalid_data'], 400)
        elif d['separator'] == 0000:
            return quart.Response(error_bodys['invalid_data'], 400)

    given = {}
    up = await users.find_one({'session_ids': [auth]})

    if d.get('username'):
        given['username'] = d.pop('username')

    if d.get('separator'):
        given['separator'] = d.pop('sparator')

    if d.get('email'):
        given['email'] = d.pop('email')

    if d.get('password'):
        given['password'] = get_hash_for(d.pop('password'))

    if d.get('bio'):
        given['bio'] = d.pop('bio')
    
    if d.get('accept_friend_requests'):
        await user_settings.update_one({'id': up['id']}, {'accept_friend_requests': bool(d.pop('accept_friend_requests'))})

    if given == {}:
        return quart.Response(error_bodys['invalid_data'], 400)

    await users.update_one({'id': up['id']}, given)

    return quart.Response(json.loads(given), 200)

@users_me.post('/blocks/<int:user_id>')
async def block_user(user_id: int):
    user = await check_session_(quart.request.headers.get('Authorization'))

    if user == None:
        return quart.Response(error_bodys['no_auth'], 401)
    
    to = await users.find_one({'id': user_id})

    if to == None:
        return quart.Response(error_bodys['not_found'], 404)
    
    await users.update_one({'id': user['id']}, {'blocked_users': [user_id]})

    return quart.Response(error_bodys['no_content'], 204)

@users_me.delete('/blocks/<int:user_id>')
async def unblock_user(user_id: int):
    user = await check_session_(quart.request.headers.get('Authorization'))

    if user == None:
        return quart.Response(error_bodys['no_auth'], 401)
    
    to = await users.find_one({'id': user_id})

    if to == None:
        return quart.Response(error_bodys['not_found'], 404)
    
    if to['id'] not in user['blocked_users']:
        return quart.Response(error_bodys['no_perms'], 403)
    
    await users

@users_me.get('')
async def get_me():
    auth = quart.request.headers.get('Authorization')
    cur = None
    find = await users.find_one({'session_ids': [auth]})

    try:
        for session_id in find['session_ids']:
            if session_id == quart.request.headers.get('Authorization'):
                cur = {
                    'id': find['id'],
                    'username': find['username'],
                    'separator': find['separator'],
                    'bio': find['bio'],
                    'avatar_url': find['avatar_url'],
                    'banner_url': find['banner_url'],
                    'flags': find['flags'],
                    'verified': find['verified'],
                    'system': find['system'],
                }
    except TypeError:
        return quart.Response(error_bodys['no_auth'], status=401)

    if cur is None:
        return quart.Response(error_bodys['no_auth'], status=401)

    return quart.Response(json.dumps(cur))


@users_me.post('/sessions')
async def create_session():
    login: dict = await quart.request.get_json(True)

    u = await users.find_one(
        {
            'email': login.get('email', ''),
            'password': get_hash_for(login.get('password', 'nan')),
        }
    )

    if u == None:
        return quart.Response(error_bodys['no_auth'], status=401)

    session_id = snowflake_with_blast()

    await users.find_one_and_update(
        {
            'email': login.get('email'),
            'password': get_hash_for(login.get('password', 'nan')),
        },
        {'session_ids': [session_id]},
    )
    return quart.Response(json.dumps({'session_id': session_id}), 201)


@users_me.delete('/sessions/<int:session_id>')
async def delete_session(session_id: int):
    login: dict = await quart.request.get_json(True)

    u = await users.find_one(
        {
            'email': login.get('email', ''),
            'password': get_hash_for(login.get('password', 'nan')),
        }
    )

    if u == None:
        return quart.Response(error_bodys['no_auth'], status=401)

    await users.replace_one({'session_ids': [session_id]}, {'session_ids': []})
    return quart.Response(json.dumps({'completed': True}), 410)