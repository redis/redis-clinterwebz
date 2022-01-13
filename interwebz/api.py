from shlex import split
import sys
from typing import Any

from redis import exceptions

from .pagesession import PageSession
from .redis import NameSpacedRedis

max_batch_size = 20
max_arguments = 25
max_argument_size = 256


def reply(value:Any, error:bool) -> dict:
    return {
        'value': value,
        'error': error,
    }


def deny(message:str) -> dict:
    return reply(f'{message} allowed on the interwebz', True)


def snip(value:str, init:int = 0) -> str:
    signature = '... (full value snipped by the interwebz)'
    return value[:max_argument_size - init - len(signature)] + signature


def sanitize_exceptions(argv:list) -> Any:
    # TODO: potential "attack" vectors: append, bitfield, sadd, zadd, xadd, hset, lpush/lmove*, sunionstore, zunionstore, ...
    cmd_name = argv[0].lower()
    argc = len(argv)
    if cmd_name == 'setbit' and argc == 4:
        try:
            offset = int(argv[2])
            max_offset = max_argument_size * 8
            if offset > max_offset:
                return f'offset too big - only up to {max_offset} bits allowed'
        except ValueError:
            pass  # Let the Redis server return a proper parsing error :)
    elif cmd_name == 'setrange' and argc == 4:
        try:
            offset = int(argv[2])
            if offset > max_argument_size:
                return f'offset too big - only up to {max_argument_size} bytes allowed'
            argv[3] = argv[3][:(max_argument_size - offset + 1)]
        except ValueError:
            argv[3] = ''
    elif cmd_name in  ['quit', 'hello', 'reset', 'auth']:
        return f'the \'{argv[0]}\' command is not'

    return None


def verify_commands(commands:Any) -> Any:
    if type(commands) is not list:
        return 'It posts commands as a list', 400
    if len(commands) > max_batch_size:
        return deny(f'batch is too large. Only up to {max_batch_size} commands')
    return None


def execute_commands(dburl:str, session: PageSession, commands:list) -> list:
    try:
        client = NameSpacedRedis.from_url(dburl, decode_responses=True)
    except exceptions.RedisError as e:
        return [reply(str(e), True)]

    rep = []
    for command in commands:
        try:
            argv = split(command)
        except ValueError as e:
            rep.append(reply(str(e), True))
            continue

        argc = len(argv)
        if argc == 0:
            continue
        if argc > max_arguments:
            rep.append(deny(f'too many arguments - only up to {max_arguments}'))
            continue

        stronly = True
        for i in range(argc):
            stronly = type(argv[i]) is str
            if not stronly:
                break
            if len(argv[i]) > max_argument_size:
                argv[i] = snip(argv[i])
        if not stronly:
            rep.append(deny(f'only string arguments are allowed'))
            continue

        error = sanitize_exceptions(argv)
        if error is not None:
            rep.append(deny(error))
            continue

        try:
            resp = client.execute_namespaced(session, argv)
            rep.append(reply(resp, False))
        except Exception as e:
            rep.append(reply(str(e), True))

    return rep

