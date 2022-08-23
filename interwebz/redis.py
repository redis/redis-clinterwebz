from typing import Any
from redis import Redis, exceptions
from .pagesession import PageSession
from abc import ABC
from abc import abstractmethod

class FindKeysBase(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def get_keys_data(self, argv: list, start_at: int):
        pass

class FindKeysRange():
    def __init__(self, step: int, lastkey: int, limit: int):
        super().__init__()
        self.step = step
        self.lastkey = lastkey
        self.limit = limit

    def get_keys_data(self, argv: list, start_at: int):
        if self.lastkey >= 0:
            last = start_at + self.lastkey
        else:
            if self.limit != 0:
                last = start_at + (int((len(argv) - start_at)/self.limit) + self.lastkey)
            else:
                last = len(argv) + self.lastkey
        return start_at, last, self.step

class FindKeysNum():
    def __init__(self, step: int, firstkey: int, keynumidx: int):
        super().__init__()
        self.step = step
        self.firstkey = firstkey
        self.keynumidx = keynumidx

    def get_keys_data(self, argv: list, start_at: int):
        keynum = argv[start_at + self.keynumidx]
        if type(keynum) is not int:
            return 0, 0, 0
        first = start_at + self.firstkey
        last = first + keynum - 1
        return first, last, self.step

class BeginSearchBase(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def get_first(self, argv: list):
        pass

class BeginSearchIndex(BeginSearchBase):
    def __init__(self, index: int):
        super().__init__()
        self.index = index

    def get_first(self, argv: list):
        return self.index

class BeginSearchKeyord(BeginSearchBase):
    def __init__(self, keyword: str, start_from: int):
        super().__init__()
        self.keyword = keyword
        self.start_from = start_from

    def get_first(self, argv: list):
        start_index = self.start_from if self.start_from > 0 else len(argv) + self.start_from
        end_index = len(argv) - 1 if self.start_from > 0 else 0
        i = start_index
        incr = 1 if start_index <= end_index else -1
        while i != end_index:
            if i > len(argv):
                break
            if argv[i] == self.keyword:
                return i + 1
            i += incr
        return 0

class KeySpec():
    def __init__(self, begin_search: BeginSearchBase, find_keys: FindKeysBase):
        self.begin_search = begin_search
        self.find_keys = find_keys

class CommandSpec():
    def __init__(self, arity: int, flags: list):
        self.arity = arity
        self.moveable_keys = 'movablekeys' in flags
        self.key_specs = []

    def add_key_spec(self, key_spec: KeySpec):
        self.key_specs.append(key_spec)

    def get_keys_possitions(self, argv: list):
        ret = set()
        for key_spec in self.key_specs:
            argc = len(argv)
            start_at = key_spec.begin_search.get_first(argv)
            if start_at == 0:
                continue
            
            first, last, step = key_spec.find_keys.get_keys_data(argv, start_at)
            if first == 0:
                continue

            for i in range(first, last + 1, step):
                if i >= argc:
                    # Module and negative arity commands (TODO: find out if module command)
                    if self.arity < 0:
                        continue
                    else:
                        # Command key specs do not match arguments
                        raise exceptions.RedisError(
                            'keys do not match the command\'s key_specs')
                ret.add(i)
        return ret

class NameSpacedRedis(Redis):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.commands = {}
        self._get_commands()

    @staticmethod
    def _pairs_to_dict(response: list, recursive=False) -> dict:
        if response is None:
            return {}
        if type(response) != list:
            return response
        return {response[i]:NameSpacedRedis._pairs_to_dict(response[i + 1]) if recursive else response[i + 1] for i in range(0, len(response) - 1, 2)}

    @staticmethod
    def _key_spec_to_dict(response: list) -> dict:
        ks = NameSpacedRedis._pairs_to_dict(response)
        for k in ['begin_search', 'find_keys']:
            ks[k] = NameSpacedRedis._pairs_to_dict(ks[k], True)
        return ks

    def _parse_command_response(self, response, **options):
        for command in response:
            command_spec = CommandSpec(command[1], command[2])
            for s in command[8]:
                key_spec = NameSpacedRedis._key_spec_to_dict(s) # spec start at possition 8
                begin_type = key_spec['begin_search']['type']
                begin_search = None
                if begin_type == 'index':
                    begin_search = BeginSearchIndex(key_spec['begin_search']['spec']['index'])
                elif begin_type == 'keyword':
                    keyword = key_spec['begin_search']['spec']['keyword']
                    start_from = key_spec['begin_search']['spec']['startfrom']
                    begin_search = BeginSearchKeyord(keyword, start_from)

                if begin_search is None:
                    continue

                find_type = key_spec['find_keys']['type']
                find_keys = None
                if find_type == 'range':
                    step = key_spec['find_keys']['spec']['keystep']
                    lastkey = key_spec['find_keys']['spec']['lastkey']
                    limit = key_spec['find_keys']['spec']['limit']
                    find_keys = FindKeysRange(step, lastkey, limit)
                elif find_type == 'keynum':
                    step = key_spec['find_keys']['spec']['keystep']
                    firstkey = key_spec['find_keys']['spec']['firstkey']
                    keynumidx = key_spec['find_keys']['spec']['keynumidx']
                    find_keys = FindKeysNum(step, firstkey, keynumidx)

                if find_keys is None:
                    continue

                key_spec = KeySpec(begin_search, find_keys)
                command_spec.add_key_spec(key_spec)
            self.commands[command[0]] = command_spec

        for c in self.commands.keys():
            # make sure all responses will be returned as is
            self.set_response_callback(c, lambda res, **options: res)

    def _get_commands(self):
        self.set_response_callback('COMMAND', self._parse_command_response)
        self.execute_command('COMMAND')

    @staticmethod
    def _keys_index(argv: list, cmd: CommandSpec) -> list:
        return cmd.get_keys_possitions(argv)
        
    @staticmethod
    def _strip_id_from_keys(id: str, keys: list) -> list:
        return [x[len(str(id))+1:] for x in keys]

    def execute_namespaced(self, session: PageSession, argv: list) -> Any:
        # try:
        # Locate the command in the SSOT
        cmd_name = argv[0].lower()
        is_subcmd = False
        if cmd_name not in self.commands:
            raise exceptions.RedisError(f'unknown command \'{argv[0]}\'')
        # Check if this is a subcommand
        argc = len(argv)
        if argc > 1:
            subcmd_name = f'{cmd_name} {argv[1].lower()}'
            is_subcmd = subcmd_name in self.commands
            if is_subcmd:
                cmd_name = subcmd_name

        # Pre-processing
        # TODO: patterns may be extracted the from command arguments pecs, and if so
        # we can add support for `SORT` and potential future commands automatically.
        cmd = self.commands[cmd_name]
        options = {}
        if cmd_name == 'dump':
            from redis.client import NEVER_DECODE
            options[NEVER_DECODE] = []

        if cmd_name == 'keys' and argc == 2:
            # Namespace the key pattern
            argv[1] = f'{session}:{argv[1]}'
        elif cmd_name == 'scan':
            # Namespace all key patterns (even though only the last one really
            # matters), or slap a namespaced pattern if are given.
            match = False
            for i in range(argc-1):
                if argv[i].lower() == 'match':
                    argv[i+1] = f'{session}:{argv[i+1]}'
                    match = True
            if not match:
                argv.append('MATCH')
                argv.append(f'{session}:*')
                argc += 2
        elif cmd_name in ['flushdb', 'flushall']:
            # Much easier than finding them keys
            session.relogin()
            return 'OK'
        elif cmd.moveable_keys:
            get_keys_args = argv.copy()
            get_keys_args.insert(0, 'GETKEYS')
            get_keys_args.insert(0, "COMMAND")
            mapping = self.execute_command(*get_keys_args)
            for arg in mapping:
                idx = argv.index(arg)
                argv[idx] = f'{session}:{arg}'
        else:
            # Quickly check arity
            if cmd.arity > 0 and argc != cmd.arity:
                raise exceptions.RedisError(
                    'ERR wrong number of arguments for command')
            elif cmd.arity < 0 and argc < abs(cmd.arity):
                raise exceptions.RedisError(
                    'ERR wrong number of arguments for command')
            # Namespace the key names
            keys_index = self._keys_index(argv, cmd)
            for i in keys_index:
                argv[i] = f'{session}:{argv[i]}'

        # Send the command
        rep = self.execute_command(*argv, **options)

        # Post-processin'
        if cmd_name == 'keys':
            rep = self._strip_id_from_keys(session, rep)
        elif cmd_name == 'scan':
            rep[1] = self._strip_id_from_keys(session, rep[1])
        elif cmd_name in ['lmpop','zmpop'] and rep is not None and len(rep) == 2:
            rep[0] = self._strip_id_from_keys(session, [rep[0]])[0]
        elif cmd_name == 'dump':
            rep = repr(rep)[2:-1]

        return rep
