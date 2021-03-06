import json
import datetime
from quart import Blueprint, Response, request

from ..snowflakes import snowflake
from ..database import channels, users, send_message, get_message as find_message, members, guilds, delete_message as remove_message, edit_message as message_edit
from ..data_bodys import error_bodys as err
from ..permissions import Permissions
from ..data_bodys import mention, get_regexed_id
from ...gateway import send_notification, guild_dispatch

msgs = Blueprint('messages-v3', __name__)

def _verify_embed(d: dict):
    ret = {
        'fields': []
    }
    if d.get('title'):
        if len(d.get('title')) > 40:
            pass
        else:
            ret['title'] = d.pop('title')
    if d.get('description'):
        if len(d.get('description')) > 200:
            pass
        else:
            ret['description'] = d.pop('description')
    if d.get('url'):
        if not isinstance(d.get('url'), str):
            pass
        else:
            url: str = d.get('url')
            if not url.startswith('http') or not url.startswith('https'):
                pass
            else:
                ret['url'] = url
    if d.get('timestamp'):
        if not isinstance(d.get('timestamp'), str):
            pass
        else:
            dt = datetime.datetime.fromisoformat(d.pop('timestamp'))
            ret['timestamp'] = dt.isoformat()
    if d.get('color'):
        if not isinstance(d.get('color'), int):
            pass
        else:
            ret['color'] = d.pop('color')
    if d.get('fields'):
        if not isinstance(d.get('fields'), list[dict]):
            pass
        else:
            for f in d.pop('fields'):
                if not f.get('name') or not f.get('value'):
                    pass
                else:
                    ret['fields'].append({'name': d.pop('name'), 'value': d.pop('value')})
    if d.get('author'):
        if not isinstance(d.get('author'), dict):
            pass
        else:
            author: dict = d.pop('author')

            if not author.get('name'):
                pass
            else:
                ret['author'] = {
                    'name': author.pop('name')
                }

                if author.get('url'):
                    ret['author']['url'] = author.pop('url')
                if author.get('avatar_url'):
                    ret['author']['avatar_url'] = author.pop('avatar_url')

    return ret

@msgs.post('/<channel_id>/messages/create')
async def create_message(channel_id):
    auth = request.headers.get('Authorization', '')
    user = await users.find_one({'session_ids': [auth]})

    if user == None:
        return Response(err['no_auth'], 401)

    channel = await channels.find_one({'_id': channel_id})

    if channel == None:
        return Response(err['not_found'], 404)

    if channel['type'] == 1:
        return Response(err['invalid_data'], 400)

    member = await members.find_one({'id': user['_id'], 'guild_id': channel['guild_id']})

    if member == None:
        return Response(err['not_found'], 404)

    guild = await guilds.find_one({'_id': channel['guild_id']})

    if member['roles'] == []:
        v = guild['default_permission']
    else:
        v = member['roles'][0]['permissions']

    p = Permissions(v)

    if not p.send_messages and not member['owner']:
        return Response(err['no_perms'], 403)

    d: dict = await request.get_json()

    member['user'].pop('session_ids')
    member['user'].pop('email')
    member['user'].pop('password')
    member['user'].pop('email_verified')
    member['user'].pop('blocked_users')
    member.pop('_id')
    member['_id'] = member['id']
    member.pop('id')
    member.pop('guild_id')

    data = {
        '_id': snowflake(),
        'author': member,
        'content': '',
        'tts': False,
        'embeds': [],
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    if d.get('content'):
        data['content'] = d.pop('content')

    if d.get('tts'):
        if isinstance(d.get('tts'), bool):
            data['tts'] = d.pop('tts')
        else:
            return Response(err['invalid_data'], 400)
        
    if d.get('embeds'):
        if isinstance(d.get('embeds'), list[dict]):
            embeds = []
            for embed in d.pop('embeds'):
                if isinstance(embed, dict):
                    e = _verify_embed(embed)

                    if e == {'fields': []}:
                        pass
                    else:
                        embeds.append(e)

            for r in embeds:
                if r == None:
                    return Response(err['invalid_data'], 400)

            data['embeds'] = embeds
        else:
            return Response(err['invalid_data'], 400)

    if len(data['content']) > 5000:
        return Response(err['invalid_data'], 400)

    await send_message(channel_id=channel_id, data=data)

    await guild_dispatch(guild['_id'], 'MESSAGE_CREATE', data)

    mentions = mention.findall(data['content'])

    # prevent spam pings
    _last_ids = []

    for m in mentions:
        id = get_regexed_id(m)
        if id in _last_ids:
            pass
        else:
            _last_ids.append(id)
            await send_notification('MENTION', data, id)
    
    del _last_ids

    return Response(json.dumps(data), 201)

@msgs.patch('/<channel_id>/messages/<message_id>')
async def edit_message(channel_id, message_id):
    auth = request.headers.get('Authorization', '')
    user = await users.find_one({'session_ids': [auth]})

    if user == None:
        return Response(err['no_auth'], 401)

    channel = channels.find_one({'_id': channel_id})

    if channel == None:
        return Response(err['not_found'], 404)

    member = await members.find_one({'_id': user['_id'], 'guild_id': channel['guild_id']})

    if member == None:
        return Response(err['no_perms'], 403)

    message = await find_message(channel['id'], message_id)

    if message == None:
        return Response(err['not_found'], 404)

    if message['author'] != member:
        return Response(err['no_perms'], 403)

    edited_ms = await message_edit(channel['id'], message['id'])
    await guild_dispatch(channel['guild_id'], 'MESSAGE_EDIT', message)

    return Response(json.dumps(edited_ms.raw_result))

@msgs.get('/<channel_id>/messages/<message_id>')
async def get_message(channel_id, message_id):
    auth = request.headers.get('Authorization', '')
    user = await users.find_one({'session_ids': [auth]})

    if user == None:
        return Response(err['no_auth'], 401)

    channel = await channels.find_one({'_id': channel_id})

    if channel == None:
        return Response(err['not_found'], 404)

    member = await members.find_one({'id': user['_id'], 'guild_id': channel['guild_id']})

    if member == None:
        return Response(err['not_found'], 404)

    guild = await members.find_one({'id': channel['guild_id']})

    if member['roles'] == []:
        v = guild['default_permission']
    else:
        v = member['roles'][0]['permissions']

    p = Permissions(v)

    gtg = False

    if p.read_message_history:
        gtg = True

    for b in channel['bypass']:
        if user['_id'] == b['_id']:
            v = Permissions(b['value'])
            if v.read_message_history:
                gtg = True
            else:
                gtg = False

    if member['owner']:
        gtg = True

    if gtg is False:
        return Response(err['no_perms'], 403)

    ms = await find_message(channel_id, message_id)

    if ms == None:
        return Response(err['not_found'], 404)

    return Response(json.dumps(ms), 200)

@msgs.delete('/<channel_id>/messages/<message_id>')
async def delete_message(channel_id, message_id):
    auth = request.headers.get('Authorization', '')
    user = await users.find_one({'session_ids': [auth]})

    if user == None:
        return Response(err['no_auth'], 401)

    channel = await channels.find_one({'_id': channel_id})

    if channel == None:
        return Response(err['not_found'], 404)

    member = await members.find_one({'id': user['_id'], 'guild_id': channel['guild_id']})

    if member == None:
        return Response(err['no_perms'], 403)

    message = await find_message(channel['_id'], message_id)

    if message == None:
        return Response(err['not_found'], 404)

    if member['roles'] == []:
        guild = await guilds.find_one({'_id': channel['guild_id']})
        v = guild['default_permission']
    else:
        v = member['roles'][0]['permissions']

    p = Permissions(v)
    bypassed = False

    for bypass in channel['bypass']:
        if user['_id'] == bypass['_id']:
            _p = Permissions(bypass['value'])
            if _p.manage_messages:
                bypassed = True

    if not p.manage_messages and not bypassed and not member['owner']:
        return Response(err['no_perms'], 403)

    # TODO: Audit Log?
    await remove_message(channel['_id'], message['_id'])
    await guild_dispatch(channel['guild_id'], 'MESSAGE_DELETE', message)

    return Response(json.dumps(message))
