from typing import Any
from redis import Redis, exceptions
from .pagesession import PageSession


class NameSpacedRedis(Redis):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._get_commands()

    @staticmethod
    def _pairs_to_dict(response: list) -> dict:
        if response is None:
            return {}
        it = iter(response)
        return dict(zip(it, it))

    @staticmethod
    def _key_spec_to_dict(response: list) -> dict:
        ks = NameSpacedRedis._pairs_to_dict(response)
        ks['begin_search'] = NameSpacedRedis._pairs_to_dict(ks['begin_search'])
        ks['begin_search']['spec'] = NameSpacedRedis._pairs_to_dict(
            ks['begin_search']['spec'])
        ks['find_keys'] = NameSpacedRedis._pairs_to_dict(ks['find_keys'])
        ks['find_keys']['spec'] = NameSpacedRedis._pairs_to_dict(
            ks['find_keys']['spec'])
        return ks

    def _get_commands(self):
        conn = self.connection_pool.get_connection('COMMAND')
        conn.send_command('COMMAND')
        commands = conn.read_response()
        self.connection_pool.release(conn)
        self.commands = {}
        for command in commands:
            name = command[0]
            self.commands[name] = {
                'arity': command[1],
                'key_specs': [NameSpacedRedis._key_spec_to_dict(x) for x in command[8]],
            }

    @staticmethod
    def _match_key_spec(arity: int, spec: dict, argv: list) -> list:
        rep = []
        first, last, step = 0, 0, 0
        argc = len(argv)
        begin_type = spec['begin_search']['type']
        if begin_type == 'index':
            first = spec['begin_search']['spec']['index']
        elif begin_type == 'keyword':
            keyword = spec['begin_search']['spec']['keyword']
            start_from = spec['begin_search']['spec']['startfrom']
            start_index = start_from if start_from > 0 else argc + start_from
            end_index = argc - 1 if start_from > 0 else 0
            i = start_index
            incr = 1 if start_index <= end_index else -1
            while i != end_index:
                if i > argc:
                    break
                if argv[i] == keyword:
                    first = i + 1
                    break
                i += incr
        else:
            return rep

        if first == 0:
            return rep

        find_type = spec['find_keys']['type']
        if find_type == 'range':
            step = spec['find_keys']['spec']['keystep']
            lastkey = spec['find_keys']['spec']['lastkey']
            limit = spec['find_keys']['spec']['limit']
            if lastkey >= 0:
                last = first + lastkey
            else:
                if limit != 0:
                    last = first + (int((argc - first)/limit) + lastkey)
                else:
                    last = argc + lastkey
        elif find_type == 'keynum':
            step = spec['find_keys']['spec']['keystep']
            firstkey = spec['find_keys']['spec']['firstkey']
            keynumidx = spec['find_keys']['spec']['keynumidx']
            keynum = argv[first + keynumidx]
            if type(keynum) is not int:
                return rep
            first += firstkey
            last = first + keynum - 1
        else:
            return rep

        for i in range(first, last + 1, step):
            if i >= argc:
                # Module and negative arity commands (TODO: find out if module command)
                if arity < 0:
                    return []
                else:
                    # Command key specs do not match arguments
                    raise exceptions.RedisError(
                        'keys do not match the command\'s key_specs')
            rep.append(i)
        return rep

    @staticmethod
    def _keys_index(argv: list, cmd: dict) -> list:
        rep = []
        for spec in cmd['key_specs']:
            rep.extend(NameSpacedRedis._match_key_spec(
                cmd['arity'], spec, argv))
        return rep

    @staticmethod
    def _strip_id_from_keys(id: str, keys: list) -> list:
        return [x[len(str(id))+1:] for x in keys]

    def execute_namespaced(self, session: PageSession, argv: list) -> Any:
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
        if cmd_name == 'keys' and argc == 2:
            # Namespace the key pattern
            argv[1] = f'{session.id}:{argv[1]}'
        elif cmd_name == 'scan':
            # Namespace all key patterns (even though only the last one really
            # matters), or slap a namespaced pattern if are given.
            match = False
            for i in range(argc-1):
                if argv[i].lower() == 'match':
                    argv[i+1] = f'{session.id}:{argv[i+1]}'
                    match = True
            if not match:
                argv.append('MATCH')
                argv.append(f'{session.id}:*')
                argc += 2
        elif cmd_name in ['flushdb', 'flushall']:
            # Much easier than finding them keys
            session.relogin()
            return 'OK'
        else:
            # Quickly check arity
            if cmd['arity'] > 0 and argc != cmd['arity']:
                raise exceptions.RedisError(
                    'ERR wrong number of arguments for command')
            elif cmd['arity'] < 0 and argc < abs(cmd['arity']):
                raise exceptions.RedisError(
                    'ERR wrong number of arguments for command')
            # Namespace the key names
            keys_index = self._keys_index(argv, cmd)
            for i in keys_index:
                argv[i] = f'{session}:{argv[i]}'

        # Send the command
        conn = self.connection_pool.get_connection(argv[0])
        conn.send_command(argv[0], *argv[1:])
        rep = conn.read_response()
        self.connection_pool.release(conn)

        # Post-processin'
        if cmd_name == 'keys':
            rep = self._strip_id_from_keys(session.id, rep)
        elif cmd_name == 'scan':
            rep[1] = self._strip_id_from_keys(session.id, rep[1])

        return rep
