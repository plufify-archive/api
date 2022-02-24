import json
import dotenv
import logging
import quart_rate_limiter
from quart import Quart, Response
from .rest.servers import channels
from .rest.users import create_user, get_me, edit_user

app = Quart(__name__)
dotenv.load_dotenv()
logging.basicConfig(level=logging.DEBUG)

rates = quart_rate_limiter.RateLimiter(app=app)

# users
app.add_url_rule('/v1/users/@me', view_func=create_user, methods=['POST'])
app.add_url_rule('/v1/users/@me', view_func=get_me, methods=['GET'])
app.add_url_rule('/v1/users/@me', view_func=edit_user, methods=['PATCH'])

# guilds

## channels
app.add_url_rule('/v1/servers/channels', view_func=channels.create_channel, methods=['POST'])

@app.route('/')
async def health_check():
    d = {'http': 'https://hatsu.vincentrps.xyz', 'gateway': 'wss://hatsu.vincentrps.xyz'}
    return Response(json.dumps(d), 200)