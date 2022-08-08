from shlex import split
from typing import Any

from redis import exceptions

from .pagesession import PageSession
from .redis import NameSpacedRedis
from math import log
from math import log2
from math import pow

max_batch_size = 20
max_arguments = 25
max_argument_size = 256
max_bits_allowed = 16000
max_bytes_allowed = max_bits_allowed * 8

ts_cmds = ['ts.create','ts.add','ts.alter','ts.incrby','ts.decrby']

def reply(value: Any, error: bool) -> dict:
    return {
        'value': value,
        'error': error,
    }


def deny(message: str) -> dict:
    return reply(f'{message} allowed on the interwebz', True)


def snip(value: str, init: int = 0) -> str:
    signature = '... (full value snipped by the interwebz)'
    return value[:max_argument_size - init - len(signature)] + signature


def sanitize_exceptions(argv: list) -> Any:
    # TODO: potential "attack" vectors: append, bitfield, sadd, zadd, xadd, hset, lpush/lmove*, sunionstore, zunionstore, ...
    cmd_name = argv[0].lower()
    argc = len(argv)
    argv_lower = [x.lower()  for x in argv]
    if cmd_name == 'setbit' and argc == 4:
        try:
            offset = int(argv[2])
            max_offset = max_argument_size * 8
            if offset > max_offset:
                return f'offset too big - only up to {max_offset} bits allowed'
        except ValueError:
            pass  # Let the Redis server return a proper parsing error :)
    elif cmd_name == 'bf.reserve' and argc >=4 :
        try:
            error_rate = float(argv[2])
            capacity = float(argv[3])
            return verify_bf(error_rate, capacity, argv, argv_lower, cmd_name)
        except Exception as e:
            raise e
    elif cmd_name == 'bf.insert':
        capacity_idx = argv_lower.index('capacity')
        error_idx = argv_lower.index('error')
        res = None
        if(capacity_idx >= 1) and error_idx >= 1 and argc> max(capacity_idx, error_idx):
            res = verify_bf(float(argv[error_idx+1]), float(argv[capacity_idx+1]), argv, argv_lower, cmd_name)
    elif cmd_name == 'cms.initbydim' or cmd_name == 'cms.initbyprob':
        return verify_cms(argv, cmd_name)
    elif cmd_name == 'cf.reserve' or cmd_name == 'cf.insert' or cmd_name == 'cf.insertnx':
        return verify_cf(argv_lower, cmd_name)
    elif cmd_name == 'topk.reserve':
        return verify_topk(argv)
    elif cmd_name in ts_cmds:
        return verify_ts_create(argv_lower)
    elif cmd_name == 'setrange' and argc == 4:
        try:
            offset = int(argv[2])
            if offset > max_argument_size:
                return f'offset too big - only up to {max_argument_size} bytes allowed'
            argv[3] = argv[3][:(max_argument_size - offset + 1)]
        except ValueError:
            argv[3] = ''
    elif cmd_name in ['quit', 'hello', 'reset', 'auth']:
        return f'the \'{argv[0]}\' command is not'

    return None

def verify_ts_create(argv_lower) -> Any:    
    illegal_arguments = []
    if 'chunk_size' in argv_lower:
        illegal_arguments.append('chunk_size')
    if 'encoding' in argv_lower:
        illegal_arguments.append('encoding')
    if 'labels' in argv_lower:
        illegal_arguments.append('labels')
    if len(illegal_arguments) == 1:
        return f'Argument "{illegal_arguments[0]}" is not'
    elif len(illegal_arguments) > 0:
        return f'Arguments {illegal_arguments} are not'

def verify_topk(argv) -> Any:
    k = int(argv[2])
    width = 0
    depth = 0
    if len(argv) > 3:
        width = int(argv[3])
        depth = int(argv[4])

    bytes_required = (k * 13 + width * depth * 8)
    if bytes_required > max_bytes_allowed:
        return f'TOPK.RESERVE requests more than allowed bytes, requested {bytes_required} only {max_bytes_allowed}'

def verify_cf(argv_lower, cmd_name) -> Any:
    capacity = 1024
    bucket_size = 1
    if cmd_name == 'cf.reserve':
        if 'bucketsize' in argv_lower and len(argv_lower) > argv_lower.index('bucketsize')+1:
            bucket_size = int(argv_lower[argv_lower.index('bucketsize')+1])
        capacity = int(argv_lower[2])
    elif cmd_name == 'cf.insert':
        if 'capacity' in argv_lower and len(argv_lower) > argv_lower.index('capacity') + 1:
            capacity = int(argv_lower[argv_lower.index('capacity') + 1])
    if 'expansion' in argv_lower:
        return 'Use of the EXPANSION argument is not'
    num_bits_required = ceil((log2(1./((2.*bucket_size)/255))/.955) * capacity)
    if num_bits_required > max_bits_allowed:
        return f'{cmd_name} requests more thant allowed bits, requested {num_bits_required} only {max_bits_allowed}'

def verify_cms(argv, cmd_name) -> Any:
    
    width = 0
    depth = 0
    if cmd_name == 'cms.initbyprob':
        width = ceil(2./float(argv[2]))
        print(argv[3])
        depth = ceil(log10(float(argv[3]))/log10(.5))
    elif cmd_name == 'cms.initbydim':
        width = int(argv[2])
        depth = int(argv[3])
    num_bits_required = width * depth * 64
    print(num_bits_required)
    if num_bits_required > max_bits_allowed:
        return f'{cmd_name} requests more thant allowed bits, requested {num_bits_required} only {max_bits_allowed}'
    return None


def verify_bf(error_rate, capacity, argv, argv_lower, cmd_name) -> Any:
    bits_per_item = -log2(error_rate)/(pow(log(2), 2))
    num_bits_required = bits_per_item * capacity
    if num_bits_required > max_bits_allowed:
        return f'{cmd_name} asking for too much memory, {int(num_bits_required)} bits requested, only {max_bits_allowed} '
    elif 'expansion' in argv_lower:
        return 'Use of the EXPANSION argument is not'
    elif not 'nonscaling' in argv_lower:
        if 'items' in argv_lower:
            items_idx = argv_lower.index('items')
            argv.insert(items_idx, 'NONSCALING')
        else:
            argv.append('NONSCALING')
    return None

def verify_commands(commands: Any) -> Any:
    if type(commands) is not list:
        return 'It posts commands as a list', 400
    if len(commands) > max_batch_size:
        return deny(f'batch is too large. Only up to {max_batch_size} commands')
    return None


def execute_commands(client: NameSpacedRedis, session: PageSession, commands: list) -> list:
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
            rep.append(
                deny(f'too many arguments - only up to {max_arguments}'))
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
