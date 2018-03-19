import asyncio,re,time,json,logging,hashlib,base64
from webframe import get,post
from aiohttp import web
# import markdown2

#用户登录cookie
COOKIE_NAME = 'fefefeafafefe'
_COOKIE_KEY = 'fdfdfdfafefefefeaf'

@get('/')
async def index(request):
    return "indexs"
