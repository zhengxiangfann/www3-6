import asyncio
import os
import inspect
import logging
import functools


from urllib import parse
from aiohttp import web



def get(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator


def post(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator


def get_required_kw_args(fn):

    # 如果url处理函数需要传入关键字参数，且默认是空得话，获取这个key
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)

def get_named_kw_args(fn):

    # 如果url处理函数需要传入关键字参数，获取这个key
    args=[]
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


def has_named_kw_args(fn):

    '判断是否有关键字参数'
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


def has_var_kw_args(fn):

    # 判断是否有关键字参数
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError('request parameter must be the last named parameter in function: %s%s'%(fn.__name__, str(sig)))
    return found



class RequestHandler(object):

    def __init__(self, app, fn):

        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_args(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    async def __call__(self, request):
            kw = None
            # 判断是否存在参数
            if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:

                # ------阶段1：POST/GET方法下正确解析request的参数，包括位置参数和关键字参数----
                #
                # 如果是POST提交请求的类型(通过content_type可以指定)可以参考我的博客：http://kaimingwan.com/post/python/postchang-jian-qing-qiu-fang-shi-qian-xi
                if request.method == 'POST':
                    # 判断是否村存在Content-Type（媒体格式类型），一般Content-Type包含的值：
                    # text/html;charset:utf-8;
                    if not request.content_type:
                        return web.HTTPBadRequest(text='Missing Content-Type.')
                    ct = request.content_type.lower()
                    # 如果请求json数据格式
                    if ct.startswith('application/json'):
                        # params = yield from request.json()
                        params = await request.json()
                        # 是否参数是dict格式，不是的话提示JSON BODY出错
                        if not isinstance(params, dict):
                            return web.HTTPBadRequest(text='JSON body must be object.')
                        kw = params  # 正确的话把request的参数信息给kw
                    # POST提交请求的类型
                    elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                        # params = yield from request.post()  # 调用post方法，注意此处已经使用了装饰器
                        params = await request.post()  # 调用post方法，注意此处已经使用了装饰器
                        kw = dict(**params)
                    else:
                        return web.HTTPBadRequest(text='Unsupported Content-Type: %s' % request.content_type)
                # 如果是GET提交请求的类型
                if request.method == 'GET':  # get方法比较简单，直接后面跟了string来请求服务器上的资源
                    qs = request.query_string
                    if qs:
                        kw = dict()
                        # 该方法解析url中?后面的键值对内容保存到kw
                        # 解析一个类型为application/x-www-form-urlencoded的查询字符串
                        # 返回一个dict，k是查询变量名称，值是每个名称的值列表
                        # 如{'wd': ['python'], 'ie', [utf-8]}
                        for k, v in parse.parse_qs(qs, True).items():
                            kw[k] = v[0]

            # 判断kw是够为空

            if kw is None:  # 没有从Request对象中获取到必要参数
                # 此时kw指向match_info属性，一个变量标识符的名字的dict列表。Request中获取的命名关键字参数必须要在这个dict当中

                kw = dict(**request.match_info)

            # kw不为空时
            else:
                # 如果从Request对象中获取到参数了
                # 当没有可变参数，有命名关键字参数时候，kw指向命名关键字参数的内容
                if not self._has_var_kw_arg and self._named_kw_args:
                    # remove all unamed kw: 删除所有没有命名的关键字参数
                    copy = dict()
                    for name in self._named_kw_args:
                        if name in kw:
                            copy[name] = kw[name]
                    kw = copy
                # check named arg: 检查命名关键字参数的名字是否和match_info中的重复
                for k, v in request.match_info.items():
                    if k in kw:  # 命名参数和关键字参数有名字重复
                        logging.warning(
                            'Duplicate arg name in named arg and kw args: %s' % k)
                        # kw中加入match_info中的值
                    kw[k] = v
            # 如果有request这个参数，则把request对象加入kw['request']
            if self._has_request_arg:
                kw['request'] = request
            # check required kw: 检查是否有必要关键字参数
            if self._required_kw_args:
                for name in self._required_kw_args:
                    if name not in kw:
                        return web.HTTPBadRequest(text='Missing argument: %s' % name)
            logging.info('call with args: %s' % str(kw))
            # 调用handler，并返回response
            try:
                # r = yield from self._func(**kw)
                r = await self._func(**kw)
                return r
            except BaseException as e:
                return dict(error=e.error, data=e.data, message=e.message)


    # # 3.6 版本之前的写法
    # # @asyncio.coroutine
    # # def __call_(self, request):
    #
    # async def __call_(self, request):
    #     kw = None
    #     # 判断参数
    #     if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
    #         if request.method == 'POST':
    #             if not request.content_type:
    #                 return web.HTTPBadRequest(text='Missing Content-Type')
    #
    #             ct = request.content_type.lower()
    #
    #             if ct.startswith('application/json'):
    #                 # params = yield from request.json() 3.6  以前版本写法
    #                 params = await request.json()
    #                 if not isinstance(params, dict):
    #                     return web.HTTPBadRequest(text='JSON body must be object.')
    #                 kw = params
    #             elif ct.startswith('application/x-www-form-urlencoded') or c.startswith('multipart/form-data'):
    #                 prams = await request.post()
    #             else:
    #                 return web.HTTPBadRequest(text='Unsupported Content-type:%s'%request.content_type)
    #         if request.method == 'GET':
    #             qs = request.query_string
    #             if qs:
    #                 kw = dict()
    #
    #                 for k, v in parse.parse_qs(qs, True).items():
    #                     kw[k] = v[0]
    #
    #     if kw is None:
    #         kw = dict(**request.match_info)
    #
    #     else:
    #         if not self._has_var_kw_arg and self._named_kw_args:
    #             copy = dict()
    #             for name in self._named_kw_args:
    #                 if name in kw:
    #                     copy[name] = kw[name]
    #             kw = copy
    #
    #         for k, v in request.match_info.items():
    #             if k in kw:
    #                 logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
    #             kw[k] = v
    #
    #
    #     if self._has_request_arg:
    #         kw['request'] = request
    #
    #     if self._required_kw_args:
    #         for name in self._required_kw_args:
    #             if name not in kw:
    #                 return web.HTTPBadRequest(text='Missing argument:%s'%name)
    #     logging.info('call with args:%s'%str(kw))
    #
    #     try:
    #         # field from slef._func(kw)
    #         r = await self._func(**kw)
    #         return r
    #     except BaseException  as e:
    #         return dict(error=e.error, data=e.data, message=e.message)



def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s'%('/static/', path))


# def add_route(app, fn):
#     method = getattr(fn, '__method__', None)
#     path = getattr(fn, '__route__', None)
#     if path is None or method is None:
#         raise ValueError('@get or @post not defined in %s.'%str(fn))
#
#     if not asyncio.iscoroutine(fn) and not inspect.isgeneratorfunction(fn):
#         fn = asyncio.coroutine(fn)
#
#     logging.info('add route %s %s => %s (%s)'%(method, path, fn.__name__, ','.join(inspect.signature(fn).parameters.keys())))
#     logging.info("method={},path={},".format(method, path))
#     app.router.add_route(method, path, RequestHandler(app,fn))


# 把URL请求处理函数注册到app
def add_route(app, fn):

# 获取'__method__'和'__route__'属性，如果有空则抛出异常
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.' % str(fn))
    # 判断fn是不是协程和生成器
    if not asyncio.iscoroutine(fn) and not inspect.isgeneratorfunction(fn):
        # 都不是的话，强行修饰为协程
        fn = asyncio.coroutine(fn)
    logging.info('add route %s %s => %s (%s)' % (
        method, path, fn.__name__, ', '.join(inspect.signature(fn).parameters.keys())))
    # 正式注册为相应的url处理方法
    # 处理方法为RequestHandler的自省函数 '__call__'
    app.router.add_route(method, path, RequestHandler(app, fn))





def add_routes(app, module_name):
    n = module_name.rfind('.')
    logging.info('n = %s', n)

    if n == (-1):
        mod = __import__(module_name, globals(), locals())
        logging.info('globals = %s', globals()['__name__'])

    else:
        name = module_name[n + 1:]
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)

    for attr in dir(mod):
        # 如果是以'_'开头的，一律pass，我们定义的处理方法不是以'_'开头的
        if attr.startswith('_'):
            continue
        # 获取到非'_'开头的属性或方法
        fn = getattr(mod, attr)
        # 取能调用的，说明是方法
        if callable(fn):
            # 检测'__method__'和'__route__'属性
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path:
                # 如果都有，说明使我们定义的处理方法，加到app对象里处理route中
                add_route(app, fn)




